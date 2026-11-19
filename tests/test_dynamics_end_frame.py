"""Dynamics are simulated to the scene's end frame and no further: past it a frame goes on one step from the end. Every
frame from the start to the one shown was simulated, so a far frame took seconds (frame 20000 in the clay file 13.8 s)
and a key put on frame 1,000,000 ran for minutes.

Run with:  OpenAnimate --background --python tests/test_dynamics_end_frame.py
"""

import faulthandler
import math
import time

import oanim

ops, L = oanim.ops, oanim.data.layers


def scene():
    """A spring hanging from a pusher that moves on frames 1 to 6; the scene ends on frame 24."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_freeze_keys = False
    doc.frame_end = 24
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = L.active
    for name, h, t, parent in (("pusher", (0, 0), (1, 0), ""), ("spring", (1, 0), (2, 0), "pusher")):
        assert ops.armature.bone_add(name=name, head_x=str(h[0]), head_y=str(h[1]), tail_x=str(t[0]),
                                     tail_y=str(t[1]), parent=parent) == {'FINISHED'}
    assert ops.armature.constraint_add(bone="spring", type="DYNAMICS") == {'FINISHED'}
    for f, x in ((1, 0.0), (6, 3.0)):
        doc.frame_current = f
        rig.select_bone("pusher")
        rig.bone_set("pusher", position=(x, 0.0))
        assert ops.anim.keyframe_insert() == {'FINISHED'}
    return doc, rig


def tip(doc, rig, f):
    doc.frame_current = f
    return next(b for b in rig.bones if b["name"] == "spring")["tail"]


# --- A far frame takes no longer than the end, and shows as just past the end -------------------------------------------
doc, rig = scene()
moving = [tip(doc, rig, f) for f in range(1, 25)]
assert max(math.dist(a, b) for a, b in zip(moving, moving[1:])) > 1e-3, "the spring lags and swings"
past = tip(doc, rig, 30)
faulthandler.dump_traceback_later(30, exit=True)
start = time.time()
far = tip(doc, rig, 1_000_000)
took = time.time() - start
faulthandler.cancel_dump_traceback_later()
assert took < 2.0, ("frame 1,000,000 simulated every frame on the way", took)
assert math.dist(far, past) < 1e-6, ("past the end every frame goes on one step from it", far, past)
# A key on a far frame too.
doc.frame_current = 1_000_000
rig.select_bone("pusher")
rig.bone_set("pusher", position=(5.0, 0.0))
start = time.time()
assert ops.anim.keyframe_insert() == {'FINISHED'}
assert time.time() - start < 2.0, "a key on frame 1,000,000"

print("dynamics end frame: ok")
