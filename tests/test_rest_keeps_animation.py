"""Changing a rig's rest keeps what plays: Apply Pose as Rest and Keep Poses (G on the setup frame) take a bone's path
control points and handles along with its keys (they are in the keys' space too); leave a fix's keys on the bones it
moves as they are, adding none (a fix plays its keys as their change from the setup, as an action bone action does); and
keep a 2 Axis Controller on its parent when the parent's rest moves (its keys are its knob's frames in its box). Convert
To Regular and back takes the knob's keys in every ordinary action from frames to moves (and back), not the mainline's
alone.

Run with:  OpenAnimate --background --python tests/test_rest_keeps_animation.py
"""

import math

import oanim

ops, wm = oanim.ops, oanim.wm


def fresh():
    global doc, layers
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    assert ops.layer.new_bone() == {'FINISHED'}
    rid = layers.active.id
    return lambda: next(l for l in layers.all() if l.id == rid)


def bone(rig, name):
    return next(b for b in rig().bones if b["name"] == name)


def heads(rig, name, frames):
    out = {}
    for f in frames:
        doc.frame_current = f
        out[f] = tuple(bone(rig, name)["head"])
    return out


def worst(a, b):
    f = max(a, key=lambda k: math.dist(a[k], b[k]))
    return math.dist(a[f], b[f]), f


def mainline():
    ops.anim.action_set(name="")
    doc.frame_current = 0


def path_scene():
    """A bone keyed on 1 and 28 with a control point bending the stretch between."""
    rig = fresh()
    assert ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0.4", parent="") == {'FINISHED'}
    doc.auto_key = True
    for f, at in ((1, (0.5, 0.2)), (28, (2.0, 1.0))):
        doc.frame_current = f
        rig().bone_set("arm", position=at)
    doc.frame_current = 29  # (the edit keyed as the frame changes)
    doc.auto_key = False
    doc.motion_paths = True
    doc.path_own_motion = True
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    for other in layers.all():
        other.selected = other.id == rig().id
    layers.active = rig()
    rig().select_bone("arm")
    doc.frame_current = 14
    args = dict(bone="arm", layer=str(rig().id))
    assert ops.anim.motion_path_select(frame="28", **args) == {'FINISHED'}
    assert ops.anim.motion_path_control_add(frame="14", **args) == {'FINISHED'}
    assert ops.anim.motion_path_control_move(frame="28", index="0", x="0.4", y="1.6", **args) == {'FINISHED'}
    assert len(wm.motion_path_controls()) == 1
    return rig


def fix_scene():
    """A knob (a controller with two sides) a fix follows, the fix moving Lid; Ear posed on the mainline only."""
    rig = fresh()
    doc.auto_key = True
    for name, x, y in (("Bone", 3.0, 3.0), ("Lid", 0.0, 4.0), ("Ear", -2.0, 1.0)):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(x), head_y=str(y), tail_x=str(x + 1), tail_y=str(y + 0.5),
                                     parent="") == {'FINISHED'}
    for side in ("Right", "Up"):
        assert ops.anim.action_new(name="Bone " + side) == {'FINISHED'}
        doc.frame_current = 24
        rig().bone_set("Ear", angle=bone(rig, "Ear")["setup_angle"] + 0.1)
        doc.frame_current = 25
        mainline()
    rig().select_bone("Bone")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    for side in ("RIGHT", "UP"):
        assert ops.armature.controller_side(side=side, action="Bone " + side.title()) == {'FINISHED'}
    rig().select_bone("Bone")
    assert ops.armature.bone_fix_new(bones="Bone") == {'FINISHED'}
    doc.frame_current = 30
    rig().bone_set("Bone", knob=(24.0, 24.0))
    p = bone(rig, "Lid")["position"]
    rig().bone_set("Lid", position=(p[0] + 0.6, p[1] - 0.3))
    doc.frame_current = 31
    mainline()
    doc.frame_current = 10
    rig().bone_set("Bone", knob=(24.0, 24.0))
    rig().bone_set("Ear", position=(-1.2, 1.7))
    p = bone(rig, "Lid")["position"]
    doc.frame_current = 11
    doc.frame_current = 10
    doc.auto_key = False
    fix = rig().bone_fixes[0]["name"]
    assert rig().bone_fixes[0]["strength"] > 0.99, rig().bone_fixes[0]
    layers.active = rig()
    return rig, fix


