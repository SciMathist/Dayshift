"""RoboCasa spike probes for Day Shift Zero. Throwaway code; never imported by src/.

Answers spec section 7 spike questions on this machine:
  P1 load a composite task offscreen, reset time
  P2 step rate: no cameras vs 3x RGB 256x256
  P3 edit object pose + fixture (door) state mid-episode, check it sticks under physics
  P4 persistence: long run stability, state checkpoint/restore, reset behaviour
Prints one JSON report at the end.
"""

import argparse
import json
import platform
import time
import traceback

import numpy as np

REPORT = {"host": {"platform": platform.platform(), "python": platform.python_version()}}


def probe(name):
    def deco(fn):
        def run(*a, **k):
            t0 = time.time()
            try:
                REPORT[name] = {"ok": True, **(fn(*a, **k) or {})}
            except Exception as e:  # spike: record and keep going
                REPORT[name] = {"ok": False, "error": repr(e), "tb": traceback.format_exc()[-1500:]}
            REPORT[name]["wall_s"] = round(time.time() - t0, 2)
        return run
    return deco


def _make(kw, cams):
    import robocasa  # noqa: F401  registers kitchen envs with robosuite
    import robosuite
    from robosuite.controllers import load_composite_controller_config

    return robosuite.make(
        env_name=kw["env_name"],
        robots="PandaOmron",
        controller_configs=load_composite_controller_config(controller=None, robot="PandaOmron"),
        camera_names=["robot0_agentview_left", "robot0_agentview_right", "robot0_eye_in_hand"] if cams else [],
        camera_widths=kw["camera_widths"],
        camera_heights=kw["camera_heights"],
        has_renderer=False,
        has_offscreen_renderer=cams,
        use_camera_obs=cams,
        ignore_done=True,
        use_object_obs=True,
        seed=kw["seed"],
    )


def zero_action(env):
    return np.zeros(env.action_spec[0].shape)


def step_rate(env, n):
    a = zero_action(env)
    t0 = time.time()
    for _ in range(n):
        env.step(a)
    return n / (time.time() - t0)


@probe("P1_load_reset")
def p1(task, seed):
    t0 = time.time()
    env = _make(dict(env_name=task, camera_widths=256, camera_heights=256, seed=seed), cams=True)
    build = time.time() - t0
    t0 = time.time()
    obs = env.reset()
    reset = time.time() - t0
    out = {
        "build_s": round(build, 2),
        "reset_s": round(reset, 2),
        "action_dim": int(env.action_spec[0].shape[0]),
        "control_freq_hz": getattr(env, "control_freq", None),
        "obs_keys_sample": sorted(k for k in obs if "image" in k or k.startswith("robot0_base") or "proprio" in k)[:12],
        "image_shapes": {k: list(v.shape) for k, v in obs.items() if k.endswith("_image")},
        "lang": env.get_ep_meta().get("lang") if hasattr(env, "get_ep_meta") else None,
        "n_objects": len(getattr(env, "objects", {})),
        "fixtures_sample": sorted(getattr(env, "fixtures", {}).keys())[:25],
    }
    env.close()
    return out


@probe("P2_step_rate")
def p2(task, seed, n):
    res = {}
    for cams in (False, True):
        env = _make(dict(env_name=task, camera_widths=256, camera_heights=256, seed=seed), cams=cams)
        env.reset()
        step_rate(env, 10)  # warmup
        res["steps_per_s_cams" if cams else "steps_per_s_nocam"] = round(step_rate(env, n), 1)
        env.close()
    hz = 20.0
    res["realtime_factor_cams_at_20hz"] = round(res["steps_per_s_cams"] / hz, 2)
    res["realtime_factor_nocam_at_20hz"] = round(res["steps_per_s_nocam"] / hz, 2)
    return res


def first_free_object(env):
    for name, obj in env.objects.items():
        if getattr(obj, "joints", None):
            return name, obj
    raise RuntimeError("no free-jointed object found")


def find_door_fixture(env):
    for name, fx in env.fixtures.items():
        if hasattr(fx, "set_door_state") and hasattr(fx, "get_door_state"):
            return name, fx
    raise RuntimeError("no door fixture found")


