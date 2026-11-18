"""Frame to Selected (a pose tile's right-click): its thumbnail framed on the selected points, wherever the pose puts
them, so it goes and scales with them (the character moved or scaled, the points spread); Frame Collection to Selected
does every pose in its collection; Frame to Pose lets go, back round what the pose moves. Kept in the file, an undo
step each, CANCELLED when nothing is selected or nothing changes.

Run with:  OpenAnimate --background --python tests/test_pose_frame.py
"""


import math
import os
import tempfile

import _oanim
import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    if isinstance(a, (int, float)):
        return abs(a - b) < eps
    return all(abs(x - y) < eps for x, y in zip(a, b))


def scene():
    """A bone layer with Arm_L, Arm_R and Leg, a drawing whose points Arm_L moves. Frame 10: the arm raised, a point
    pulled out; frame 20: the arm lowered. Auto Keying on."""
    global doc, layers, rig_id, art_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id
    assert ops.armature.bone_add(name="Arm_L", head_x="0.5", head_y="0", tail_x="1.5", tail_y="0", parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="Arm_R", head_x="-0.5", head_y="0", tail_x="-1.5", tail_y="0",
                                 parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="Leg", head_x="0", head_y="-1", tail_x="0", tail_y="-2", parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.layer.new() == {'FINISHED'}
    art_id = layers.active.id
    art().name = "hand"
    assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
    art().add_curve([(1.2, 0.1), (1.4, 0.3), (1.1, 0.5)])
    assert ops.layer.parent_bone_set(bone="Arm_L", deform="POINTS") == {'FINISHED'}
    art().edit_with_bones = True
    doc.auto_key = True
    doc.frame_current = 10
    rig().bone_set("Arm_L", angle=0.7)
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] + 0.3)
    art().set_point(0, (1.3, 0.0))
    doc.frame_current = 20
    rig().bone_set("Arm_L", angle=-0.4)
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] - 0.5)
    art().set_point(0, (1.6, 0.4))
    at(10)
    # (An undo step of its own, so undoing an operator leaves the scene's Python edits in.)
    layers.active = art()
    assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
    assert ops.object.modifier_remove(index="0") == {'FINISHED'}


def rig():
    return next(l for l in layers.all() if l.id == rig_id)


def art():
    return next(l for l in layers.all() if l.id == art_id)


def bone(name):
    return next(b for b in rig().bones if b["name"] == name)


def stored():
    return [tuple(p[:2]) for p in art().points]


