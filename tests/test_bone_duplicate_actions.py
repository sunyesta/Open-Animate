"""Shift D's and Paste Bones' Actions (off by default): the copies get their own copies of the originals' actions. A 2 Axis
Controller's sides are copied and made the copy's sides, named after the copy where they were after the original
("Jaw Right" for Jaw.001 is "Jaw.001 Right", else numbered); a bone's turn actions take the copy's name; a fix following
copied bones is copied, following the copies in place of the bones copied (the others it follows kept). The keys a copied
bone has in them go on its copy, everything else's stay where they were, so the copies move the same drawings; the
originals' actions are left as they were. Pasted into another file, keys go only on what that file has, and a fix
following a bone it hasn't is left out.

Run with:  OpenAnimate --background --python tests/test_bone_duplicate_actions.py
"""

import oanim

ops = oanim.ops


def doc():
    return oanim.data.document


def layer(lid):
    return next(l for l in oanim.data.layers.all() if l.id == lid)


def mainline():
    assert ops.anim.action_set(name="") in ({'FINISHED'}, {'CANCELLED'})
    doc().frame_current = 0


def settle():
    doc().frame_current = doc().frame_current + 1
    doc().frame_current = doc().frame_current - 1


def scene():
    """A knob Jaw (Right: "Jaw Right", Up: "look_up", each moving the face), Arm with its turn action "Arm" (also moving
    the face's last point), Other, and two fixes: one following Jaw, one following Jaw and Other."""
    global rig_id, face_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc().auto_key = True
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = oanim.data.layers.active
    rig_id = rig.id
    ops.armature.bone_add(name="Jaw", head_x="-3.0", head_y="3.0", tail_x="-2.5", tail_y="3.0")
    ops.armature.bone_add(name="Arm", head_x="3.0", head_y="3.0", tail_x="3.0", tail_y="4.0")
    ops.armature.bone_add(name="Other", head_x="6.0", head_y="3.0", tail_x="6.0", tail_y="4.0")
    for name in ("Jaw", "Arm", "Other"):
        layer(rig_id).bone_set(name, strength=0.0)
    ops.layer.new()
    face = oanim.data.layers.active
    face.name = "face"
    face_id = face.id
    face.add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
    ops.layer.move_to_group(group=str(rig_id))
    for name, i, frames, moved in (("Jaw Right", 0, 24, (2.0, 0.5)), ("look_up", 1, 20, (1.0, 1.0))):
        oanim.data.layers.active = layer(rig_id)
        assert ops.anim.action_new(name=name) == {'FINISHED'}
        doc().frame_current = frames
        layer(face_id).set_point(i, moved)
        doc().frame_current = frames + 1
        mainline()
    oanim.data.layers.active = layer(rig_id)
    layer(rig_id).select_bone("Jaw")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action="Jaw Right") == {'FINISHED'}
    assert ops.armature.controller_side(side="UP", action="look_up") == {'FINISHED'}
    # Arm's turn action, its keys turning Arm and moving the face's last point.
    layer(rig_id).select_bone("Arm")
    assert ops.armature.bone_turn_action_new(direction="CCW") == {'FINISHED'}
    assert doc().action == "Arm", doc().action
    layer(face_id).set_point(2, (2.0, 1.0))
    settle()
    mainline()
    # A fix following Jaw, and one following Jaw and Other.
    for extra in (None, "Other"):
        oanim.data.layers.active = layer(rig_id)
        layer(rig_id).select_bone("Jaw")
        if extra:
            layer(rig_id).select_bone(extra, extend=True)
        assert ops.armature.bone_fix_new() == {'FINISHED'}
        doc().frame_current = 30
        layer(rig_id).bone_set("Jaw", knob=(24.0, 20.0))
        layer(face_id).set_point(2, (2.5, -0.5))
        settle()
        mainline()
    assert len(fixes()) == 2, fixes()
    oanim.data.layers.active = layer(rig_id)


def bones():
    return {b["name"]: b for b in layer(rig_id).bones}


def sides(name):
    """A knob's sides' actions: Right, Left, Up, Down."""
    a = bones()[name]["controller_actions"]
    return [a["RIGHT"], a["LEFT"], a["UP"], a["DOWN"]]


def fixes():
    return [(f["name"], sorted(f["follows"])) for f in layer(rig_id).bone_fixes]


