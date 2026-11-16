"""Paste Pose As, a pick-one: Keys (the keys copied; what actions add where it is pasted comes on top), Same Look (it looks
just as it did when copied, moving with the bones here: what actions added there is kept and what they add here is taken
out) and Same Place (each point exactly where it showed when copied, whatever the bones and actions do here; Ignore
Bones's old name). The choice is kept for the next paste.

Run with:  OpenAnimate --background --python tests/test_pose_paste_as.py
"""

import oanim

ops, wm = oanim.ops, oanim.wm

SMILE_MOVE = (0.0, 0.3)
SMILE_TURN = 0.2


def close(a, b, eps=1e-4):
    if isinstance(a, (int, float)):
        return abs(a - b) < eps
    return all(abs(x - y) < eps for x, y in zip(a, b))


def plus(a, b):
    return (a[0] + b[0], a[1] + b[1])


def minus(a, b):
    return (a[0] - b[0], a[1] - b[1])


def scene():
    """A bone layer: Arm moves the drawing's points (Parent Bone, Points), Leg is posed by hand, and Smile has an action
    bone action that moves point 0 by SMILE_MOVE and turns Leg by SMILE_TURN when Smile is turned 0.8. Frame 10: Smile
    turned (its action plays whole), point 0 and Leg keyed by hand too. Frame 20: Smile at rest, Arm turned. Frame 30:
    Smile turned again. Auto Keying on."""
    global doc, layers, rig_id, art_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id
    for name, hx, hy, tx, ty in (("Arm", 0, 0, 1, 0), ("Leg", 0, -1, 0, -2), ("Smile", 2, 0, 2, 1)):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(hx), head_y=str(hy), tail_x=str(tx), tail_y=str(ty),
                                     parent="") == {'FINISHED'}
    assert ops.layer.new() == {'FINISHED'}
    art_id = layers.active.id
    assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
    art().add_curve([(0.2, 0.1), (0.4, 0.3), (0.1, 0.5)])
    assert ops.layer.parent_bone_set(bone="Arm", deform="POINTS") == {'FINISHED'}
    setup0 = stored()[0]
    leg_setup = bone("Leg")["setup_angle"]
    smile_setup = bone("Smile")["setup_angle"]
    # The Smile action: point 0 moved, Leg turned, at its frame 10.
    doc.auto_key = True
    layers.active = rig()
    rig().select_bone("Smile")
    assert ops.anim.action_new(name="Smile", action_bone="1") == {'FINISHED'}
    doc.frame_current = 10
    rig().bone_set("Smile", angle=smile_setup + 0.8)
    rig().bone_set("Leg", angle=leg_setup + SMILE_TURN)
    art().set_point(0, plus(setup0, SMILE_MOVE))
    doc.frame_current = 11
    doc.frame_current = 0
    doc.action = ""
    # The mainline.
    doc.frame_current = 10
    rig().bone_set("Smile", angle=smile_setup + 0.8)
    doc.frame_current = 11
    doc.frame_current = 10
    art().set_point(0, (0.3, 0.0))
    rig().bone_set("Leg", angle=leg_setup + 0.3)
    doc.frame_current = 20
    rig().bone_set("Smile", angle=smile_setup)
    rig().bone_set("Arm", angle=0.8)
    art().set_point(1, (0.7, 0.1))
    doc.frame_current = 30
    rig().bone_set("Smile", angle=smile_setup + 0.8)
    rig().bone_set("Arm", angle=0.8)
    doc.frame_current = 21
    doc.frame_current = 10
    # (An undo step of its own, so undoing a paste leaves the scene's Python edits in.)
    layers.active = art()
    assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
    assert ops.object.modifier_remove(index="0") == {'FINISHED'}


def rig():
    return next(l for l in layers.all() if l.id == rig_id)


def art():
    return next(l for l in layers.all() if l.id == art_id)


def bone(name):
    return next(b for b in rig().bones if b["name"] == name)


