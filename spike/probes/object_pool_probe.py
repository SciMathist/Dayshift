"""Spike: object pool for deliveries in a compiled-once MuJoCo model. Throwaway.

Idea: let RoboCasa place pool objects at valid rest poses during build, record those poses,
park the objects far away floating (body_gravcomp=1, zero velocity), and "deliver" by
restoring a recorded rest pose with gravity re-enabled. Measures parking stability,
delivery settle error, and whether parked objects disturb the scene.
"""

import json
import time

import numpy as np

import robocasa  # noqa: F401
from robocasa.environments.kitchen.kitchen import FixtureType, Kitchen
import robosuite
from robosuite.controllers import load_composite_controller_config

POOL = ["egg", "butter_stick", "milk", "chicken_breast", "cake", "tupperware"]
PARK_ORIGIN = np.array([40.0, 40.0, 2.0])


class DszPoolProbe(Kitchen):
    """Minimal kitchen with a delivery pool; registered with robosuite on class creation."""

    def _setup_kitchen_references(self):
        super()._setup_kitchen_references()
        self.counter = self.register_fixture_ref("counter", dict(id=FixtureType.COUNTER, size=(0.6, 0.6)))
        self.init_robot_base_ref = self.counter

    def _load_model(self):
        super()._load_model()
        # MuJoCo only applies gravcomp if ngravcomp > 0 at compile time; a static, contact-free
        # anchor body with gravcomp makes runtime toggling of body_gravcomp effective.
        import xml.etree.ElementTree as ET

        anchor = ET.Element("body", name="dsz_gravcomp_anchor", pos="40 40 -5", gravcomp="1")
        ET.SubElement(anchor, "geom", type="sphere", size="0.001", contype="0", conaffinity="0", group="5")
        self.model.worldbody.append(anchor)

    def _get_obj_cfgs(self):
        return [
            dict(
                name=f"pool_{g}",
                obj_groups=g,
                graspable=True,
                placement=dict(fixture=self.counter, size=(1.0, 0.6), pos=(0.0, -1.0)),
            )
            for g in POOL
        ]


def subtree_ids(env, obj):
    """Root body of the object plus all descendants (mass may sit on child bodies)."""
    root = env.sim.model.body_name2id(obj.root_body)
    parent = env.sim.model.body_parentid
    ids = [root]
    for b in range(root + 1, env.sim.model.nbody):
        p = b
        while p not in (0, root):
            p = parent[p]
        if p == root:
            ids.append(b)
    return ids


def set_gravcomp(env, obj, value):
    for b in subtree_ids(env, obj):
        env.sim.model.body_gravcomp[b] = value


def set_free_pose(env, obj, pos, quat=None):
    jn = obj.joints[0]
    q = env.sim.data.get_joint_qpos(jn).copy()
    q[:3] = pos
    if quat is not None:
        q[3:7] = quat
    env.sim.data.set_joint_qpos(jn, q)
    env.sim.data.set_joint_qvel(jn, np.zeros(6))


def main():
    env = robosuite.make(
        env_name="DszPoolProbe",
        robots="PandaOmron",
        controller_configs=load_composite_controller_config(controller=None, robot="PandaOmron"),
        has_renderer=False,
        has_offscreen_renderer=False,
        use_camera_obs=False,
        ignore_done=True,
        seed=0,
        obj_registries=("objaverse", "lightwheel", "aigen"),
        layout_ids=[1],
        style_ids=[1],
    )
    env.reset()
    a = np.zeros(env.action_spec[0].shape)
    out = {"pool_requested": POOL, "pool_built": sorted(env.objects)}

    # 1. record valid rest poses chosen by RoboCasa's placement sampler
    for _ in range(20):
        env.step(a)
    rest = {n: env.sim.data.get_joint_qpos(o.joints[0]).copy() for n, o in env.objects.items()}

    # 2. park: float far away, spaced 1 m apart
    for i, (n, o) in enumerate(env.objects.items()):
        set_gravcomp(env, o, 1.0)
        set_free_pose(env, o, PARK_ORIGIN + np.array([i * 1.0, 0, 0]))
    env.sim.forward()
    parked = {n: env.sim.data.get_joint_qpos(o.joints[0])[:3].copy() for n, o in env.objects.items()}
    t0 = time.time()
    for _ in range(400):
        env.step(a)
    out["park_400_steps_wall_s"] = round(time.time() - t0, 2)
    out["park_max_drift_m"] = round(max(
        float(np.linalg.norm(env.sim.data.get_joint_qpos(o.joints[0])[:3] - parked[n])) for n, o in env.objects.items()
    ), 5)

    # 3. deliver one at a time back to its recorded rest pose, gravity on, measure settle error
    settle = {}
    for n, o in env.objects.items():
        set_gravcomp(env, o, 0.0)
        set_free_pose(env, o, rest[n][:3] + np.array([0, 0, 0.005]), rest[n][3:7])
        env.sim.forward()
        for _ in range(40):
            env.step(a)
        settle[n] = round(float(np.linalg.norm(env.sim.data.get_joint_qpos(o.joints[0])[:3] - rest[n][:3])), 4)
    out["deliver_settle_err_m"] = settle

    # 4. checkpoint must carry gravcomp? (it is a model field, not in qpos/qvel state)
    out["note_gravcomp_is_model_field"] = "body_gravcomp lives in MjModel, so checkpoints must save it alongside sim state"
    env.close()
    print("=== REPORT ===")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
