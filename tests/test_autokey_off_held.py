"""With Auto Keying off, an edit to an unkeyed value lands where it was put when an action bone action holds that value
still (keyed in the action with no change, as Key Whole Drawing leaves most points and a pose key most bones), as it
already did where the action moves it: the action blends from the setup either way. Only the moved ones got the
setup's extra share, so on the eye rig Head_X, G by (0.03, 0.02) half way through the head turn, landed a tenth of
the way, and the wrong way further on.

Run with:  OpenAnimate --background --python tests/test_autokey_off_held.py
"""

import math

import _oanim
import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers


def rig_scene():
    """A knob whose Right action moves bone C and holds bone B where it is, played half way."""
    ops.wm.read_homefile()
    doc.auto_key = True
    doc.frame_current = 0
    ops.layer.new_bone()
    rid = layers.active.id
    rig = lambda: next(l for l in layers.all() if l.id == rid)
    for name, head, tail in (("Knob", (3, 3), (3.5, 3)), ("B", (0, 0), (0.5, 0)), ("C", (1, 0), (1.5, 0))):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(head[0]), head_y=str(head[1]), tail_x=str(tail[0]),
                                     tail_y=str(tail[1])) == {'FINISHED'}
    ops.armature.select_none()
    assert ops.anim.action_new(name="Knob Right") == {'FINISHED'}
    doc.frame_current = 24
    rig().bone_set("C", position=(1.0, 1.0))
    rig().bone_set("B", position=(0.0, 0.0))
    rig().keyframe_insert('bones["B"].position', 24)
    doc.frame_current = 25
    assert ops.anim.action_set(name="") == {'FINISHED'}
    doc.frame_current = 0
    rig().select_bone("Knob")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action="Knob Right") == {'FINISHED'}
    doc.frame_current = 10
    rig().bone_set("Knob", contain_knob=False)
    rig().bone_set("Knob", knob=(12.0, 0.0))
    doc.frame_current = 11
    doc.frame_current = 10
    doc.auto_key = False
    doc.frame_current = 11
    doc.frame_current = 10
    ops.armature.select_none()
    rig().select_bone("B")
    return rig


def head(rig, name):
    return tuple(next(b for b in rig().bones if b["name"] == name)["head"])


# --- G on a bone the action holds still lands where it was put
rig = rig_scene()
at = head(rig, "B")
assert ops.armature.translate(move_x="0.1", move_y="-0.2") == {'FINISHED'}
now = head(rig, "B")
assert math.dist(now, (at[0] + 0.1, at[1] - 0.2)) < 1e-4, ("held bone: G landed short", at, now)
doc.frame_current = 11
doc.frame_current = 10
assert math.dist(head(rig, "B"), now) < 1e-4, ("held bone: stays put on coming back", now, head(rig, "B"))

# --- A drag of a bone the action holds still lands where it was dropped
rig = rig_scene()
at = head(rig, "B")
_oanim.debug_move_bones(rig().id, [(0.05, -0.1), (0.1, -0.2)], "B")
doc.frame_current = 11
doc.frame_current = 10
now = head(rig, "B")
assert math.dist(now, (at[0] + 0.1, at[1] - 0.2)) < 1e-4, ("held bone: a drag landed short", at, now)

# --- G on a point the action holds still (Key Whole Drawing keyed it) lands where it was put
ops.wm.read_homefile()
doc.auto_key = True
ops.layer.new_bone()
rid = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rid)
assert ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0") == {'FINISHED'}
ops.armature.select_none()
ops.layer.new()
fid = layers.active.id
face = lambda: next(l for l in layers.all() if l.id == fid)
face().add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
assert ops.layer.move_to_group(group=str(rid)) == {'FINISHED'}
assert face().key_whole_drawing
layers.active = rig()
assert ops.anim.action_new(name="Knob Right") == {'FINISHED'}
doc.frame_current = 24
face().set_point(1, (1.0, 1.0))
doc.frame_current = 25
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0
rig().select_bone("Knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="Knob Right") == {'FINISHED'}
doc.frame_current = 10
rig().bone_set("Knob", knob=(12.0, 0.0))
doc.frame_current = 11
doc.frame_current = 10
assert 0.3 < face().shown()[0][1][1] < 0.7, ("half the action plays", face().shown()[0][1])
doc.auto_key = False
doc.frame_current = 11
doc.frame_current = 10
layers.active = face()
ops.mesh.select_none()
at = face().shown()[0][2]
face().select_points([2])
assert ops.mesh.translate(move_x="0.1", move_y="-0.2") == {'FINISHED'}
now = face().shown()[0][2]
assert math.dist(now, (at[0] + 0.1, at[1] - 0.2)) < 1e-4, ("held point: G landed short", at, now)
moved = face().shown()[0][1]
assert 0.3 < moved[1] < 0.7, ("the point the action moves is left as it was", moved)

print("test_autokey_off_held: all passed")
