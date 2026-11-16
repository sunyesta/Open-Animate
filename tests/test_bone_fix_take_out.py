"""Take Out Action (a fix's right-click menu in the Bone tab's Fix Actions, armature.bone_fix_take_out): keys a fix
so an action playing under it adds nothing on its poses (the frames its line has keys on), the opposite of what it adds
there on every bone and point it moves, so the fix is edited from the pose without it. Factor takes out part of it, On
Selected Only only on the selected bones and points. The fix's own keys stay on top; it opens the fix for it and goes
back to where you were.

Run with:  OpenAnimate --background --python tests/test_bone_fix_take_out.py
"""

import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-3):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    return abs(a - b) < eps


def find(layer_id):
    return next(l for l in layers.all() if l.id == layer_id)


def rig():
    return find(rig_id)


def face():
    return find(face_id)


def point(i):
    return tuple(face().shown()[0][i])


def bone(name):
    return next(b for b in rig().bones if b["name"] == name)


def settle():
    doc.frame_current = doc.frame_current + 1
    doc.frame_current = doc.frame_current - 1


def mainline():
    assert ops.anim.action_set(name="") in ({'FINISHED'}, {'CANCELLED'})
    doc.frame_current = 0


def ordinary(name, moves, turn=None):
    """An action moving the face's points (index: place) by frame 24, and turning bone `turn` (name, angle) too."""
    assert ops.anim.action_new(name=name) == {'FINISHED'} and doc.action == name
    doc.frame_current = 24
    for i, to in moves.items():
        face().set_point(i, to)
    if turn:
        rig().bone_set(turn[0], angle=bone(turn[0])["setup_angle"] + turn[1])
    doc.frame_current = 25
    mainline()


def knob(name, x, y):
    rig().select_bone(name)
    rig().bone_set(name, knob=(x, y))
    settle()


def scene():
    """A head knob (Head: Right moves point 0, Up moves point 1 and turns bone arm) over a face of four points, and a
    fix following it from rest to its corner, Up and Right, where point 2 is pulled up."""
    global doc, layers, rig_id, face_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_key = True
    doc.auto_freeze_keys = False
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id
    rig().name = "Rig"
    ops.armature.bone_add(name="Head", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
    ops.armature.select_none()
    ops.armature.bone_add(name="arm", head_x="0.0", head_y="-2.0", tail_x="1.0", tail_y="-2.0")
    ops.armature.select_none()
    ops.armature.bone_add(name="Jaw", head_x="-3.0", head_y="3.0", tail_x="-2.5", tail_y="3.0")
    assert ops.layer.new() == {'FINISHED'}
    face_id = layers.active.id
    face().add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])
    assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
    layers.active = rig()
    ordinary("Head Right", {0: (2.0, 0.0)})
    ordinary("Head Up", {1: (1.0, 1.0)}, turn=("arm", 0.6))
    ordinary("Jaw Down", {3: (3.0, -1.0)})
    rig().select_bone("Head")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action="Head Right") == {'FINISHED'}
    assert ops.armature.controller_side(side="UP", action="Head Up") == {'FINISHED'}
    rig().select_bone("Jaw")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="DOWN", action="Jaw Down") == {'FINISHED'}
    doc.frame_current = 5


def corner_fix():
    """The fix from rest to Up and Right (frame 30), point 2 pulled up there and point 1 right; back on the mainline after."""
    rig().select_bone("Head")
    assert ops.armature.bone_fix_new() == {'FINISHED'}
    doc.frame_current = 30
    rig().bone_set("Head", knob=(24.0, 24.0))
    settle()
    face().set_point(2, (2.0, 0.5))
    face().set_point(1, (1.2, 1.0))
    settle()
    mainline()
    return rig().bone_fixes[0]["name"]


def at_corner():
    doc.frame_current = 5
    knob("Head", 24.0, 24.0)


