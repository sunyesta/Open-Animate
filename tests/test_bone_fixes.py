"""Fix actions that follow bones (the Bone tab's Fix Actions): Create Fix Action on the selected bones (2 ways or more: a
2 Axis Controller's knob goes 2) makes an action keyed on frame 1 where they are now and opens it. Their keys in it are
its line, from frame 1 to the last frame they are keyed on; its other keys the fix along it. On the mainline it plays by
itself: the frame whose pose the bones are nearest along what changes on the line, as much as what stays put is there.
Named after the actions playing where it ends, until renamed by hand; saved with the file.

Run with:  OpenAnimate --background --python tests/test_bone_fixes.py
"""

import os
import tempfile

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
doc.auto_key = True

ops.layer.new_bone()
rig = layers.active
rig.name = "Rig"
ops.armature.bone_add(name="Bone", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
ops.armature.select_none()
ops.armature.bone_add(name="arm", head_x="0.0", head_y="-2.0", tail_x="1.0", tail_y="-2.0")
ops.layer.new()
face = layers.active
face.add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
ops.layer.move_to_group(group=str(rig.id))
layers.active = rig


def fresh():
    return next(l for l in layers.all() if l.id == rig.id)


def face_now():
    return next(l for l in layers.all() if l.id == face.id)


def point(i):
    return tuple(face_now().shown()[0][i])


def close(a, b, eps=1e-3):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    return abs(a - b) < eps


def mainline():
    assert ops.anim.action_set(name="") in ({'FINISHED'}, {'CANCELLED'})
    doc.frame_current = 0


def settle():
    doc.frame_current = doc.frame_current + 1
    doc.frame_current = doc.frame_current - 1


def ordinary(name, i, moved):
    """An action taking the face's point `i` to `moved` by frame 24."""
    assert ops.anim.action_new(name=name) == {'FINISHED'} and doc.action == name
    doc.frame_current = 24
    face_now().set_point(i, moved)
    doc.frame_current = 25
    mainline()


def fixes():
    return fresh().bone_fixes


def knob(x, y, frame=5):
    """The knob there on the mainline, on `frame`."""
    doc.frame_current = frame
    fresh().select_bone("Bone")
    fresh().bone_set("Bone", knob=(x, y))
    settle()


ordinary("Bone Right", 0, (2.0, 0.0))
ordinary("Bone Up", 1, (1.0, 1.0))
fresh().select_bone("Bone")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="Bone Right") == {'FINISHED'}
assert ops.armature.controller_side(side="UP", action="Bone Up") == {'FINISHED'}

# --- It needs 2 ways to follow ------------------------------------------------------------------------------------------
assert ops.armature.bone_fix_new(bones="arm") == {'CANCELLED'}, "one bone turning goes one way"
assert fixes() == []

# --- Create: keyed on frame 1 where the knob is now, opened there --------------------------------------------------------
knob(0.0, 24.0)
assert close(point(1), (1.0, 1.0)), "Up plays on the mainline"
fresh().select_bone("Bone")
assert ops.armature.bone_fix_new() == {'FINISHED'}, "a controller alone goes 2 ways"
made = doc.action
assert made == "Bone Up 2", ("named after Up, which plays where it starts", made)
assert doc.frame_current == 1
assert [f["name"] for f in fixes()] == [made] and fixes()[0]["follows"] == ["Bone"]
assert any(a["name"] == made and a["kind"] == "FIX" for a in fresh().actions)
bone = next(b for b in fresh().bones if b["name"] == "Bone")
assert close(bone["knob"], (0.0, 24.0)), ("the knob where it was on the mainline", bone["knob"])
assert close(point(1), (1.0, 1.0)), "Up plays under it from the knob"

# Where it ends: Up and Right, and the fix there.
doc.frame_current = 30
fresh().bone_set("Bone", knob=(24.0, 24.0))
settle()
assert close(point(0), (2.0, 0.0)) and close(point(1), (1.0, 1.0)), "both sides play under it"
face_now().set_point(2, (2.0, 0.5))
settle()
assert close(point(2), (2.0, 0.5))
assert fixes()[0]["end"] == 30.0, fixes()

# --- Back on the mainline: named after where it ends ---------------------------------------------------------------------
mainline()
name = "Bone Up and Right"
assert [f["name"] for f in fixes()] == [name], fixes()
assert ops.armature.bone_fix_new(bones="Bone") == {'FINISHED'} and doc.action == "Bone Fix", "at rest: its bone's name"
assert ops.anim.action_delete(name="Bone Fix") == {'FINISHED'}
mainline()

# --- It plays by itself: along the line, as much as Up is there ---------------------------------------------------------
knob(24.0, 24.0)
assert close(point(2), (2.0, 0.5)), ("the whole fix where it ends", point(2))
f = fixes()[0]
assert close(f["frame"], 30.0) and close(f["strength"], 1.0), f
knob(12.0, 24.0)
f = fixes()[0]
assert 10.0 < f["frame"] < 22.0 and close(f["strength"], 1.0), ("partway along the line (its keys ease)", f)
assert 0.05 < point(2)[1] < 0.45, ("part of the way", point(2))
knob(24.0, 12.0)
f = fixes()[0]
assert close(f["frame"], 30.0) and close(f["strength"], 0.5), ("half of Up: half the fix", f)
assert close(point(2), (2.0, 0.25)), point(2)
knob(24.0, 0.0)
assert fixes()[0]["strength"] == 0.0 and close(point(2), (2.0, 0.0)), "no Up, no fix"
knob(0.0, 24.0)
assert close(fixes()[0]["frame"], 1.0) and close(point(2), (2.0, 0.0)), ("where it starts it adds nothing", fixes(), point(2))

