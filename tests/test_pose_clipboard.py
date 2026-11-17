"""Copy Pose and Paste Pose, as Blender's pose mode: off the setup frame Ctrl C over the viewport copies the selected
bones' and points' pose and Ctrl V puts it back on the same bones and points on another frame or in an action (Auto
Keying keys it; without it, it is an edit going to another frame drops). On frame 0, where the drawing is made, Ctrl C
copies shapes as before, and Ctrl V pastes a pose copied on another frame as the setup pose (Keep Poses as a move's). Options: On Selected Only, Factor (a blend toward the copied pose), Ignore
Bones (each point shows where it did when copied, whatever the bones do here) and Keep Place (the shape only, its
centre staying where it is).

Run with:  OpenAnimate --background --python tests/test_pose_clipboard.py
"""

import math

import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def scene():
    """A bone layer with two bones, a drawing whose points the first bone moves (Parent Bone, Points). Frame 10: the
    bones at rest and a point pulled out; frame 20: the bones turned, the point pulled elsewhere. Auto Keying on."""
    global doc, layers, rig_id, art_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id
    assert ops.armature.bone_add(name="Arm", head_x="0", head_y="0", tail_x="1", tail_y="0", parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="Leg", head_x="0", head_y="-1", tail_x="0", tail_y="-2",
                                 parent="") == {'FINISHED'}
    assert ops.layer.new() == {'FINISHED'}
    art_id = layers.active.id
    assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
    art().add_curve([(0.2, 0.1), (0.4, 0.3), (0.1, 0.5)])
    assert ops.layer.parent_bone_set(bone="Arm", deform="POINTS") == {'FINISHED'}
    doc.auto_key = True
    doc.frame_current = 10
    art().set_point(0, (0.3, 0.0))
    art().set_point(1, (0.5, 0.2))
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] + 0.3)
    doc.frame_current = 20
    rig().bone_set("Arm", angle=0.8)
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] - 0.6, position=(0.5, -1.2))
    art().set_point(0, (0.6, 0.4))
    art().set_point(1, (0.7, 0.1))
    doc.frame_current = 21
    doc.frame_current = 10
    # (An undo step of its own, so undoing a paste leaves the scene's Python edits in.)
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


def shown():
    return [tuple(p) for p in art().shown()[0]]


def edit_points(picked):
    layers.active = art()
    for l in layers.all():
        l.selected = l.id == art_id
    ops.mesh.select_none()
    art().select_points(picked)


def said():
    """What the status bar last reported."""
    r = wm.banner_report()
    return r[2] + " " + r[3]


def last_step():
    names, index = wm.undo_history()
    return names[index]


