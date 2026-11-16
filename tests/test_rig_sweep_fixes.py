"""Bugs a sweep of bones and rigging found, each section its own scene: Add Spot's numbers, renaming a bone to another
bone's or an action's name, Mirror Controller Side onto an aligned point, and Paste Pose as Same Look where the paste
moves the knob that plays an action.

Run with:  OpenAnimate --background --python tests/test_rig_sweep_fixes.py
"""

import math

import oanim

ops, wm, L = oanim.ops, oanim.wm, oanim.data.layers


def close(a, b, eps=1e-4):
    if isinstance(a, (int, float)):
        return abs(a - b) < eps
    return all(close(x, y, eps) for x, y in zip(a, b))


def rig_new(bones):
    """A bone layer with `bones` (name, head, tail) at frame 0, Auto Keying on."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_key = True
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = L.active
    for name, head, tail in bones:
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(head[0]), head_y=str(head[1]), tail_x=str(tail[0]),
                                     tail_y=str(tail[1])) == {"FINISHED"}
    return doc, rig


def bone(rig, name):
    return next(b for b in rig.bones if b["name"] == name)


def go(doc, frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def knob_new(rig, name):
    L.active = rig
    ops.armature.select_none()
    rig.select_bone(name)
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {"FINISHED"}


# --- Add Spot refuses nan, inf and numbers past ten million ---------------------------------------------------------------
doc, rig = rig_new([("K", (1, 0), (1.2, 0))])
knob_new(rig, "K")
for x, y in (("nan", "0"), ("inf", "0"), ("0", "-inf"), ("1e30", "0"), ("x", "0")):
    was = wm.undo_history()[1]
    assert ops.armature.controller_spot_add(x=x, y=y) == {"CANCELLED"}, (x, y)
    assert wm.undo_history()[1] == was and not bone(rig, "K")["controller_spots"], bone(rig, "K")["controller_spots"]
assert ops.armature.controller_spot_add(x="3", y="1", name="Up") == {"FINISHED"}
spots = bone(rig, "K")["controller_spots"]
assert len(spots) == 1 and spots[0][0] == "Up" and close(spots[0][1], (3.0, 1.0)), spots

# --- Renaming a bone: never another bone's name, nor an ordinary action's (it would become the bone's own) -----------------
doc, rig = rig_new([("arm", (0, 0), (1, 0)), ("leg", (0, -1), (0, -2))])
assert ops.anim.action_new(name="wave") == {"FINISHED"}
doc.frame_current = 10
rig.bone_set("leg", angle=bone(rig, "leg")["angle"] + 0.5)
go(doc, 10)
doc.action = ""
go(doc, 0)
kind = next(a["kind"] for a in rig.actions if a["name"] == "wave")
for to in ("leg", "wave"):
    try:
        rig.bone_set("arm", name=to)
    except ValueError:
        pass
    else:
        raise AssertionError("renamed to " + to)
names = [b["name"] for b in rig.bones]
assert sorted(names) == ["arm", "leg"], names
assert next(a["kind"] for a in rig.actions if a["name"] == "wave") == kind == "ACTION", rig.actions
# Its own name, and a free one, as before.
rig.bone_set("arm", name="arm")
rig.bone_set("arm", name="hand")
assert sorted(b["name"] for b in rig.bones) == ["hand", "leg"]

# --- Mirror Controller Side onto an aligned point keeps its handles in line ------------------------------------------------
doc, rig = rig_new([("K", (3, 0), (3.2, 0))])
ops.layer.new()
brow = L.active
brow.name = "Brow_X"
ops.layer.move_to_group(group=str(rig.id))
brow.add_curve([(-0.9, 0.0), (-0.5, 0.3), (0.0, 0.4), (0.5, 0.3), (0.9, 0.0)])
ops.mesh.select_none(); brow.select_points([1])
assert ops.mesh.handles_align() in ({"FINISHED"}, {"CANCELLED"})
ops.mesh.select_none(); brow.select_points([3])
assert ops.mesh.handles_unalign() in ({"FINISHED"}, {"CANCELLED"})
ops.mesh.select_none()
assert brow.curve_handles(0)[1][0] == "ALIGNED" and brow.curve_handles(0)[3][0] == "FREE"
knob_new(rig, "K")
assert ops.armature.controller_action_new(side="RIGHT") == {"FINISHED"}
side = doc.action
doc.frame_current = 10
h = brow.curve_handles(0)[3]
brow.move_handle(0, 3, "OUT", (h[2][0], h[2][1] + 0.15))
go(doc, 10)
doc.action = ""
go(doc, 0)
L.active = rig
ops.armature.select_none()
rig.select_bone("K")
assert ops.armature.controller_mirror(side="LEFT") == {"FINISHED"}
mirrored = bone(rig, "K")["controller_actions"]["LEFT"]
assert mirrored and mirrored != side, bone(rig, "K")["controller_actions"]
doc.action = mirrored
worst = 0.0
for f in range(0, 11):
    doc.frame_current = f
    p = brow.points[brow.curve_points(0)[1]]
    t, hi, ho = brow.curve_handles(0)[1]
    a = (hi[0] - p[0], hi[1] - p[1])
    b = (ho[0] - p[0], ho[1] - p[1])
    la, lb = math.hypot(*a), math.hypot(*b)
    worst = max(worst, math.degrees(math.atan2(abs(a[0] * b[1] - a[1] * b[0]), -(a[0] * b[0] + a[1] * b[1]))))
assert worst < 0.05, ("the aligned point's handles bend", worst)
doc.action = ""

# --- Paste Pose as Same Look, the paste moving the knob that plays an action: one press gives the look ---------------------
for flipped in (False, True):
    doc, rig = rig_new([("K", (3, 0), (3.2, 0)), ("nose", (0, 0), (0, 0.3))])
    knob_new(rig, "K")
    assert ops.armature.controller_action_new(side="RIGHT") == {"FINISHED"}
    doc.frame_current = 10
    rig.bone_set("nose", position=(0.3, 0.0))
    go(doc, 10)
    doc.action = ""
    go(doc, 0)
    doc.frame_current = 5
    rig.bone_set("K", knob=(10.0, 0.0))
    go(doc, 5)
    looked = bone(rig, "nose")["head"]
    assert not close(looked, (0.0, 0.0)), "the knob's action moves the nose"
    L.active = rig
    ops.armature.select_all()
    assert ops.pose.copy() == {"FINISHED"}
    go(doc, 1)
    ops.armature.select_none()
    paste = ops.pose.paste_flipped if flipped else ops.pose.paste
    assert paste(paste_as="LOOK") == {"FINISHED"}
    go(doc, 1)
    once = bone(rig, "nose")["head"]
    want = (-looked[0], looked[1]) if flipped else looked
    assert close(once, want), (flipped, "one press", once, want)
    assert paste(paste_as="LOOK") == {"FINISHED"}
    go(doc, 1)
    assert close(bone(rig, "nose")["head"], once), (flipped, "a second press changes nothing")

print("rig sweep fixes: ok")
