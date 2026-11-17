"""Duplicating and copying bones with or without their keys. Shift D's Keyframes (off by default, shown in Adjust Last
Operation): on, the copies keep the originals' keys, on the mainline and in every action; off, they have none and rest
in their setup pose. Copy Bones and Paste Bones (Ctrl C and Ctrl V over the viewport on the setup frame): the picked
bones pasted into the active bone layer, here or in another file, taken names numbered, each whose parent wasn't copied
hung from a bone of that name if there is one; Paste's Keyframes (off by default) brings their mainline keys and their
keys in the actions that bone layer has.

Run with:  OpenAnimate --background --python tests/test_bone_duplicate_keys.py
"""

import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def scene():
    """A bone layer with Arm (upright, off the origin, so a child's place in it differs from its place in the layer)
    and its child Hand. Hand is turned 0.5 on frame 10 of the mainline and 0.3 on frame 5 of
    the action Wave. Back on frame 0 with Hand picked."""
    global doc, layers, rig
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    rig.name = "Rig"
    assert ops.armature.bone_add(name="Arm", head_x="0.5", head_y="0.5", tail_x="0.5", tail_y="1.5", parent="") == {'FINISHED'}
    assert ops.armature.bone_add(name="Hand", head_x="1", head_y="0", tail_x="1.5", tail_y="0.5",
                                 parent="Arm") == {'FINISHED'}
    doc.auto_key = True
    doc.frame_current = 10
    rig.bone_set("Hand", angle=bone("Hand")["setup_angle"] + 0.5)
    doc.frame_current = 0
    assert ops.anim.action_new(name="Wave") == {'FINISHED'}
    doc.frame_current = 5
    rig.bone_set("Hand", angle=bone("Hand")["setup_angle"] + 0.3)
    doc.frame_current = 0
    assert ops.anim.action_set(name="") == {'FINISHED'}
    layers.active = rig
    ops.armature.select_none()
    rig.select_bone("Hand")


def bone(name, layer=None):
    return next(b for b in (layer or rig).bones if b["name"] == name)


def turn(name, frame, layer=None):
    """How far a bone is turned from its setup pose on a frame of the mainline."""
    doc.frame_current = frame
    b = bone(name, layer)
    doc.frame_current = 0
    return b["angle"] - b["setup_angle"]


def turn_in(action, name, frame, layer=None):
    """The same in an action."""
    layers.active = layer or rig
    assert ops.anim.action_set(name=action) == {'FINISHED'}
    t = turn(name, frame, layer)
    assert ops.anim.action_set(name="") == {'FINISHED'}
    return t


def said():
    r = wm.banner_report()
    return r[2] + " " + r[3]


def last_step():
    names, index = wm.undo_history()
    return names[index]


# --- Shift D: off by default, the copy has no keys and rests in its setup pose ---------------------------------------
scene()
assert ops.armature.duplicate_move(move_x="0.5", move_y="0") == {'FINISHED'}
assert last_step() == "Duplicate Bones", last_step()
op = wm.last_operation()
assert op and op[0] == "armature.duplicate_move" and op[1].get("keyframes") == "0", op
copy = [b for b in rig.bones if b["selected"]]
assert [b["name"] for b in copy] == ["Hand.001"], copy
assert close(bone("Hand.001")["head"], (1.5, 0.0)), bone("Hand.001")["head"]
assert abs(turn("Hand.001", 10)) < 1e-4, "no mainline keys"
assert abs(turn_in("Wave", "Hand.001", 5)) < 1e-4, "no keys in the action"
assert abs(turn("Hand", 10) - 0.5) < 1e-4 and abs(turn_in("Wave", "Hand", 5) - 0.3) < 1e-4, "the original keeps its"

