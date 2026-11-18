"""A pose's thumbnail frame: Save Pose shows a square in the viewport, at first round what the pose moves; dragging inside
moves it, a corner resizes it (square, the corner across staying); saved with the pose (poselib.pose_new's frame_x,
frame_y, frame_size) its thumbnail is framed on it, kept in the file; Fit to Pose leaves it round what it moves; Edit
Frame (poselib.frame_set) frames a saved pose again, frame_size=0 back round what it moves.

Run with:  OpenAnimate --background --python tests/test_pose_frame.py
"""

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


# --- Save Pose: the frame starts round what the pose moves --------------------------------------------------------------
scene()
select_bones("Arm_L")
wm.pose_frame_open()
start = wm.pose_frame()
assert start is not None, "Save Pose shows a frame"
assert ops.poselib.pose_new(name="Auto", new_collection="Arms") == {'FINISHED'}
auto = wm.pose_thumbnail_frame(pose("Auto")["id"])
assert close(auto, start), (auto, start)

# --- Dragging inside moves it; a corner resizes it, square, the corner across staying ------------------------------------
x, y, s = start
assert wm.pose_frame_drag((x, y), (x + 0.5, y - 0.25))
assert close(wm.pose_frame(), (x + 0.5, y - 0.25, s)), wm.pose_frame()
x, y, s = wm.pose_frame()
assert wm.pose_frame_drag((x + s / 2, y + s / 2), (x + s / 2 + 0.4, y + s / 2 + 0.1), reach=0.01)
lo = (x - s / 2, y - s / 2)
assert close(wm.pose_frame(), (lo[0] + (s + 0.4) / 2, lo[1] + (s + 0.4) / 2, s + 0.4)), wm.pose_frame()
assert not wm.pose_frame_drag((x + 50.0, y + 50.0), (0.0, 0.0)), "a press off the frame isn't taken"
wm.pose_frame_open(-1)
assert wm.pose_frame() is None, "closed: no frame"

# --- Saved with a frame: its thumbnail is framed on it, kept in the file --------------------------------------------------
assert ops.poselib.pose_new(name="Framed", collection="Arms", frame_x="0.25", frame_y="-0.5", frame_size="3") == {'FINISHED'}
framed = pose("Framed")["id"]
assert close(wm.pose_thumbnail_frame(framed), (0.25, -0.5, 3.0)), wm.pose_thumbnail_frame(framed)
path = os.path.join(tempfile.gettempdir(), "oa_pose_frame_%d.oanim" % os.getpid())
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
os.remove(path)
assert close(wm.pose_thumbnail_frame(framed), (0.25, -0.5, 3.0)), "kept in the file"
assert close(wm.pose_thumbnail_frame(pose("Auto")["id"]), auto), "one without a frame still fits what it moves"

# --- Edit Frame: shown as given, set again, then back round what it moves ------------------------------------------------
wm.pose_frame_open(framed)
assert close(wm.pose_frame(), (0.25, -0.5, 3.0)), wm.pose_frame()
wm.pose_frame_open(-1)
wm.pose_frame_open(pose("Auto")["id"])
assert close(wm.pose_frame(), auto), "a pose framed on what it moves shows that"
wm.pose_frame_open(-1)
assert ops.poselib.frame_set(pose=str(framed), frame_x="1", frame_y="1", frame_size="0.5") == {'FINISHED'}
assert close(wm.pose_thumbnail_frame(framed), (1.0, 1.0, 0.5))
assert ops.ed.undo() == {'FINISHED'}
assert close(wm.pose_thumbnail_frame(framed), (0.25, -0.5, 3.0)), "an undo step"
assert ops.poselib.frame_set(pose=str(framed), frame_size="0") == {'FINISHED'}
assert close(wm.pose_thumbnail_frame(framed), auto), "frame_size=0: round what it moves again"
assert ops.poselib.frame_set(pose=str(framed), frame_size="0") == {'CANCELLED'}, "nothing to change"
assert ops.poselib.frame_set(pose=str(framed), frame_x="1", frame_y="1", frame_size="-2") == {'CANCELLED'}

print("test_pose_frame: OK")