@probe("P3_midepisode_edits")
def p3(task, seed):
    env = _make(dict(env_name=task, camera_widths=128, camera_heights=128, seed=seed), cams=False)
    env.reset()
    a = zero_action(env)
    for _ in range(20):
        env.step(a)
    out = {}

    # object teleport: lift object 0.3 m and shift it 0.05 m in x, let it settle
    name, obj = first_free_object(env)
    jn = obj.joints[0]
    q0 = env.sim.data.get_joint_qpos(jn).copy()
    q1 = q0.copy()
    q1[0] += 0.05
    q1[2] += 0.30
    env.sim.data.set_joint_qpos(jn, q1)
    env.sim.forward()
    for _ in range(40):
        env.step(a)
    qs = env.sim.data.get_joint_qpos(jn)
    out["obj"] = name
    out["obj_dx_after_settle_m"] = round(float(qs[0] - q0[0]), 3)
    out["obj_dz_after_settle_m"] = round(float(qs[2] - q0[2]), 3)
    out["obj_settled_back_near_start_height"] = abs(float(qs[2] - q0[2])) < 0.05

    # fixture door: open fully, step, read back; then close
    fname, fx = find_door_fixture(env)
    fx.set_door_state(min=0.9, max=1.0, env=env)
    env.sim.forward()
    for _ in range(40):
        env.step(a)
    out["door_fixture"] = fname
    out["door_state_after_open_40steps"] = {k: round(float(v), 3) for k, v in fx.get_door_state(env=env).items()}
    env.close()
    return out


@probe("P4_persistence")
def p4(task, seed, long_steps):
    env = _make(dict(env_name=task, camera_widths=128, camera_heights=128, seed=seed), cams=False)
    env.reset()
    a = zero_action(env)

    # object drift over a long idle run (stand-in for a long shift)
    pos0 = {n: env.sim.data.get_joint_qpos(o.joints[0])[:3].copy() for n, o in env.objects.items() if o.joints}
    t0 = time.time()
    for _ in range(long_steps):
        env.step(a)
    long_s = time.time() - t0
    drift = {n: float(np.linalg.norm(env.sim.data.get_joint_qpos(env.objects[n].joints[0])[:3] - p)) for n, p in pos0.items()}

    # checkpoint / restore
    state = env.sim.get_state().flatten()
    for _ in range(50):
        env.step(np.random.default_rng(0).uniform(-1, 1, a.shape))
    moved = float(np.linalg.norm(env.sim.get_state().flatten() - state))
    env.sim.set_state_from_flattened(state)
    env.sim.forward()
    restored = float(np.linalg.norm(env.sim.get_state().flatten() - state))

    # does reset() rebuild the world (new layout/objects) or keep it?
    names_before = sorted(env.objects.keys())
    model_before = env.sim.model.nbody
    env.reset()
    out = {
        "idle_steps": long_steps,
        "idle_wall_s": round(long_s, 1),
        "max_obj_drift_m": round(max(drift.values()), 4) if drift else None,
        "objs_drift_gt_1cm": [n for n, d in drift.items() if d > 0.01],
        "state_dim": int(state.shape[0]),
        "state_change_after_50_random_steps": round(moved, 3),
        "state_error_after_restore": restored,
        "reset_changes_objects": names_before != sorted(env.objects.keys()),
        "reset_changes_nbody": model_before != env.sim.model.nbody,
    }
    env.close()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="LoadFridgeByType")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--long", type=int, default=2000)
    ap.add_argument("--only", nargs="*", default=["P1", "P2", "P3", "P4"])
    args = ap.parse_args()
    REPORT["task"] = args.task
    if "P1" in args.only:
        p1(args.task, args.seed)
    if "P2" in args.only:
        p2(args.task, args.seed, args.n)
    if "P3" in args.only:
        p3(args.task, args.seed)
    if "P4" in args.only:
        p4(args.task, args.seed, args.long)
    print("=== REPORT ===")
    print(json.dumps(REPORT, indent=1, default=str))
