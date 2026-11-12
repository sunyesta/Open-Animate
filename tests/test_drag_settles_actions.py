"""A bone drag draws what the frame shows once dropped, when action bone actions play from what others move: a head
controller's action moves the eye a pupil's knob looks inside (Look At in an Eye Shape), and the knob plays the pupil's
actions. Played once per update, the pupil's actions read the eye from before the update, so the blend was wrong while
dragging and snapped right on letting go (the eye file's Pupil_L as the head turn's knob was dragged).

Run with:  OpenAnimate --background --python tests/test_drag_settles_actions.py
"""

import math

import _oanim
import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
ops.wm.read_homefile()
doc.auto_key = True
doc.frame_current = 0
ops.layer.new_bone()
rig = layers.active


def bone(name):
    return next(b for b in rig.bones if b["name"] == name)


def go(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


for name, head, tail in (("head", (0, -1), (0.1, -1)), ("eye", (0, 0), (0, 0.05)), ("look", (0, 0), (0, 0.1))):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(head[0]), head_y=str(head[1]), tail_x=str(tail[0]),
                                 tail_y=str(tail[1])) == {'FINISHED'}


def drawing(points, closed):
    ops.layer.new()
    l = layers.active
    assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
    l = next(x for x in layers.all() if x.id == l.id)
    l.add_curve(points, closed=closed, fill=closed)
    return next(x for x in layers.all() if x.id == l.id)


def action(layer, name, move):
    """An action on `layer` moving every point by `move` at frame 40."""
    layers.active = layer
    assert ops.anim.action_new(name=name) == {'FINISHED'}
    doc.frame_current = 40
    for i, p in enumerate(layer.points):
        layer.set_point(i, (p[0] + move[0], p[1] + move[1]))
    go(40)
    doc.action = ""
    go(0)


white = drawing([(0.2 * math.cos(2 * math.pi * i / 32), 0.2 * math.sin(2 * math.pi * i / 32)) for i in range(32)], True)
pupil = drawing([(0.0, 0.5), (0.02, 0.5)], False)
action(white, "head_r", (-0.15, 0.0))
action(pupil, "eye_r", (1.0, 0.0))
action(pupil, "eye_l", (-1.0, 0.0))

layers.active = rig
for name, sides in (("head", (("RIGHT", "head_r"),)), ("eye", (("RIGHT", "eye_r"), ("LEFT", "eye_l")))):
    ops.armature.select_none()
    rig.select_bone(name)
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    for side, act in sides:
        assert ops.armature.controller_side(side=side, action=act) == {'FINISHED'}
rig.bone_set("eye", contain_knob=False)
assert ops.armature.constraint_add(type="LOOK_AT", bone="eye") == {'FINISHED'}
rig.bone_constraint_set("eye", 0, target="look", shape_layer=white.name, fit="CENTER")
size = bone("head")["controller_frame_size"]

doc.frame_current = 10
rig.bone_set("look", position=(5.0, 0.0))
go(10)
pts = pupil.evaluated()[0]
rest = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
assert rest[0] > 0.1, ("looking right: the pupil's knob at the eye's right edge plays eye_r", rest)
for frames in (20.0, 40.0, 10.0):
    ops.armature.select_none()
    rig.select_bone("head")
    drawn = _oanim.debug_move_bones(rig.id, [(frames * size, 0.0)] * 2, "head", pupil.id)
    go(10)
    pts = pupil.evaluated()[0]
    lands = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
    assert lands[0] < rest[0] - 0.01, ("the eye carried left pushes the pupil's knob with its edge", frames, lands, rest)
    for i, at in enumerate(drawn):
        assert math.dist(at, lands) < 1e-4, ("drawn mid-drag where it lands", frames, i, at, lands)
    assert ops.ed.undo() == {'FINISHED'}
    go(10)

print("test_drag_settles_actions: all passed")