# --- Keyframes in Adjust Last Operation: turned on there, the copy gets its keys --------------------------------------
scene()
# The pick in an undo step, as a click's is (the panel's redo undoes back to it).
ops.armature.select_none()
rig.select_bone("Arm")
assert ops.armature.select_invert() == {'FINISHED'}
assert [b["name"] for b in rig.bones if b["selected"]] == ["Hand"]
assert ops.armature.duplicate_move(move_x="0.5", move_y="0") == {'FINISHED'}
assert wm.redo_last(keyframes="1") == "FINISHED"
assert [b["name"] for b in rig.bones] == ["Arm", "Hand", "Hand.001"], [b["name"] for b in rig.bones]
assert close(bone("Hand.001")["head"], (1.5, 0.0)), bone("Hand.001")["head"]
assert abs(turn("Hand.001", 10) - 0.5) < 1e-4

# --- Keyframes on: the copy keeps them, on the mainline and in every action --------------------------------------------
scene()
assert ops.armature.duplicate_move(keyframes="1", move_x="0", move_y="0.5") == {'FINISHED'}
assert last_step() == "Duplicate Bones", last_step()
ops.ed.undo()
assert not any(b["name"] == "Hand.001" for b in rig.bones), "one undo step"
ops.ed.redo()
assert close(bone("Hand.001")["head"], (1.0, 0.5)), bone("Hand.001")["head"]
assert abs(turn("Hand.001", 10) - 0.5) < 1e-4
assert abs(turn_in("Wave", "Hand.001", 5) - 0.3) < 1e-4

# --- The same through Shift D and a move: one step, and Keyframes kept by the confirm ---------------------------------
scene()
assert wm.event_simulate("D", shift=True, area="Viewport")
wm.event_simulate("RET", area="Viewport")
assert last_step() == "Duplicate Bones", last_step()
op = wm.last_operation()
assert op and op[0] == "armature.duplicate_move" and op[1].get("keyframes") == "0", op
assert any(b["name"] == "Hand.001" for b in rig.bones)
assert abs(turn("Hand.001", 10)) < 1e-4

# --- Ctrl C and Ctrl V on frame 0: the bones pasted, numbered, keys left off by default --------------------------------
scene()
assert wm.event_simulate("C", ctrl=True, area="Viewport")
assert "Copied 1 bone" in said(), said()
assert wm.event_simulate("V", ctrl=True, area="Viewport")
assert last_step() == "Paste Bones", last_step()
op = wm.last_operation()
assert op and op[0] == "armature.paste" and op[1].get("keyframes") == "0", op
pasted = bone("Hand.001")
assert pasted["selected"] and not bone("Hand")["selected"]
assert pasted["parent"] == "Arm", pasted["parent"]
assert close(pasted["head"], bone("Hand")["head"]) and close(pasted["tail"], bone("Hand")["tail"])
ops.ed.undo()
assert not any(b["name"] == "Hand.001" for b in rig.bones)
ops.ed.redo()
assert abs(turn("Hand.001", 10)) < 1e-4 and abs(turn_in("Wave", "Hand.001", 5)) < 1e-4

# --- Paste's Keyframes on: mainline keys and keys in this bone layer's actions -----------------------------------------
scene()
assert ops.armature.copy() == {'FINISHED'}
assert ops.armature.paste(keyframes="1") == {'FINISHED'}
assert abs(turn("Hand.001", 10) - 0.5) < 1e-4
assert abs(turn_in("Wave", "Hand.001", 5) - 0.3) < 1e-4

# --- Arm and Hand together into another bone layer: Hand stays under the copied Arm -----------------------------------
scene()
ops.armature.select_none()
rig.select_bone("Arm")
rig.select_bone("Hand", extend=True)
assert ops.armature.copy() == {'FINISHED'}
assert ops.layer.new_bone() == {'FINISHED'}
other = layers.active
assert ops.armature.paste() == {'FINISHED'}
assert sorted(b["name"] for b in other.bones) == ["Arm", "Hand"], [b["name"] for b in other.bones]
assert bone("Hand", other)["parent"] == "Arm"
assert close(bone("Hand", other)["head"], bone("Hand")["head"]) and close(bone("Hand", other)["tail"], bone("Hand")["tail"])