def fix_adds(rig, fix, name, f=10):
    """What the fix adds to `name`'s head on frame f: with it playing less with it muted."""
    doc.frame_current = f
    on = bone(rig, name)["head"]
    assert ops.anim.action_play_set(layer=str(rig().id), name=fix, mute="1") == {'FINISHED'}
    doc.frame_current = f + 1
    doc.frame_current = f
    off = bone(rig, name)["head"]
    assert ops.anim.action_play_set(layer=str(rig().id), name=fix, mute="0") == {'FINISHED'}
    doc.frame_current = f + 1
    doc.frame_current = f
    return (on[0] - off[0], on[1] - off[1])


def boxes(rig, posed):
    out = {}
    for f in posed:
        doc.frame_current = f
        b = bone(rig, "Pupil")
        out[f] = (*b["head"], *b.get("knob_head", b["head"]))
    return out


def spots(rig, name, frames):
    """Where a bone shows on each frame: a controller's knob, a regular bone's head."""
    out = {}
    for f in frames:
        doc.frame_current = f
        b = bone(rig, name)
        out[f] = tuple(b.get("knob_head", b["head"]))
    return out


FRAMES = range(1, 29)


# --- Apply Pose as Rest: the stretch's control point comes along with its keys -----------------------------------------
rig = path_scene()
before = heads(rig, "arm", FRAMES)
assert math.dist(before[12], (0.5 + 1.5 * 11 / 27, 0.2 + 0.8 * 11 / 27)) > 0.05, "the control point bends the path"
doc.frame_current = 28
assert ops.armature.apply_pose_as_rest() == {'FINISHED'}
d, f = worst(before, heads(rig, "arm", FRAMES))
assert d < 1e-3, f"Apply Pose as Rest moved the bone {d:.4f} on frame {f}: its path's control point was left behind"

# --- Keep Poses: the same with a setup move -----------------------------------------------------------------------------
rig = path_scene()
before = heads(rig, "arm", FRAMES)
doc.frame_current = 0
rig().select_bone("arm")
assert ops.armature.translate(move_x="0.3", move_y="0.2", posing="0", keep_poses="1") == {'FINISHED'}
assert ops.armature.rotate(angle="20", posing="0", keep_poses="1") == {'FINISHED'}
d, f = worst(before, heads(rig, "arm", FRAMES))
assert d < 1e-3, f"Keep Poses moved the bone {d:.4f} on frame {f}: its path's control point was left behind"


# --- Keep Poses leaves a fix's keys on a bone it moves as they are --------------------------------------------------------
rig, fix = fix_scene()
was = fix_adds(rig, fix, "Lid")
assert math.dist(was, (0.0, 0.0)) > 0.3, ("the fix moves Lid", was)
doc.frame_current = 0
rig().select_bone("Lid")
# (A setup move: what a fix adds, as what an action bone action adds, is a change in the bone's own axes, turning with a
# setup turn.)
assert ops.armature.translate(move_x="0.2", move_y="0.3", posing="0", keep_poses="1") == {'FINISHED'}
now = fix_adds(rig, fix, "Lid")
assert math.dist(was, now) < 1e-4, f"Keep Poses changed what the fix adds to Lid: {was} -> {now}"

