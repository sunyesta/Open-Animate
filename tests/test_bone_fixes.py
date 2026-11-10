"""Fix actions that follow bones (the Bone tab's Fix Actions): Create Fix Action on the selected bones (2 ways or more: a
2 Axis Controller's knob goes 2) makes an action keyed on frame 1 where they are now and opens it. Their keys in it are
its line, from frame 1 to the last frame they are keyed on; its other keys the fix along it. On the mainline it plays by
itself: the frame whose pose the bones are nearest along what changes on the line, as much as what stays put is there.
Named after the actions playing where it ends, until renamed by hand; saved with the file.

Run with:  OpenAnimate --background --python tests/test_bone_fixes.py
"""

import os
import tempfile
import zipfile

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

# --- Smooth fade: easing in and out as Up goes ---------------------------------------------------------------------------
assert fixes()[0]["fade"] == "LINEAR"
knob(24.0, 6.0)
assert close(fixes()[0]["strength"], 0.25), fixes()
assert ops.armature.bone_fix_set(name=name, fade="SMOOTH") == {'FINISHED'}
assert ops.armature.bone_fix_set(name=name, fade="SMOOTH") == {'CANCELLED'}, "it is that already"
assert ops.armature.bone_fix_set(name=name, fade="SIDEWAYS") == {'CANCELLED'}
assert ops.armature.bone_fix_set(name="Nothing", fade="LINEAR") == {'CANCELLED'}
assert fixes()[0]["fade"] == "SMOOTH"
assert close(fixes()[0]["strength"], 0.25 * 0.25 * (3 - 0.5)), ("a quarter of Up: less than a quarter", fixes())
assert close(point(2), (2.0, 0.5 * 0.15625)), point(2)
knob(24.0, 12.0)
assert close(fixes()[0]["strength"], 0.5), "the same halfway"
knob(24.0, 18.0)
assert close(fixes()[0]["strength"], 0.75 * 0.75 * (3 - 1.5)), "three quarters: more"
ops.ed.undo()
assert fixes()[0]["fade"] == "LINEAR", "undone"
ops.ed.redo()
assert fixes()[0]["fade"] == "SMOOTH"

# --- Its line in the knob's box, a dot where it plays --------------------------------------------------------------------
knob(12.0, 24.0)
lines = next(b for b in fresh().bones if b["name"] == "Bone")["fix_lines"]
assert [l["name"] for l in lines] == [name] and not lines[0]["edited"], lines
pts = lines[0]["points"]
assert close(pts[0], (0.0, 24.0)) and close(pts[-1], (24.0, 24.0)), ("from frame 1 to its end", pts[0], pts[-1])
assert all(close(p[1], 24.0) for p in pts), "Up stays put along it"
assert close(lines[0]["now"], (12.0, 24.0), 0.05) and close(lines[0]["strength"], 1.0), lines[0]
assert ops.anim.action_play_set(name=name, mute="1") == {'FINISHED'}
settle()
assert next(b for b in fresh().bones if b["name"] == "Bone")["fix_lines"][0]["strength"] == 0.0, "muted: no dot"
assert ops.anim.action_play_set(name=name, mute="0") == {'FINISHED'}
assert "fix_lines" not in next(b for b in fresh().bones if b["name"] == "arm"), "only a knob has a box"

# --- Going two ways at once, it fades as the knob leaves its line --------------------------------------------------------
knob(0.0, 0.0)
fresh().select_bone("Bone")
assert ops.armature.bone_fix_new(bones="Bone") == {'FINISHED'}
diagonal = doc.action
doc.frame_current = 30
fresh().bone_set("Bone", knob=(24.0, 24.0))
settle()
mainline()
diagonal = next(f["name"] for f in fixes() if f["name"] != name)


def diag():
    return next(f for f in fixes() if f["name"] == diagonal)


knob(12.0, 12.0)
assert close(diag()["strength"], 1.0) and 10.0 < diag()["frame"] < 22.0, ("on its line", diag())
knob(15.0, 9.0)
assert close(diag()["strength"], 1.0 - (0.125 * 2 ** 0.5) / 0.5, 1e-2), ("a little off it", diag())
knob(24.0, 0.0)
assert diag()["strength"] == 0.0, ("far off it, though Right and Up are both partway", diag())
lines = next(b for b in fresh().bones if b["name"] == "Bone")["fix_lines"]
d = next(l for l in lines if l["name"] == diagonal)
assert all(close(p[0], p[1], 1e-3) for p in d["points"]), "a diagonal across the box"
assert ops.anim.action_delete(name=diagonal) == {'FINISHED'}
mainline()
assert [f["name"] for f in fixes()] == [name]
knob(24.0, 24.0)

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
assert f["fade"] == "SMOOTH", "its fade saved"
assert ops.armature.bone_fix_set(name="Look Fix", fade="LINEAR") == {'FINISHED'}
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

# --- Never taken for a bone's turn action: "turn 2" would be turn's other one -------------------------------------------
knob(0.0, 0.0)
fresh().select_bone("Knob")
assert ops.armature.bone_fix_new() == {'FINISHED'}
doc.frame_current = 30
fresh().bone_set("Knob", knob=(20.0, 0.0))
settle()
mainline()
named = [f["name"] for f in fixes() if f["name"] != "up and turn"]
assert len(named) == 1 and named[0] not in ("turn", "turn 2"), ("named for turn, never as turn's own", named)
# A file from before, with a fix named so: it opens as a fix all the same.
old = os.path.join(tempfile.mkdtemp(), "turn_named.oanim")
assert ops.wm.save_as_mainfile(filepath=old) == {'FINISHED'}
with zipfile.ZipFile(old) as z:
    members = {n: z.read(n) for n in z.namelist()}