# --- The side view: Up taken out of the corner fix, Right left playing, the fix's own edit kept on top ------------------
scene()
fix = corner_fix()
at_corner()
assert close(point(0), (2.0, 0.0)) and close(point(1), (1.2, 1.0)) and close(point(2), (2.0, 0.5)), "the blend"
arm_rest = bone("arm")["setup_angle"]
assert close(bone("arm")["angle"], arm_rest + 0.6)
layers.active = rig()
assert ops.armature.bone_fix_take_out(name=fix, action="Head Up") == {'FINISHED'}, wm.banner_report()
assert doc.action == "" and doc.frame_current == 5, "back where it was"
assert close(point(1), (1.2, 0.0)), ("Up's point at rest, the fix's own change kept", point(1))
assert close(bone("arm")["angle"], arm_rest), ("Up's bone turn taken out too", bone("arm")["angle"])
assert close(point(0), (2.0, 0.0)), "Right still plays"
assert close(point(2), (2.0, 0.5)), "the fix's own key stays on top"
names, index = wm.undo_history()
assert names[index] == "Take Out Action", names[index]
ops.ed.undo()
at_corner()
assert close(point(1), (1.2, 1.0)), "undone"
ops.ed.redo()
at_corner()
assert close(point(1), (1.2, 0.0)), "redone"
# In the fix, on its last pose, as you'd edit it.
assert ops.anim.action_set(name=fix) == {'FINISHED'}
doc.frame_current = 30
settle()
assert close(point(1), (1.2, 0.0)) and close(point(0), (2.0, 0.0)), (point(0), point(1))
mainline()

# --- Factor: part of it; On Selected Only: just the selected points ------------------------------------------------------
scene()
fix = corner_fix()
layers.active = rig()
assert ops.armature.bone_fix_take_out(name=fix, action="Head Up", factor="0.5") == {'FINISHED'}
at_corner()
assert close(point(1), (1.2, 0.5)), ("half taken out", point(1))
ops.ed.undo()
layers.active = face()
ops.mesh.select_none()
face().select_points([0])
layers.active = rig()
rig().select_bone("Jaw")
assert ops.armature.bone_fix_take_out(name=fix, action="Head Up", selected_mask="1") == {'CANCELLED'}, \
    "Up moves none of the selected (point 0, Jaw)"
layers.active = face()
face().select_points([1])
assert ops.armature.bone_fix_take_out(name=fix, action="Head Up", selected_mask="1") == {'FINISHED'}, \
    "from a drawing in the rig too"
at_corner()
assert close(point(1), (1.2, 0.0)), "the selected point"
assert close(bone("arm")["angle"], bone("arm")["setup_angle"] + 0.6), "arm isn't selected: Up still turns it"

# --- What it can't take out --------------------------------------------------------------------------------------------
layers.active = rig()
assert ops.armature.bone_fix_take_out(name=fix, action=fix) == {'CANCELLED'}, "itself"
assert ops.armature.bone_fix_take_out(name=fix, action="Nope") == {'CANCELLED'}
assert ops.armature.bone_fix_take_out(name="Nope", action="Head Up") == {'CANCELLED'}
assert ops.anim.action_play_set(layer=str(rig_id), name="Head Right", mute="1") == {'FINISHED'}
assert ops.armature.bone_fix_take_out(name=fix, action="Head Right") == {'CANCELLED'}, "muted: adds nothing"

# --- The jaw: with the head straight up, opening the jaw moves nothing --------------------------------------------------
scene()
knob("Head", 0.0, 24.0)
knob("Jaw", 0.0, 0.0)
rig().select_bone("Head")
rig().select_bone("Jaw", extend=True)
assert ops.armature.bone_fix_new() == {'FINISHED'}
doc.frame_current = 20
rig().bone_set("Jaw", knob=(0.0, -24.0))
settle()
mainline()
jaw_fix = rig().bone_fixes[0]["name"]
doc.frame_current = 5
knob("Head", 0.0, 24.0)
knob("Jaw", 0.0, -24.0)
assert close(point(3), (3.0, -1.0)), "the jaw opens with the head up"
layers.active = rig()
# Opened already: it stays open, on the frame it was on.
assert ops.anim.action_set(name=jaw_fix) == {'FINISHED'}
doc.frame_current = 7
assert ops.armature.bone_fix_take_out(name=jaw_fix, action="Jaw Down") == {'FINISHED'}
assert doc.action == jaw_fix and doc.frame_current == 7
doc.frame_current = 20
settle()
assert close(point(3), (3.0, 0.0)), ("in the fix, the jaw open, nothing moves", point(3))
mainline()
doc.frame_current = 5
for y in (-24.0, -12.0):
    knob("Head", 0.0, 24.0)
    knob("Jaw", 0.0, y)
    assert close(point(3), (3.0, 0.0), 0.02), ("head up: the jaw moves nothing", y, point(3))
knob("Head", 0.0, 0.0)
knob("Jaw", 0.0, -24.0)
assert close(point(3), (3.0, -1.0)), ("head at rest: the jaw opens as before", point(3))

print("bone fix take out: ok")
