"""A regular or pin bone's action bone actions in the Bone tab's Actions: a slot each way it turns (counterclockwise,
clockwise), each filled by a new action (keyed 90 degrees that way on frame 10), an action picked (named after the
bone), or a mirror of the other way; None lets go of one (renamed, its keys kept). Reach scales the bone's turn keys to
end where asked. Turns: Full Turn plays one action, a whole turn (keyed to 360 degrees), saved with the file.

Run with:  OpenAnimate --background --python tests/test_bone_turn_actions.py
"""

import math
import os
import tempfile

import oanim

ops, layers = oanim.ops, oanim.data.layers
doc = oanim.data.document
doc.frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
rig.name = "Rig"
ops.armature.bone_add(name="dial", head_x="0", head_y="0", tail_x="1", tail_y="0", parent="")
ops.armature.bone_add(name="spin", head_x="0", head_y="1", tail_x="1", tail_y="1", parent="")
ops.armature.bone_add(name="spare", head_x="0", head_y="2", tail_x="1", tail_y="2", parent="")
ops.layer.new()
face = layers.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}


def fresh():
    return next(l for l in layers.all() if l.id == rig.id)


def bone(name):
    return next(b for b in fresh().bones if b["name"] == name)


def keys(name, action):
    """The bone's turn keys in `action` as (frame, value), opening it and coming back."""
    was = doc.action
    assert ops.anim.action_set(name=action, layer=str(rig.id)) == {'FINISHED'}
    out = [(k["frame"], k["value"]) for k in fresh().keyframes('bones["%s"].angle' % name)]
    assert ops.anim.action_set(name=was, layer=str(rig.id)) == {'FINISHED'}
    return out


def actions():
    return [a["name"] for a in fresh().actions]


def mainline():
    assert ops.anim.action_set(name="", layer=str(rig.id)) == {'FINISHED'}
    doc.frame_current = 0


def close(a, b, eps=1e-4):
    return abs(a - b) < eps


layers.active = fresh()
fresh().select_bone("dial")
assert bone("dial")["turn_actions"] == ("", "") and not bone("dial")["full_turn"]

# --- New: counterclockwise keys 90 degrees on frame 10 and opens it --------------------------------------------------
assert ops.armature.bone_turn_action_new(direction="CCW") == {'FINISHED'}
assert doc.action == "dial" and doc.frame_current == 10
face_now = next(l for l in layers.all() if l.id == face.id)
face_now.location_x = 2.0
doc.frame_current = 0
mainline()
assert bone("dial")["turn_actions"] == ("dial", ""), bone("dial")["turn_actions"]
k = keys("dial", "dial")
assert [f for f, _ in k] == [0, 10] and close(k[-1][1], math.pi / 2), k

# It plays: turned 45 degrees, halfway.
doc.frame_current = 5
fresh().bone_set("dial", angle=math.pi / 4)
doc.frame_current = 6
doc.frame_current = 5
assert close(next(l for l in layers.all() if l.id == face.id).location_x, 1.0, 1e-2), "the action plays halfway"
doc.frame_current = 0

# --- Clockwise: the bone's name with " 2", turning the other way ------------------------------------------------------
assert ops.armature.bone_turn_action_new(direction="CW") == {'FINISHED'} and doc.action == "dial 2"
mainline()
assert bone("dial")["turn_actions"] == ("dial", "dial 2")
assert close(keys("dial", "dial 2")[-1][1], -math.pi / 2)
assert ops.armature.bone_turn_action_new(direction="CW") == {'CANCELLED'}, "that way is taken"

# --- Reach: the keys scaled to end there -------------------------------------------------------------------------------
assert ops.armature.bone_turn_reach(direction="CW", angle="45") == {'FINISHED'}
assert close(keys("dial", "dial 2")[-1][1], -math.pi / 4)

