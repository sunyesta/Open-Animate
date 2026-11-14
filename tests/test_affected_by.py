"""Affected By: a field moved by something besides its own keys (an action bone action, a 2 Axis Controller's knob, a fix
action, a driver) shows no colour for it: green and yellow are the timeline's own keys only. Its right-click menu (and its
timeline row's) has an Affected By submenu: its own value and what it shows, then a row for each thing moving it, which
goes there when clicked; its tooltip says "Moved by 1 action bone, 1 knob".

Run with:  OpenAnimate --background --python tests/test_affected_by.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

doc.frame_current = 0
ops.layer.new_bone()
rig = layers.active
ops.armature.bone_add(name="dial", head_x="0", head_y="0", tail_x="1", tail_y="0", parent="")
ops.armature.select_none()
ops.armature.bone_add(name="stick", head_x="0", head_y="2", tail_x="1", tail_y="2", parent="")
ops.layer.new()
face = layers.active
face.add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
ops.layer.move_to_group(group=str(rig.id))
layers.active = rig


def fresh():
    return next(l for l in layers.all() if l.id == rig.id)


def face_now():
    return next(l for l in layers.all() if l.id == face.id)


def settle():
    doc.frame_current = doc.frame_current + 1
    doc.frame_current = doc.frame_current - 1


def rows(path, component=-1):
    return wm.field_affected_by(face.id, path, component)


def kinds(path):
    return [r["kind"] for r in rows(path)]


def bone(name):
    return next(b for b in fresh().bones if b["name"] == name)


# The dial's action bone action takes the face to x = 2 by frame 10.
assert ops.anim.action_new(name="dial", action_bone="1") == {'FINISHED'} and doc.action == "dial"
doc.frame_current = 10
fresh().bone_set("dial", angle=1.0)
face_now().location_x = 2.0
doc.frame_current = 0
assert ops.anim.action_set(name="") == {'FINISHED'}

# An ordinary action the stick's knob plays on its Right side: the face's first point to (1, 1) by frame 20.
assert ops.anim.action_new(name="Look Right") == {'FINISHED'} and doc.action == "Look Right"
doc.frame_current = 20
face_now().set_point(0, (1.0, 1.0))
face_now().location_y = 1.0
doc.frame_current = 21
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0
fresh().select_bone("stick")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="Look Right") == {'FINISHED'}

# --- An action bone moving a field: grey (no keys of its own), its Affected By listing the bone ------------------------
doc.frame_current = 30
fresh().bone_set("dial", angle=0.5)
settle()
assert abs(face_now().location_x - 1.0) < 1e-3, face_now().location_x
assert face_now().field_state("position")[0] == "NONE", "no keys on the mainline: no green, whatever moves it"
r = rows("position")
assert [x["kind"] for x in r] == ["OWN", "ACTION_BONE"], r
assert r[0]["name"] == "Own value 0.00, 0.00 → 1.00, 0.00", r[0]
assert r[1]["name"] == "dial" and r[1]["detail"] == "dial · 50%", r[1]
assert r[1]["layer"] == rig.id and r[1]["bone"] == "dial" and r[1]["action"] == "dial", r[1]
assert rows("position", 0)[0]["name"] == "Own value 0.00 → 1.00", "one part: its number only"
assert wm.field_affected_summary(face.id, "position") == "Moved by 1 action bone"
assert rows("opacity") == [] and wm.field_affected_summary(face.id, "opacity") == "", "the action doesn't touch it"

# Clicking the row goes to the bone: its layer active, only it selected.
layers.active = face_now()
fresh().select_bone("stick")
wm.field_affected_go(face.id, "position", 1)
assert layers.active.id == rig.id
assert bone("dial")["selected"] and not bone("stick")["selected"], [(b["name"], b["selected"]) for b in fresh().bones]
assert bone("dial")["active"], bone("dial")

# Keyed on the mainline, it is green or yellow as any field, and still lists the bone.
face_now().keyframe_insert("position")
settle()
assert face_now().field_state("position")[0] == "KEYED", face_now().field_state("position")
assert "ACTION_BONE" in kinds("position")
doc.frame_current = 31
assert face_now().field_state("position")[0] == "ANIMATED"
doc.frame_current = 30

# At rest, nothing plays: no Affected By.
fresh().bone_set("dial", angle=0.0)
settle()
assert rows("position") == [], rows("position")

# --- Inside the action being edited: its own keys are the field's, never an Affected By ---------------------------------
assert ops.anim.action_set(name="dial") == {'FINISHED'}
doc.frame_current = 10
settle()
assert face_now().field_state("position")[0] == "KEYED", "the action's key there"
assert "ACTION_BONE" not in kinds("position"), ("the action edited isn't something else moving it", rows("position"))
assert ops.anim.action_set(name="") == {'FINISHED'}

# --- A knob: its side's action, how far out ----------------------------------------------------------------------------
doc.frame_current = 30
fresh().select_bone("stick")
fresh().bone_set("stick", knob=(10.0, 0.0))
settle()
r = rows("points[0].pos")
assert [x["kind"] for x in r] == ["OWN", "KNOB"], r
assert r[1]["name"] == "stick" and r[1]["detail"] == "Look Right · 50%", r[1]
assert rows("points[1].pos") == [], ("the action holds its other points still: nothing moves them", rows("points[1].pos"))
assert wm.field_affected_summary(face.id, "points[0].pos") == "Moved by 1 knob"
fresh().select_bone("dial")
wm.field_affected_go(face.id, "points[0].pos", 1)
assert bone("stick")["active"] and bone("stick")["selected"] and not bone("dial")["selected"]

# The dial and the knob both move the face: both listed, in the order they play.
fresh().bone_set("dial", angle=0.5)
settle()
assert kinds("position") == ["OWN", "ACTION_BONE", "KNOB"], rows("position")
assert wm.field_affected_summary(face.id, "position") == "Moved by 1 action bone, 1 knob"
# Editing the dial's action, the knob moved in it plays under it: listed, the action edited not.
assert ops.anim.action_set(name="dial") == {'FINISHED'}
doc.frame_current = 5
fresh().select_bone("stick")
fresh().bone_set("stick", knob=(10.0, 0.0))
settle()
assert kinds("position") == ["OWN", "KNOB"], ("only what plays under the action edited", rows("position"))
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 30
fresh().bone_set("dial", angle=0.0)
settle()

# Muted, it plays nothing, and nothing is listed.
assert ops.anim.action_play_set(layer=str(rig.id), name="Look Right", mute="1") == {'FINISHED'}
settle()
assert rows("points[0].pos") == [], rows("points[0].pos")
assert ops.anim.action_play_set(layer=str(rig.id), name="Look Right", mute="0") == {'FINISHED'}
settle()

# --- A driver: its own row, after what the actions do -----------------------------------------------------------------
assert ops.anim.driver_add(layer=str(face.id), path="opacity", expression="0.5") == {'FINISHED'}
settle()
r = rows("opacity")
assert r == [{"kind": "DRIVER", "name": "Driver", "detail": "0.5", "layer": face.id, "bone": "", "action": ""}], r
assert wm.field_affected_summary(face.id, "opacity") == "Moved by 1 driver"

# --- A fix action following the knob: its strength ---------------------------------------------------------------------
# Up as well, then a fix where the knob is up and right: the face's last point lifted.
assert ops.anim.action_new(name="Look Up") == {'FINISHED'} and doc.action == "Look Up"
doc.frame_current = 20
face_now().set_point(1, (1.0, 1.0))
doc.frame_current = 21
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0
fresh().select_bone("stick")
assert ops.armature.controller_side(side="UP", action="Look Up") == {'FINISHED'}
doc.frame_current = 30
fresh().bone_set("stick", knob=(0.0, 20.0))
settle()
fresh().select_bone("stick")
assert ops.armature.bone_fix_new() == {'FINISHED'}
fix = doc.action
doc.frame_current = 30
fresh().bone_set("stick", knob=(20.0, 20.0))
settle()
face_now().set_point(2, (2.0, 0.5))
settle()
assert ops.anim.action_set(name="") == {'FINISHED'}
fix = fresh().bone_fixes[0]["name"]
doc.frame_current = 30
fresh().bone_set("stick", knob=(20.0, 20.0))
settle()
r = rows("points[2].pos")
assert [x["kind"] for x in r] == ["OWN", "FIX"], ("the sides hold this point still: only the fix moves it", r)
assert r[1]["name"] == fix and r[1]["detail"] == "fix · 100%", r[1]
fresh().bone_set("stick", knob=(20.0, 10.0))
settle()
assert rows("points[2].pos")[1]["detail"] == "fix · 50%", rows("points[2].pos")
assert wm.field_affected_summary(face.id, "points[2].pos") == "Moved by 1 fix"
fresh().select_bone("dial")
wm.field_affected_go(face.id, "points[2].pos", 1)
assert bone("stick")["active"] and bone("stick")["selected"] and not bone("dial")["selected"], "the fix's bone"

# --- How drivers show: a knob is no link; a 2-Way Link's driven side is purple, both sides carry the link icon ---------
assert wm.field_driver_look(rig.id, 'bones["stick"].position') == ("NONE", False), \
    ("a knob plays its sides' actions: nothing links it", wm.field_driver_look(rig.id, 'bones["stick"].position'))
assert wm.field_driver_look(face.id, "opacity") == ("DRIVEN", False), "an ordinary driver: purple, no link icon"
doc.frame_current = 0
ops.layer.new()
lid = layers.active
var = '[{"name": "d", "layer": %d, "path": "rotation", "component": -1}]' % face.id
assert ops.anim.driver_add(layer=str(lid.id), path="rotation", vars=var, expression="-d * 0.5") == {'FINISHED'}
assert ops.anim.driver_two_way(layer=str(lid.id), path="rotation") == {'FINISHED'}
assert wm.field_driver_look(lid.id, "rotation") == ("DRIVEN", True), wm.field_driver_look(lid.id, "rotation")
assert wm.field_driver_look(face.id, "rotation") == ("NONE", True), "the side read: its own colours, the link icon"
r = wm.field_affected_by(lid.id, "rotation")
assert [x["kind"] for x in r] == ["DRIVER"] and r[0]["detail"].startswith("2-Way Linked with "), r
assert wm.field_affected_by(face.id, "rotation") == [], "the side read is moved by nothing"

print("affected by: ok")