# --- Hand alone into a bone layer with its own Arm elsewhere: hung from that Arm, resting where it did; with Keyframes,
# the mainline keys come and the action this bone layer doesn't have doesn't -----------------------------------------
scene()
want_head, want_tail = bone("Hand")["head"], bone("Hand")["tail"]
assert ops.armature.copy() == {'FINISHED'}
assert ops.layer.new_bone() == {'FINISHED'}
other = layers.active
assert ops.armature.bone_add(name="Arm", head_x="0", head_y="2", tail_x="0", tail_y="3", parent="") == {'FINISHED'}
assert ops.armature.paste(keyframes="1") == {'FINISHED'}
hand = bone("Hand", other)
assert hand["parent"] == "Arm", hand["parent"]
assert close(hand["head"], want_head) and close(hand["tail"], want_tail), (hand["head"], hand["tail"])
assert abs(turn("Hand", 10, other) - 0.5) < 1e-4
assert "Wave" not in [a["name"] for a in other.actions]
# (Nor do its keys wait there for an action of that name made later.)
layers.active = other
assert ops.anim.action_new(name="Wave") == {'FINISHED'}
assert ops.anim.action_set(name="") == {'FINISHED'}
assert abs(turn_in("Wave", "Hand", 5, other)) < 1e-4, "no keys left from the other bone layer's Wave"
doc.frame_current = 0
# Its parent moved, the pasted Hand moves with it.
other.bone_set("Arm", position=(1.0, 2.0))
assert close(bone("Hand", other)["head"], (want_head[0] + 1.0, want_head[1])), bone("Hand", other)["head"]

# --- With no bone of its parent's name, a root resting where it did ---------------------------------------------------
scene()
want_head = bone("Hand")["head"]
assert ops.armature.copy() == {'FINISHED'}
assert ops.layer.new_bone() == {'FINISHED'}
other = layers.active
assert ops.armature.paste() == {'FINISHED'}
assert bone("Hand", other)["parent"] in ("", None), bone("Hand", other)["parent"]
assert close(bone("Hand", other)["head"], want_head)

# --- Into another file -----------------------------------------------------------------------------------------------
scene()
assert ops.armature.copy() == {'FINISHED'}
assert ops.wm.read_homefile() == {'FINISHED'}
doc, layers = oanim.data.document, oanim.data.layers
doc.frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
assert ops.armature.paste() == {'FINISHED'}
assert [b["name"] for b in layers.active.bones] == ["Hand"]

# --- With points picked too, the shapes come along: Ctrl V with the drawing active pastes them, with the bone layer
# active the bones -------------------------------------------------------------------------------------------------
scene()
assert ops.layer.new() == {'FINISHED'}
art = layers.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
art.add_curve([(0.2, 0.1), (0.4, 0.3), (0.1, 0.5)])
art.select_points([0, 1, 2])
art.selected = True
layers.active = rig
rig.select_bone("Hand")
assert ops.armature.copy() == {'FINISHED'}
layers.active = art
curves = len(art.shown()[1])
assert not ops.armature.paste.poll(), "a drawing active: the shapes'"
assert wm.event_simulate("V", ctrl=True, area="Viewport")
assert last_step() == "Paste Shapes", last_step()
assert len(art.shown()[1]) == curves + 1
layers.active = rig
assert wm.event_simulate("V", ctrl=True, area="Viewport")
assert last_step() == "Paste Bones", last_step()

# --- Off the setup frame Ctrl C and Ctrl V stay Copy Pose and Paste Pose ---------------------------------------------
scene()
doc.frame_current = 10
assert not ops.armature.copy.poll()
assert wm.event_simulate("C", ctrl=True, area="Viewport")
assert "pose" in said(), said()

print("test_bone_duplicate_keys: OK")