with zipfile.ZipFile(old, "w") as z:
    for n, data in members.items():
        z.writestr(n, data.replace(('"' + named[0] + '"').encode(), b'"turn 2"') if n.endswith(".json") else data)
assert ops.wm.open_mainfile(filepath=old) == {'FINISHED'}
rig = next(l for l in layers.all() if l.name == "Head")
assert [a["kind"] for a in fresh().actions if a["name"] == "turn 2"] == ["FIX"], fresh().actions
assert "turn 2" not in next(b for b in fresh().bones if b["name"] == "turn")["turn_actions"], "not turn's own"
knob(20.0, 0.0)
assert close(next(f for f in fixes() if f["name"] == "turn 2")["strength"], 1.0), fixes()
assert ops.anim.action_delete(name="turn 2") == {'FINISHED'}
mainline()

# --- Symmetrize mirrors the fixes of its bones: the other side's follow the other side's bones ---------------------------
mainline()
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
rig.name = "Eyes"
ops.armature.bone_add(name="Eye_L", head_x="2.0", head_y="3.0", tail_x="2.5", tail_y="3.0")
ops.armature.select_none()
ops.armature.bone_add(name="Lid_L", head_x="2.0", head_y="4.0", tail_x="3.0", tail_y="4.0")
ops.armature.select_none()
ops.armature.bone_add(name="Iris_L", head_x="2.0", head_y="2.0", tail_x="2.5", tail_y="2.0")
for side, to in (("Right", (2.5, 2.0)), ("Up", (2.0, 2.5))):
    # Its sides move the iris (the lid is the fix's alone).
    assert ops.anim.action_new(name="Eye_L " + side) == {'FINISHED'}
    doc.frame_current = 24
    fresh().bone_set("Iris_L", position=to)
    doc.frame_current = 25
    mainline()
fresh().select_bone("Eye_L")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="Eye_L Right") == {'FINISHED'}
assert ops.armature.controller_side(side="UP", action="Eye_L Up") == {'FINISHED'}


def bone_of(n):
    return next(b for b in fresh().bones if b["name"] == n)


def turned(n):
    b = bone_of(n)
    return (b["angle"] - b["setup_angle"] + 3.14159265) % 6.2831853 - 3.14159265


def eye(n, x, y):
    doc.frame_current = 5
    fresh().select_bone(n)
    fresh().bone_set(n, knob=(x, y))
    settle()


eye("Eye_L", 0.0, 0.0)
assert ops.armature.bone_fix_new(bones="Eye_L") == {'FINISHED'}
doc.frame_current = 30
fresh().bone_set("Eye_L", knob=(10.0, 5.0))
fresh().bone_set("Lid_L", angle=bone_of("Lid_L")["setup_angle"] + 0.5)
settle()
mainline()
left = fixes()[0]["name"]
assert ops.armature.bone_fix_set(name=left, fade="SMOOTH") == {'FINISHED'}
eye("Eye_L", 10.0, 5.0)
assert close(turned("Lid_L"), 0.5), ("the fix turns the lid", turned("Lid_L"))
mainline()
ops.armature.select_none()
for n in ("Eye_L", "Lid_L", "Iris_L"):
    fresh().select_bone(n, extend=True)
assert ops.armature.symmetrize(action_bone_actions="1") == {'FINISHED'}
right = next(f for f in fixes() if f["name"] != left)
assert right["follows"] == ["Eye_R"] and right["fade"] == "SMOOTH" and right["auto_name"], right
assert right["name"] == "Eye_R Up and Left", ("named for the other side's actions where it ends", right)
line = next(l for l in bone_of("Eye_R")["fix_lines"] if l["name"] == right["name"])
assert close(line["points"][0], (0.0, 0.0)) and close(line["points"][-1], (-10.0, 5.0)), ("Left and Right swap", line)
eye("Eye_R", -10.0, 5.0)
assert close(next(f for f in fixes() if f["name"] == right["name"])["strength"], 1.0), fixes()
assert close(turned("Lid_R"), -0.5), ("the other lid turns the other way", turned("Lid_R"))
assert close(turned("Lid_L"), 0.5), "the first side as it was"
eye("Eye_R", 10.0, 5.0)
assert close(turned("Lid_R"), 0.0), "on the wrong side it's off its line"
# Again: the other side's fix is made anew, not a second one.
mainline()
ops.armature.select_none()
for n in ("Eye_L", "Lid_L", "Iris_L"):
    fresh().select_bone(n, extend=True)
assert ops.armature.symmetrize(action_bone_actions="1") == {'FINISHED'}
assert sorted(f["follows"][0] for f in fixes()) == ["Eye_L", "Eye_R"], fixes()
assert bone_of("Eye_R")["controller_actions"] == {'RIGHT': '', 'LEFT': 'Eye_R Left', 'UP': 'Eye_R Up', 'DOWN': ''},     ("the other knob keeps its sides, made anew", bone_of("Eye_R")["controller_actions"])
assert "Eye_R Up and Left" in [f["name"] for f in fixes()], fixes()

print("test_bone_fixes: ok")