# --- None lets go (renamed, keys kept); picking it back names it after the bone again ---------------------------------
assert ops.armature.bone_turn_action(direction="CW", action="") == {'FINISHED'}
assert bone("dial")["turn_actions"] == ("dial", "")
assert "dial 2 (unlinked)" in actions(), actions()
assert ops.armature.bone_turn_action(direction="CCW", action="dial 2 (unlinked)") == {'CANCELLED'}, "it turns clockwise"
assert ops.armature.bone_turn_action(direction="CW", action="dial 2 (unlinked)") == {'FINISHED'}
assert bone("dial")["turn_actions"] == ("dial", "dial 2"), bone("dial")["turn_actions"]
assert close(keys("dial", "dial 2")[-1][1], -math.pi / 4), "its keys came along"

# An action not turning the bone yet: named after it, keyed 90 degrees that way on its last frame.
assert ops.armature.bone_turn_action(direction="CW", action="") == {'FINISHED'}
layers.active = fresh()
assert ops.anim.action_new(name="wave") == {'FINISHED'}
doc.frame_current = 12
next(l for l in layers.all() if l.id == face.id).location_y = 1.0
doc.frame_current = 0
mainline()
fresh().select_bone("dial")
assert ops.armature.bone_turn_action(direction="CW", action="wave") == {'FINISHED'}
assert "wave" not in actions() and bone("dial")["turn_actions"][1] == "dial 2"
k = keys("dial", "dial 2")
assert k[-1][0] == 12 and close(k[-1][1], -math.pi / 2), k

# --- Mirror: an empty way from the other ------------------------------------------------------------------------------
assert ops.armature.bone_turn_action(direction="CW", action="") == {'FINISHED'}
assert ops.armature.bone_turn_mirror(direction="CW") == {'FINISHED'}
assert bone("dial")["turn_actions"] == ("dial", "dial 2")
k = keys("dial", "dial 2")
assert close(k[-1][1], -math.pi / 2), ("turning the other way", k)

# --- Turns: Full Turn plays one action ---------------------------------------------------------------------------------
assert ops.armature.bone_turns(mode="FULL") == {'CANCELLED'}, "two actions: let go of one first"
assert ops.armature.bone_turn_action(direction="CW", action="") == {'FINISHED'}
assert ops.armature.bone_turns(mode="FULL") == {'FINISHED'}
assert bone("dial")["full_turn"] and bone("dial")["turn_actions"] == ("dial", "")
k = keys("dial", "dial")
assert close(k[-1][1], 2 * math.pi), k
assert ops.armature.bone_turns(mode="BOTH") == {'FINISHED'}
assert not bone("dial")["full_turn"] and close(keys("dial", "dial")[-1][1], math.pi / 2)

# The slot is the way it turns, whatever its name: "dial" let go, a new clockwise one takes the plain name.
assert ops.armature.bone_turn_action(direction="CCW", action="") == {'FINISHED'}
assert ops.armature.bone_turn_action_new(direction="CW") == {'FINISHED'} and doc.action == "dial"
mainline()
assert bone("dial")["turn_actions"] == ("", "dial"), bone("dial")["turn_actions"]
assert ops.armature.bone_turn_action(direction="CCW", action="dial (unlinked)") == {'FINISHED'}
assert bone("dial")["turn_actions"] == ("dial 2", "dial"), bone("dial")["turn_actions"]

# A bone with none yet: Full Turn, then New keys a whole turn on frame 36.
fresh().select_bone("spin")
assert ops.armature.bone_turns(mode="FULL") == {'FINISHED'} and bone("spin")["full_turn"]
assert ops.armature.bone_turn_action_new(direction="CCW") == {'FINISHED'} and doc.action == "spin"
mainline()
k = keys("spin", "spin")
assert [f for f, _ in k] == [0, 36] and close(k[-1][1], 2 * math.pi), k
assert bone("spin")["turn_actions"] == ("spin", "")

# Saved with the file, Full Turn too on a bone with no action yet.
fresh().select_bone("spare")
assert ops.armature.bone_turns(mode="FULL") == {'FINISHED'}
path = os.path.join(tempfile.mkdtemp(), "turns.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
rig = next(l for l in layers.all() if l.name == "Rig")
assert bone("spin")["full_turn"] and bone("spin")["turn_actions"] == ("spin", "")
assert bone("dial")["turn_actions"] == ("dial 2", "dial")
assert bone("spare")["full_turn"] and not bone("dial")["full_turn"]

print("test_bone_turn_actions: ok")