def stored():
    return [tuple(p[:2]) for p in art().points]


def shown():
    return [tuple(p) for p in art().shown()[0]]


def at(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def pick():
    """Point 0 and Leg selected: the bone layer active, the drawing picked beside it."""
    layers.active = rig()
    rig().select_bone("Leg")
    layers.active = art()
    for l in layers.all():
        l.selected = l.id == art_id
    ops.mesh.select_none()
    art().select_points([0])
    layers.active = rig()


def copy_at_10():
    """Copy point 0 and Leg on frame 10, where Smile's action plays; what they stored and showed there."""
    scene()
    at(10)
    was = {"stored": stored()[0], "shown": shown()[0], "leg": bone("Leg")["angle"]}
    pick()
    assert ops.pose.copy() == {'FINISHED'}, "copy"
    return was


def report():
    r = wm.banner_report()
    return r[2] + " " + r[3]


# --- Keys: the keys copied; Smile's move isn't in them, and nothing plays it on frame 20 -------------------------------
was = copy_at_10()
at(20)
pick()
assert ops.pose.paste(paste_as="KEYS") == {'FINISHED'}
assert close(stored()[0], minus(was["stored"], SMILE_MOVE)), (stored()[0], was["stored"])
assert close(bone("Leg")["angle"], was["leg"] - SMILE_TURN), (bone("Leg")["angle"], was["leg"])
op = wm.last_operation()
assert op and op[0] == "pose.paste" and op[1].get("paste_as") == "KEYS", op

# --- Same Look: it looks as it did, Smile's move kept, and it moves with Arm, turned here ------------------------------
was = copy_at_10()
at(20)
pick()
assert ops.pose.paste(paste_as="LOOK") == {'FINISHED'}
assert close(stored()[0], was["stored"]), (stored()[0], was["stored"])
assert close(bone("Leg")["angle"], was["leg"]), (bone("Leg")["angle"], was["leg"])
assert not close(shown()[0], was["shown"]), "it moves with Arm, turned here"
assert "Same Look" in report(), report()
at(20)
assert close(stored()[0], was["stored"]), "keyed as pasted"

# --- Same Look where Smile plays too: Smile's move counted once, not twice ---------------------------------------------
was = copy_at_10()
at(30)
pick()
assert ops.pose.paste(paste_as="LOOK") == {'FINISHED'}
assert close(stored()[0], was["stored"]), (stored()[0], was["stored"])
assert close(bone("Leg")["angle"], was["leg"]), (bone("Leg")["angle"], was["leg"])
at(30)
assert close(stored()[0], was["stored"]), "keyed as pasted, Smile's move taken out of the key"

# --- Same Place: exactly where it showed on screen, whatever Arm and Smile do here --------------------------------------
was = copy_at_10()
at(20)
pick()
assert ops.pose.paste(paste_as="PLACE") == {'FINISHED'}
assert close(shown()[0], was["shown"]), (shown()[0], was["shown"])
at(20)
assert close(shown()[0], was["shown"]), "kept as pasted"

# --- The choice is kept for the next paste (Ctrl V); Ignore Bones still means Same Place --------------------------------
was = copy_at_10()
at(20)
pick()
assert ops.pose.paste(paste_as="LOOK") == {'FINISHED'}
assert ops.ed.undo() == {'FINISHED'}
at(20)
pick()
assert wm.event_simulate("V", ctrl=True, area="Viewport")
assert close(stored()[0], was["stored"]), "Same Look kept from the last paste"
assert wm.last_operation()[1].get("paste_as") == "LOOK", wm.last_operation()
assert ops.pose.paste(ignore_bones="1") == {'FINISHED'}
assert close(shown()[0], was["shown"]), "ignore_bones=1 is Same Place"
assert wm.last_operation()[1].get("paste_as") == "PLACE", wm.last_operation()
assert ops.pose.paste(paste_as="KEYS") == {'FINISHED'}

print("pose paste as: ok")