def at(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def select_bones(*names):
    layers.active = rig()
    ops.armature.select_none()
    for i, n in enumerate(names):
        rig().select_bone(n, extend=i > 0)


def select_points(picked):
    layers.active = art()
    ops.mesh.select_none()
    art().select_points(picked)


def select_nothing():
    layers.active = rig()
    ops.armature.select_none()
    layers.active = art()
    ops.mesh.select_none()


def poses():
    return _oanim.poses()


def pose(name):
    return next(p for p in poses() if p["name"] == name)



def square(pts):
    """The square a thumbnail shows round these points: their box's middle, its larger side with room round."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(max(xs) - min(xs), max(ys) - min(ys)) * 1.4)


def shown(*indexes):
    pts = art().shown()[0]
    return [pts[i] for i in indexes]


# --- Saved, a pose is framed on what it moves ----------------------------------------------------------------------------
scene()
select_bones("Arm_L")
assert ops.poselib.pose_new(name="Arm", new_collection="Arms") == {'FINISHED'}
select_bones("Arm_L", "Leg")
assert ops.poselib.pose_new(name="Both", collection="Arms") == {'FINISHED'}
select_bones("Leg")
assert ops.poselib.pose_new(name="Leg", new_collection="Legs") == {'FINISHED'}
arm, both, leg = pose("Arm")["id"], pose("Both")["id"], pose("Leg")["id"]
auto = wm_frame = _oanim.pose_thumbnail_frame(arm)
assert close(auto, square(shown(0, 1, 2))), (auto, square(shown(0, 1, 2)))

# --- Frame to Selected: framed on two of the hand's points ---------------------------------------------------------------
select_nothing()
assert ops.poselib.frame_selected(pose=str(arm)) == {'CANCELLED'}, "nothing selected"
select_points([0, 1])
assert ops.poselib.frame_selected(pose=str(arm)) == {'FINISHED'}
assert close(_oanim.pose_thumbnail_frame(arm), square(shown(0, 1))), _oanim.pose_thumbnail_frame(arm)
assert pose("Arm")["frame_points"] == 2
assert pose("Both")["frame_points"] == 0, "only that pose"
assert ops.poselib.frame_selected(pose=str(arm)) == {'CANCELLED'}, "already framed so"
assert ops.ed.undo() == {'FINISHED'}
assert pose("Arm")["frame_points"] == 0, "an undo step"
assert ops.ed.redo() == {'FINISHED'}
assert pose("Arm")["frame_points"] == 2

# --- It goes and scales with them ----------------------------------------------------------------------------------------
rig().location_x = rig().location_x + 2.0
assert close(_oanim.pose_thumbnail_frame(arm), square(shown(0, 1))), "moved with them"
rig().scale_x = 2.0
rig().scale_y = 2.0
assert close(_oanim.pose_thumbnail_frame(arm), square(shown(0, 1))), "scaled with them"
local = art().points[1]
art().set_point(1, (local[0] + 1.5, local[1] + 0.5))
assert close(_oanim.pose_thumbnail_frame(arm), square(shown(0, 1))), "spread: still round both"
# Where the pose puts them, not where they are now: on frame 20 the arm is lowered, the pose raises it.
at(20)
lowered = square(shown(0, 1))
assert not close(_oanim.pose_thumbnail_frame(arm), lowered, 0.05), (_oanim.pose_thumbnail_frame(arm), lowered)
at(10)

# --- Kept in the file ----------------------------------------------------------------------------------------------------
was = _oanim.pose_thumbnail_frame(arm)
path = os.path.join(tempfile.gettempdir(), "oa_pose_frame_%d.oanim" % os.getpid())
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
os.remove(path)
assert pose("Arm")["frame_points"] == 2
assert close(_oanim.pose_thumbnail_frame(arm), was), "kept in the file"

# --- Frame Collection to Selected: every pose in its collection, not the others -----------------------------------------
select_points([2])
assert ops.poselib.frame_selected(pose=str(arm), collection="1") == {'FINISHED'}
assert [pose(n)["frame_points"] for n in ("Arm", "Both", "Leg")] == [1, 1, 0]
assert close(_oanim.pose_thumbnail_frame(both)[:2], shown(2)[0]), "Both framed on the point too"

# --- Frame to Pose: back round what it moves ----------------------------------------------------------------------------
assert ops.poselib.frame_pose(pose=str(both)) == {'FINISHED'}
assert [pose(n)["frame_points"] for n in ("Arm", "Both", "Leg")] == [1, 0, 0]
assert ops.poselib.frame_pose(pose=str(both)) == {'CANCELLED'}, "nothing to let go"
assert ops.poselib.frame_pose(pose=str(arm), collection="1") == {'FINISHED'}
assert [pose(n)["frame_points"] for n in ("Arm", "Both", "Leg")] == [0, 0, 0]

# --- Its points gone: framed on what it moves again ----------------------------------------------------------------------
select_points([0, 1])
assert ops.poselib.frame_selected(pose=str(arm)) == {'FINISHED'}
layers.active = art()
ops.mesh.select_none()
art().select_points([0, 1])
assert ops.mesh.delete() == {'FINISHED'}
assert _oanim.pose_thumbnail_frame(arm) is not None, "still a thumbnail, round what the pose moves"

print("test_pose_frame: OK")