def action_names():
    return [a["name"] for a in layer(rig_id).actions]


def keys_in(action, lid, path):
    """The keys of `path` on layer `lid` in action `action`, as (frame, value) pairs."""
    oanim.data.layers.active = layer(rig_id)
    assert ops.anim.action_set(name=action) == {'FINISHED'}, action
    keys = [(k["frame"], k["value"]) for k in layer(lid).keyframes(path)]
    mainline()
    oanim.data.layers.active = layer(rig_id)
    return keys


def bone_path(name, channel):
    return 'bones["' + name + '"].' + channel


def pick(*names):
    rig = layer(rig_id)
    rig.select_bone(names[0])
    for n in names[1:]:
        rig.select_bone(n, extend=True)


def kept_as_it_was(before):
    """The originals' actions as they were before copying."""
    assert sides("Jaw") == before["sides"], (sides("Jaw"), before["sides"])
    for action, path in (("Jaw Right", "points[0].pos"), ("look_up", "points[1].pos"), ("Arm", "points[2].pos")):
        assert keys_in(action, face_id, path) == before[action], action
    assert keys_in("Arm", rig_id, bone_path("Arm", "angle")) == before["Arm angle"]


def record():
    return {"sides": sides("Jaw"),
            "Jaw Right": keys_in("Jaw Right", face_id, "points[0].pos"),
            "look_up": keys_in("look_up", face_id, "points[1].pos"),
            "Arm": keys_in("Arm", face_id, "points[2].pos"),
            "Arm angle": keys_in("Arm", rig_id, bone_path("Arm", "angle"))}


def check_copied(before, fix_names_before):
    """Jaw and Arm copied as Jaw.001 and Arm.001 with their own actions."""
    names = action_names()
    for made in ("Jaw.001 Right", "look_up.001", "Arm.001"):
        assert made in names, (made, names)
    assert sides("Jaw.001") == ["Jaw.001 Right", "", "look_up.001", ""], sides("Jaw.001")
    # The copies' actions move the face as the originals' do.
    assert keys_in("Jaw.001 Right", face_id, "points[0].pos") == before["Jaw Right"]
    assert keys_in("look_up.001", face_id, "points[1].pos") == before["look_up"]
    assert keys_in("Arm.001", face_id, "points[2].pos") == before["Arm"]
    # Arm's keys in its turn action went on Arm.001; Arm has none in the copy.
    assert keys_in("Arm.001", rig_id, bone_path("Arm.001", "angle")) == before["Arm angle"]
    assert keys_in("Arm.001", rig_id, bone_path("Arm", "angle")) == []
    # The fixes: each following Jaw copied, following Jaw.001 in its place (Other kept).
    now = fixes()
    assert len(now) == 4, now
    assert [f for f in now if f[0] in fix_names_before] == [f for f in now[:2]], now
    assert sorted(f[1] for f in now[2:]) == [["Jaw.001"], ["Jaw.001", "Other"]], now
    for (name, follows), (old, _) in zip(now[2:], now[:2]):
        assert keys_in(name, rig_id, bone_path("Jaw.001", "position")) == \
            keys_in(old, rig_id, bone_path("Jaw", "position")), name
        assert keys_in(name, rig_id, bone_path("Jaw", "position")) == [], "Jaw's line keys went on Jaw.001"
        assert keys_in(name, face_id, "points[2].pos") == keys_in(old, face_id, "points[2].pos"), name
    kept_as_it_was(before)


def face_point(i):
    return layer(face_id).points[i]


def knob_moves_face(knob):
    """Pushing `knob` right on frame 12 moves the face's first point as far as pushing Jaw does."""
    doc().frame_current = 12
    layer(rig_id).bone_set(knob, knob=(24.0, 0.0))
    settle()
    return tuple(face_point(0))


# --- Off by default: Shift D makes no actions ---------------------------------------------------------------------------
scene()
before_names = action_names()
pick("Jaw", "Arm")
assert ops.armature.duplicate_move(move_x="1.0", move_y="0.0") == {'FINISHED'}
assert action_names() == before_names, action_names()
assert sides("Jaw.001") == ["", "", "", ""], sides("Jaw.001")
assert len(fixes()) == 2, fixes()

