"""A 2 Axis Controller's knob at its box's edge plays its side's last frame, Step keys there too: a blink that hides the
eye white on its last frame hides it with the knob all the way down. The knob's place goes through its timing keys,
whose sums can land a hair short of a whole frame (the knob at -2.4705722 played 13.99999 of 14), and a Step key waits
for its frame, so the eye white stayed (from the practice file's Eye_Blink_L.001).

Run with:  OpenAnimate --background --python tests/test_controller_step_end.py
"""

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
doc.auto_key = True
doc.auto_freeze_keys = False

ops.layer.new_bone()
rig = layers.active
ops.armature.bone_add(name="blink", head_x="3.0", head_y="3.0", tail_x="3.0", tail_y="3.5")
ops.layer.new()
lid = layers.active
lid.name = "Lid"
lid.add_curve([(0.0, 1.0), (1.0, 1.0)])
ops.layer.move_to_group(group=str(rig.id))
ops.layer.new()
white = layers.active
white.name = "White"
white.add_curve([(0.0, 0.0), (1.0, 0.0), (0.5, 0.5)], closed=True)
ops.layer.move_to_group(group=str(rig.id))
lid = next(l for l in layers.all() if l.name == "Lid")
white = next(l for l in layers.all() if l.name == "White")
layers.active = rig
rig.select_bone("blink")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}


def bone():
    return next(b for b in rig.bones if b["name"] == "blink")


# The Down side: the lid comes down by 7, shut on 14, where the white hides and the knob is keyed to its timing (in
# the action once it is the side's).
assert ops.anim.action_new(name="blink Down") == {'FINISHED'}
doc.frame_current = 7
lid.set_point(0, (0.0, 0.5))
doc.frame_current = 14
lid.set_point(0, (0.0, 0.0))
white.visible = False
assert ops.anim.keyframe_toggle(layer=str(white.id), paths="visible") == {'FINISHED'}
doc.frame_current = 15
doc.action = ""
doc.frame_current = 0
layers.active = rig
rig.select_bone("blink")
assert ops.armature.controller_side(side="DOWN", action="blink Down") == {'FINISHED'}
doc.action = "blink Down"
doc.frame_current = 14
layers.active = rig
rig.select_bone("blink")
rig.bone_set("blink", knob=(0.0, -2.4705722332000732))
doc.frame_current = 15
doc.action = ""
doc.frame_current = 0
low = bone()["controller_box"][0][1]
assert abs(low + 2.4705722) < 1e-5, bone()["controller_box"]

# On the mainline: the knob pulled down past the box (held at its edge) on 10, back up on 20.
for frame, y in ((10, -10.0), (20, 0.0)):
    doc.frame_current = frame
    rig.bone_set("blink", knob=(0.0, y))
for frame in (10,):
    doc.frame_current = frame + 1
    doc.frame_current = frame
    played = {name: t for name, t, share in rig.action_bone_actions_playing}
    assert abs(played["blink Down"] - 14.0) < 1e-3, played
    assert not white.visible, ("the white hides with the knob all the way down", frame, played)
    assert abs(lid.shown()[0][0][1]) < 1e-4, lid.shown()[0]
doc.frame_current = 20
assert white.visible, "and shows again with the knob back up"

print("Controller step end tests passed")