# Muted, it doesn't play.
knob(24.0, 24.0)
assert ops.anim.action_play_set(name=name, mute="1") == {'FINISHED'}
settle()
assert close(point(2), (2.0, 0.0))
assert ops.anim.action_play_set(name=name, mute="0") == {'FINISHED'}
settle()
assert close(point(2), (2.0, 0.5))
assert ops.anim.action_play_set(name=name, frame="3") == {'CANCELLED'}, "its bones say its frame"

# --- What it follows ---------------------------------------------------------------------------------------------------
assert ops.armature.bone_fix_follow(name=name, bones="arm") == {'FINISHED'}
assert fixes()[0]["follows"] == ["Bone", "arm"]
assert ops.armature.bone_fix_follow(name=name, bones="arm") == {'CANCELLED'}, "it follows it already"
assert close(point(2), (2.0, 0.5)), "arm stays put at rest: nothing changes"
assert ops.armature.bone_fix_follow(name=name, bones="arm", follow="0") == {'FINISHED'}
assert ops.armature.bone_fix_follow(name=name, bones="Bone", follow="0") == {'CANCELLED'}, "it follows one at least"
assert fixes()[0]["follows"] == ["Bone"]

# --- Renamed by hand, it keeps its name ----------------------------------------------------------------------------------
assert ops.anim.action_rename(name=name, to="Look Fix") == {'FINISHED'}
assert fixes()[0]["name"] == "Look Fix" and not fixes()[0]["auto_name"]
assert ops.anim.action_set(name="Look Fix", layer=str(rig.id)) == {'FINISHED'}
mainline()
assert fixes()[0]["name"] == "Look Fix"

# --- Saved with the file ------------------------------------------------------------------------------------------------
path = os.path.join(tempfile.mkdtemp(), "bone_fixes.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
rig = next(l for l in layers.all() if l.name == "Rig")
face = next(l for l in layers.all() if l.type == "VECTOR")
f = fixes()[0]
assert f["name"] == "Look Fix" and f["follows"] == ["Bone"] and not f["auto_name"] and f["end"] == 30.0, f
doc.frame_current = 5
settle()
assert close(point(2), (2.0, 0.5)), "it plays as before"

# --- Deleted with its action; undo brings it back -----------------------------------------------------------------------
assert ops.anim.action_delete(name="Look Fix", layer=str(rig.id)) == {'FINISHED'}
assert fixes() == []
ops.ed.undo()
assert [f["name"] for f in fixes()] == ["Look Fix"]

# --- A knob linked to dials: their actions play under the fix as it is edited -------------------------------------------
# (A head turn: the sides are the actions of bones turned by the knob. Inside other actions the link is off.)
mainline()
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
rig.name = "Head"
ops.armature.bone_add(name="turn", head_x="5.0", head_y="1.0", tail_x="6.0", tail_y="1.0")
ops.armature.select_none()
ops.armature.bone_add(name="up", head_x="5.0", head_y="2.0", tail_x="6.0", tail_y="2.0")
ops.armature.select_none()
ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
for n in ("turn", "up"):
    fresh().bone_set(n, strength=0.0)
ops.layer.new()
face = layers.active
face.add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
ops.layer.move_to_group(group=str(rig.id))
layers.active = fresh()


def dial_action(name, i, moved):
    """Action bone action `name`: its bone turns a quarter by frame 20, taking the face's point `i` to `moved`."""
    fresh().select_bone(name)
    assert ops.anim.action_new(name=name, action_bone="1") == {'FINISHED'} and doc.action == name
    doc.frame_current = 20
    b = next(b for b in fresh().bones if b["name"] == name)
    fresh().bone_set(name, angle=b["setup_angle"] + 1.5708)
    face_now().set_point(i, moved)
    doc.frame_current = 21
    mainline()


dial_action("turn", 0, (2.0, 0.0))
dial_action("up", 1, (1.0, 1.0))
fresh().select_bone("Knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="turn") == {'FINISHED'}
assert ops.armature.controller_side(side="UP", action="up") == {'FINISHED'}
knob = lambda x, y, frame=5: (setattr(doc, "frame_current", frame), fresh().select_bone("Knob"),
                              fresh().bone_set("Knob", knob=(x, y)), settle())
knob(0.0, 20.0)
assert close(point(1), (1.0, 1.0)), "up plays from the knob on the mainline"
fresh().select_bone("Knob")
assert ops.armature.bone_fix_new() == {'FINISHED'} and doc.frame_current == 1
assert close(point(1), (1.0, 1.0)), ("the knob turns its dial in the fix, up playing", point(1))
doc.frame_current = 30
fresh().bone_set("Knob", knob=(20.0, 20.0))
settle()
assert close(point(0), (2.0, 0.0)) and close(point(1), (1.0, 1.0)), ("both play under the fix", point(0), point(1))
face_now().set_point(2, (2.0, 0.5))
settle()
assert close(point(2), (2.0, 0.5))
mainline()
assert [f["name"] for f in fixes()] == ["up and turn"], fixes()
knob(20.0, 20.0)
assert close(point(0), (2.0, 0.0)) and close(point(2), (2.0, 0.5)), ("it plays on the mainline", point(2))

print("test_bone_fixes: ok")