# --- Shift D with Actions: sides, turn actions and fixes copied for the copies; the originals' as they were --------------
scene()
before = record()
fix_names_before = [f[0] for f in fixes()]
pick("Jaw", "Arm")
assert ops.armature.duplicate_move(actions="1", move_x="1.0", move_y="0.0") == {'FINISHED'}
check_copied(before, fix_names_before)
# Played: the copy's knob moves the face as Jaw's does.
moved = knob_moves_face("Jaw.001")
assert moved[0] > 1.5, ("Jaw.001 pushed to the end of Right moves the face's first point to 2", moved)
# One step: undo takes it all back.
while "Jaw.001" in bones() and oanim.wm.undo_history()[1] > 0:
    ops.ed.undo()
assert "Jaw.001 Right" not in action_names() and len(fixes()) == 2, (action_names(), fixes())

# --- Inside an action: the one being edited is copied too ----------------------------------------------------------------
scene()
before = record()
assert ops.anim.action_set(name="Jaw Right") == {'FINISHED'}
doc().frame_current = 0
oanim.data.layers.active = layer(rig_id)
pick("Jaw")
assert ops.armature.duplicate_move(actions="1", move_x="1.0", move_y="0.0") == {'FINISHED'}
assert doc().action == "Jaw Right", doc().action
mainline()
assert keys_in("Jaw.001 Right", face_id, "points[0].pos") == before["Jaw Right"],     keys_in("Jaw.001 Right", face_id, "points[0].pos")
assert keys_in("Jaw Right", face_id, "points[0].pos") == before["Jaw Right"]

# --- Only Jaw copied: Arm's turn action stays Arm's alone, and the fix following Jaw and Other follows Jaw.001 and Other
scene()
pick("Jaw")
assert ops.armature.duplicate_move(actions="1", move_x="1.0", move_y="0.0") == {'FINISHED'}
assert "Arm.001" not in action_names(), action_names()
assert sorted(f[1] for f in fixes()[2:]) == [["Jaw.001"], ["Jaw.001", "Other"]], fixes()

# --- Only Other copied: the fix following Jaw and Other is copied following Jaw and Other.001; the one following Jaw alone
# --- isn't -------------------------------------------------------------------------------------------------------------
scene()
pick("Other")
assert ops.armature.duplicate_move(actions="1", move_x="1.0", move_y="0.0") == {'FINISHED'}
assert [f[1] for f in fixes()[2:]] == [["Jaw", "Other.001"]], fixes()
assert sides("Jaw") == ["Jaw Right", "", "look_up", ""], sides("Jaw")
assert "Jaw.001 Right" not in action_names() and len(action_names()) == len(set(action_names())), action_names()

# --- Paste Bones with Actions, here: as Shift D --------------------------------------------------------------------------
scene()
before = record()
fix_names_before = [f[0] for f in fixes()]
pick("Jaw", "Arm")
assert ops.armature.copy() == {'FINISHED'}
assert ops.armature.paste() == {'FINISHED'}
assert "Jaw.001 Right" not in action_names(), "off by default"
ops.ed.undo()
assert ops.armature.paste(actions="1") == {'FINISHED'}
check_copied(before, fix_names_before)

# --- Into another file: the face there drawn otherwise gets no keys; a fix following Other (not there) is left out ------
scene()
pick("Jaw")
assert ops.armature.copy() == {'FINISHED'}
assert ops.wm.read_homefile() == {'FINISHED'}
assert ops.layer.new_bone() == {'FINISHED'}
rig_id = oanim.data.layers.active.id
ops.layer.new()
other_face = oanim.data.layers.active
other_face.name = "face"
other_face.add_curve([(0.0, 0.0), (1.0, 0.0)])
ops.layer.move_to_group(group=str(rig_id))
face_id = other_face.id
oanim.data.layers.active = layer(rig_id)
assert ops.armature.paste(actions="1") == {'FINISHED'}
assert "Jaw" in bones(), bones().keys()
assert sides("Jaw")[0] == "Jaw Right", sides("Jaw")
assert "Jaw Right" in action_names() and "look_up" in action_names(), action_names()
assert keys_in("Jaw Right", face_id, "points[0].pos") == [], "that face has other points"
assert [f[1] for f in fixes()] == [["Jaw"]], ("the fix following Other is left out", fixes())

print("test_bone_duplicate_actions: OK")
