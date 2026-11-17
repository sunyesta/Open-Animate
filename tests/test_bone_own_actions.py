"""A bone's own actions belong to it: deleting the bone deletes them with it (a 2 Axis Controller's sides, the actions
named after a bone that turn it, and the fixes following only bones deleted; a fix following others too follows the
rest), in the same undo step. Renaming a knob renames its sides named after it ("Jaw Right" for Mouth is "Mouth Right").

Run with:  OpenAnimate --background --python tests/test_bone_own_actions.py
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



def last_step():
    names, index = oanim.wm.undo_history()
    return names[index]


# --- Deleting a knob deletes its sides and the fix following only it; the fix following Other too follows Other ---------
scene()
assert sorted(action_names()) == sorted(["Jaw Right", "look_up", "Arm", fixes()[0][0], fixes()[1][0]]), action_names()
pick("Jaw")
assert ops.armature.bone_delete() == {'FINISHED'}

assert "Jaw" not in bones()
assert "Jaw Right" not in action_names() and "look_up" not in action_names(), action_names()
assert [f[1] for f in fixes()] == [["Other"]], fixes()
assert "Arm" in action_names(), "Arm's own action stays"
assert len(action_names()) == 2, action_names()
# One step: undo brings the knob back with its actions.
ops.ed.undo()
assert "Jaw" in bones() and sides("Jaw") == ["Jaw Right", "", "look_up", ""], sides("Jaw") if "Jaw" in bones() else None
assert len(fixes()) == 2 and "Jaw Right" in action_names(), (fixes(), action_names())
assert keys_in("Jaw Right", face_id, "points[0].pos") != []

# --- Deleting a bone deletes its turn action ------------------------------------------------------------------------------
scene()
pick("Arm")
assert ops.armature.bone_delete() == {'FINISHED'}
assert "Arm" not in action_names(), action_names()
assert "Jaw Right" in action_names() and len(fixes()) == 2, (action_names(), fixes())

# --- Deleting Other: the fix following Jaw and Other follows Jaw; no action goes -----------------------------------------
scene()
before = action_names()
pick("Other")
assert ops.armature.bone_delete() == {'FINISHED'}
assert len(action_names()) == len(before), (before, action_names())
assert sorted(f[1] for f in fixes()) == [["Jaw"], ["Jaw"]], fixes()

# --- Deleting every bone a fix follows deletes it -------------------------------------------------------------------------
scene()
pick("Jaw", "Other")
assert ops.armature.bone_delete() == {'FINISHED'}
assert fixes() == [], fixes()
assert action_names() == ["Arm"], action_names()

# --- Renaming a knob renames its sides named after it ---------------------------------------------------------------------
scene()
layer(rig_id).bone_set("Jaw", name="Mouth")
assert sides("Mouth") == ["Mouth Right", "", "look_up", ""], sides("Mouth")
assert "Mouth Right" in action_names() and "Jaw Right" not in action_names(), action_names()
assert keys_in("Mouth Right", face_id, "points[0].pos") != []

print("test_bone_own_actions: OK")