def at(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


# --- Ctrl C off the setup frame copies the points' pose; Ctrl V puts it back, keyed ------------------------------------
scene()
was_stored, was_shown = stored(), shown()
edit_points([0, 1])
assert wm.event_simulate("C", ctrl=True, area="Viewport")
assert "pose" in said(), said()
at(20)
before = stored()
assert not close(before[0], was_stored[0])
assert wm.event_simulate("V", ctrl=True, area="Viewport")
assert last_step() == "Paste Pose", last_step()
op = wm.last_operation()
assert op and op[0] == "pose.paste" and {"selected_mask", "factor", "paste_as", "keep_place"} <= set(op[1]), op
now = stored()
assert close(now[0], was_stored[0]) and close(now[1], was_stored[1]), (now, was_stored)
assert close(now[2], before[2]), "a point not copied stays"
# (Its keys hold the same change: the turned bone carries the points somewhere else than frame 10 showed them.)
assert not close(shown()[0], was_shown[0])
at(20)
assert close(stored()[0], was_stored[0]), "Auto Keying keyed the pasted pose"
assert 20 in [k["frame"] for k in art().keyframes("points[0].pos")]

# --- Ignore Bones: each point shows where it did when copied ------------------------------------------------------------
scene()
was_shown = shown()
edit_points([0, 1])
assert ops.pose.copy() == {'FINISHED'}
at(20)
assert ops.pose.paste(ignore_bones="1") == {'FINISHED'}
assert close(shown()[0], was_shown[0]) and close(shown()[1], was_shown[1]), (shown(), was_shown)
at(20)
assert close(shown()[0], was_shown[0]), "kept as pasted"
# Kept for next time, as the timeline's.
ops.ed.undo()
at(20)
assert not close(shown()[0], was_shown[0]), "undone"
edit_points([0, 1])
assert ops.pose.paste() == {'FINISHED'}
assert close(shown()[0], was_shown[0]), "Ignore Bones was kept from the last paste"
assert ops.pose.paste(ignore_bones="0") == {'FINISHED'}

# --- Keep Place: the shape only, its centre staying where it is --------------------------------------------------------
scene()
was = stored()
edit_points([0, 1])
assert ops.pose.copy() == {'FINISHED'}
at(20)
centre = lambda pts: ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
centre_was = centre(shown())
assert ops.pose.paste(keep_place="1", ignore_bones="0") == {'FINISHED'}
now = stored()
assert close(centre(shown()), centre_was), (centre(shown()), centre_was)
assert close((now[1][0] - now[0][0], now[1][1] - now[0][1]), (was[1][0] - was[0][0], was[1][1] - was[0][1])), \
    "the copied shape"
assert ops.pose.paste(keep_place="0") == {'FINISHED'}

# --- Bones: by name, On Selected Only, Factor ---------------------------------------------------------------------------
scene()
layers.active = rig()
rig().select_bone("Arm")
rig().select_bone("Leg", extend=True)
pose10 = {n: (bone(n)["angle"], tuple(bone(n)["position"])) for n in ("Arm", "Leg")}
assert wm.event_simulate("C", ctrl=True, area="Viewport")
assert "pose" in said(), said()
at(20)
pose20 = {n: (bone(n)["angle"], tuple(bone(n)["position"])) for n in ("Arm", "Leg")}
assert not close(pose10["Leg"][1], pose20["Leg"][1])
assert ops.pose.paste() == {'FINISHED'}
for n in ("Arm", "Leg"):
    assert abs(bone(n)["angle"] - pose10[n][0]) < 1e-4 and close(bone(n)["position"], pose10[n][1]), n
at(20)
assert abs(bone("Arm")["angle"] - pose10["Arm"][0]) < 1e-4, "keyed"
ops.ed.undo()
at(20)
layers.active = rig()
rig().select_bone("Leg")
assert ops.pose.paste(selected_mask="1") == {'FINISHED'}
assert abs(bone("Leg")["angle"] - pose10["Leg"][0]) < 1e-4
assert abs(bone("Arm")["angle"] - pose20["Arm"][0]) < 1e-4, "Arm isn't selected: left as it was"
ops.ed.undo()
at(20)
layers.active = rig()
assert ops.pose.paste(factor="0.5") == {'FINISHED'}
half = (pose10["Leg"][0] + pose20["Leg"][0]) / 2
assert abs(bone("Leg")["angle"] - half) < 1e-4, (bone("Leg")["angle"], half)

# --- Bones and points copied together, pasted inside an action ---------------------------------------------------------
scene()
layers.active = rig()
rig().select_bone("Leg")
edit_points([0])
layers.active = rig()
leg10 = bone("Leg")["angle"]
point10 = stored()[0]
assert ops.pose.copy() == {'FINISHED'}
assert ops.anim.action_new(name="Kick") == {'FINISHED'}
at(5)
assert ops.pose.paste() == {'FINISHED'}
assert abs(bone("Leg")["angle"] - leg10) < 1e-4
assert close(stored()[0], point10)
at(5)
assert abs(bone("Leg")["angle"] - leg10) < 1e-4, "keyed in the action"
ops.anim.action_set(name="")

# --- Without Auto Keying it is an edit, dropped going to another frame (as Blender's) ----------------------------------
scene()
edit_points([0])
assert ops.pose.copy() == {'FINISHED'}
at(20)
before = stored()[0]
doc.auto_key = False
assert ops.pose.paste() == {'FINISHED'}
assert not close(stored()[0], before)
at(20)
assert close(stored()[0], before), "not keyed"

# --- Where the copied points aren't, Ctrl V pastes the shapes copied with them ----------------------------------------
scene()
edit_points([0, 1, 2])
assert ops.pose.copy() == {'FINISHED'}
assert ops.layer.new() == {'FINISHED'}
other = layers.active
for l in layers.all():
    l.selected = l.id == other.id
at(20)
assert wm.event_simulate("V", ctrl=True, area="Viewport")
assert last_step() == "Paste Shapes", last_step()
assert len(next(l for l in layers.all() if l.id == other.id).points) == 3

# --- A pose copied off the setup frame pasted on it: the setup pose takes it (as a move there does) ------------------
def setup_paste(keep):
    scene()
    at(10)
    layers.active = rig()
    ops.armature.select_none()
    rig().select_bone("Leg")
    leg_setup, leg10 = bone("Leg")["setup_angle"], bone("Leg")["angle"]
    assert ops.pose.copy() == {'FINISHED'}
    at(20)
    leg20 = bone("Leg")["angle"]
    doc.frame_current = 0
    assert ops.pose.paste(keep_poses="1" if keep else "0") == {'FINISHED'}, "a pose pastes on the setup frame"
    assert abs(bone("Leg")["angle"] - leg10) < 1e-5, ("the setup pose takes it", bone("Leg")["angle"], leg10)
    op = wm.last_operation()
    assert op and op[1].get("setup") == "1" and "keep_poses" in op[1], op
    at(0)
    assert abs(bone("Leg")["setup_angle"] - leg10) < 1e-5, ("its setup now", bone("Leg")["setup_angle"], leg10)
    at(20)
    # Keep Poses: frame 20 shows as it did; without, its key's change goes on top of the new setup.
    want = leg20 if keep else leg20 + (leg10 - leg_setup)
    assert abs(bone("Leg")["angle"] - want) < 1e-4, (keep, bone("Leg")["angle"], want)

    # Points: the setup takes where they were on frame 10.
    scene()
    at(10)
    was10, was20 = stored(), None
    edit_points([0, 1])
    assert ops.pose.copy() == {'FINISHED'}
    at(20)
    was20 = stored()
    doc.frame_current = 0
    edit_points([0, 1])
    setup = stored()
    assert ops.pose.paste(keep_poses="1" if keep else "0") == {'FINISHED'}
    at(0)
    now = stored()
    assert close(now[0], was10[0]) and close(now[1], was10[1]), (now, was10)
    assert close(now[2], setup[2]), "a point not copied stays"
    at(20)
    for i in (0, 1):
        want = was20[i] if keep else tuple(w + (a - s) for w, a, s in zip(was20[i], was10[i], setup[i]))
        assert close(stored()[i], want), (keep, i, stored()[i], want)


setup_paste(keep=False)
setup_paste(keep=True)

# --- On the setup frame Ctrl C and Ctrl V are the shapes' (a pose pasted where its points aren't: the shapes) --------
scene()
doc.frame_current = 0
edit_points([0, 1, 2])
assert wm.event_simulate("C", ctrl=True, area="Viewport")
assert "shape" in said(), said()
curves = len(art().shown()[1])
at(20)
assert wm.event_simulate("V", ctrl=True, area="Viewport")
assert last_step() == "Paste Shapes", ("shapes copied last paste as shapes", last_step())
assert len(art().shown()[1]) == curves + 1

print("pose clipboard: ok")