# --- Apply Pose as Rest: the fix adds what it did, and keys nothing in it -------------------------------------------------
rig, fix = fix_scene()
was_lid, was_ear = fix_adds(rig, fix, "Lid"), heads(rig, "Ear", (10, 20))
lid_shown = heads(rig, "Lid", (10, 20))
doc.frame_current = 10
assert ops.armature.apply_pose_as_rest() == {'FINISHED'}
assert math.dist(was_lid, fix_adds(rig, fix, "Lid")) < 1e-4, "Apply Pose as Rest changed what the fix adds to Lid"
d, f = worst(was_ear, heads(rig, "Ear", (10, 20)))
assert d < 1e-4, f"Ear, posed on the mainline and never keyed in the fix, moved {d:.4f} on frame {f} (the fix keyed it)"
d, f = worst(lid_shown, heads(rig, "Lid", (10, 20)))
assert d < 1e-4, f"Lid moved {d:.4f} on frame {f}"
ops.anim.action_set(name=fix)
assert not rig().keyframes('bones["Ear"].position') or all(
    k["frame"] == 0 for k in rig().keyframes('bones["Ear"].position')), "no hold key put in the fix"
mainline()

# --- Apply Pose as Rest keeps a controller on its parent -----------------------------------------------------------------
rig = fresh()
assert ops.armature.bone_add(name="Socket", head_x="0", head_y="0", tail_x="1", tail_y="1", parent="") == {'FINISHED'}
ops.armature.select_none()
assert ops.armature.bone_add(name="Pupil", head_x="1.5", head_y="0.5", tail_x="2", tail_y="0.5",
                             parent="Socket") == {'FINISHED'}
rig().select_bone("Pupil")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
rig().bone_set("Pupil", contain_knob=False)
doc.auto_key = True
doc.frame_current = 10
rig().bone_set("Socket", position=(0.8, -0.4), angle=bone(rig, "Socket")["setup_angle"] + 0.5)
rig().bone_set("Pupil", knob=(3.0, 2.0))
doc.frame_current = 20
rig().bone_set("Pupil", knob=(-4.0, 1.0))
doc.frame_current = 21
doc.auto_key = False
layers.active = rig()
# (Frames before the first key follow the new setup pose, the parent's too: the posed frames are what stays.)
posed = (10, 15, 20)


before = boxes(rig, posed)
doc.frame_current = 10
assert ops.armature.apply_pose_as_rest() == {'FINISHED'}
after = boxes(rig, posed)
d, f = max((math.dist(before[f], after[f]), f) for f in posed)
assert d < 1e-4, f"the controller, on a bone whose rest was applied, moved {d:.4f} on frame {f}: {before[f]} -> {after[f]}"

# --- Convert To Regular and back: the knob's keys in an ordinary action too -------------------------------------------
rig = fresh()
assert ops.armature.bone_add(name="Eye", head_x="1", head_y="1", tail_x="1.5", tail_y="1", parent="") == {'FINISHED'}
rig().select_bone("Eye")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
rig().bone_set("Eye", contain_knob=False)
doc.auto_key = True
doc.frame_current = 10
rig().bone_set("Eye", knob=(5.0, 0.0))
assert ops.anim.action_new(name="Wide") == {'FINISHED'}
doc.frame_current = 24
rig().bone_set("Eye", knob=(30.0, 12.0))
doc.frame_current = 25
doc.auto_key = False
in_action = spots(rig, "Eye", (12, 24))
mainline()
on_mainline = spots(rig, "Eye", (10,))
doc.frame_current = 0
rig().select_bone("Eye")
assert ops.armature.bone_convert(type="REGULAR") == {'FINISHED'}
d, f = worst(on_mainline, spots(rig, "Eye", (10,)))
assert d < 1e-3, f"Regular: the mainline moved {d:.4f}"
ops.anim.action_set(name="Wide")
d, f = worst(in_action, spots(rig, "Eye", (12, 24)))
assert d < 1e-3, f"Regular: in Wide on frame {f} the bone is {d:.3f} from where its knob was (its keys left as frames)"
mainline()
rig().select_bone("Eye")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
rig().bone_set("Eye", contain_knob=False)
d, f = worst(on_mainline, spots(rig, "Eye", (10,)))
assert d < 1e-3, f"back to a controller: the mainline moved {d:.4f}"
ops.anim.action_set(name="Wide")
d, f = worst(in_action, spots(rig, "Eye", (12, 24)))
assert d < 1e-3, f"back to a controller: in Wide on frame {f} the knob is {d:.3f} from where it was"
mainline()

print("rest keeps animation: ok")
