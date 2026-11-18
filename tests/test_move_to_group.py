"""P with bones picked > Move to Bone Group (armature.move_to_group target=): the selected bones, and those hanging
from them, go into another bone group of the same rig, resting and posed where they were on every frame: into a group
inside theirs they hang across from the bone they hung from; out of it, as roots (or from the bone given with
parent=). Their keys go along, those of actions the target has no part in left out; drawings bound only to them go
too, looking as they did. NEW makes a bone group inside theirs. Selected Only leaves the bones hanging from them, under
the nearest that stays. Refused, with no undo step: a bone group outside the rig, a drawing bound to bones that move
and bones that stay, a constraint between a bone that moves and one that stays, off the setup frame.

Run with:  OpenAnimate --background --python tests/test_move_to_group.py
"""

import json
import math
import os
import tempfile

import _oanim
import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def by_name(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def reopen():
    """Saved and opened again, so Python edits (no undo step of their own) are what undo goes back to."""
    path = os.path.join(tempfile.gettempdir(), "oa_move_to_group_%d.oanim" % os.getpid())
    ops.wm.save_copy(filepath=path)
    assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
    os.remove(path)


def bone(layer, name):
    return next((b for b in by_name(layer).bones if b["name"] == name), None)


def world(layer, name):
    """Where bone `name` of bone layer `layer` runs now, in the document."""
    l = by_name(layer)
    b = bone(layer, name)
    return tuple(l.to_document(b["head"])) + tuple(l.to_document(b["tail"]))


def steps():
    return wm.undo_history()[1]


def rig():
    """Bone layer Body: Hip, Leg under it, Foot under Leg, Spine and Tail; inside it the bone group Inner, moved, turned and
    scaled, with Arm. Art (in Body) is weighted to Foot alone, Skin to Hip and Spine. Keys: Hip turned on frame
    5, Leg on 10 (mainline); Arm turned on 3 in Body's action swing and on 4 in Inner's action wave. Body2 is another
    rig."""
    global doc, layers
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    body = layers.active
    body.name = "Body"
    for name, head, tail, parent in (("Hip", (0, 0), (1, 0), ""), ("Leg", (1, 0), (2, 0.2), "Hip"),
                                     ("Foot", (2, 0.2), (2.5, 0.8), "Leg"), ("Spine", (0, 0), (0, 1.5), ""),
                                     ("Tail", (-1, 0), (-2, 0.3), "")):
        assert ops.armature.bone_add(name=name, head_x=str(head[0]), head_y=str(head[1]), tail_x=str(tail[0]),
                                     tail_y=str(tail[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    assert ops.layer.new_bone() == {'FINISHED'}
    inner = layers.active
    inner.name = "Inner"
    assert ops.layer.move_to_group(group=str(body.id)) == {'FINISHED'}
    inner = by_name("Inner")
    inner.location_x, inner.location_y, inner.rotation = 0.3, -0.4, 25.0
    inner.scale_x = inner.scale_y = 1.5
    layers.active = inner
    assert ops.armature.bone_add(name="Arm", head_x="0", head_y="1", tail_x="1", tail_y="1.2", parent="") == {'FINISHED'}
    ops.armature.select_none()
    for name, bones in (("Art", ("Foot",)), ("Skin", ("Hip", "Spine"))):
        layers.active = by_name("Body")
        assert ops.layer.new() == {'FINISHED'}
        l = layers.active
        l.name = name
        assert ops.layer.move_to_group(group=str(body.id)) == {'FINISHED'}
        l = by_name(name)
        l.add_curve([(1.2, 0.1), (1.8, 0.2), (2.2, 0.5)])
        l.edit_with_bones = True
        # (Points with no bones yet take their neighbours' as they are weighed.)
        for i in range(3):
            for b in bones:
                ops.weight.point_set(layer=str(l.id), point=str(i), bone=str(bone("Body", b)["id"]), weight="0.5")
        assert [sorted(w) for w in by_name(name).weights] == [sorted(bones)] * 3, by_name(name).weights
    assert ops.layer.new_bone() == {'FINISHED'}
    layers.active.name = "Body2"
    assert ops.layer.move_to_group(group="0") == {'FINISHED'}
    assert ops.armature.bone_add(name="Other", head_x="5", head_y="0", tail_x="6", tail_y="0", parent="") == {'FINISHED'}
    doc.auto_key = True
    doc.frame_current = 5
    by_name("Body").bone_set("Hip", angle=0.6)
    doc.frame_current = 10
    by_name("Body").bone_set("Leg", angle=-0.5)
    doc.frame_current = 0
    layers.active = by_name("Body")
    assert ops.anim.action_new(name="swing") == {'FINISHED'}
    doc.frame_current = 3
    by_name("Inner").bone_set("Arm", angle=1.0)
    assert ops.anim.action_set(name="") == {'FINISHED'}
    doc.frame_current = 0
    layers.active = by_name("Inner")
    assert ops.anim.action_new(name="wave") == {'FINISHED'}
    doc.frame_current = 4
    by_name("Inner").bone_set("Arm", angle=-1.0)
    assert ops.anim.action_set(name="") == {'FINISHED'}
    doc.frame_current = 0
    reopen()


def looks(layer, names, frames=(0, 5, 10)):
    """Each bone's place, and Art's points, on each frame."""
    seen = {}
    for f in frames:
        doc.frame_current = f
        seen[f] = {n: world(layer.get(n, "Body") if isinstance(layer, dict) else layer, n) for n in names}
        seen[f]["Art"] = [tuple(p) for p in by_name("Art").shown()[0]]
    doc.frame_current = 0
    return seen


def pick(layer, *names):
    layers.active = by_name(layer)
    by_name(layer).select_bone("")
    for i, n in enumerate(names):
        by_name(layer).select_bone(n, extend=i > 0)


# --- Leg (and Foot under it) into Inner: hanging across from Hip, resting and posed where they were, Art with them ---
rig()
before = looks("Body", ("Leg", "Foot"))
pick("Body", "Leg")
step = steps()
assert ops.armature.move_to_group(target=str(by_name("Inner").id)) == {'FINISHED'}
assert steps() == step + 1
assert bone("Body", "Leg") is None and bone("Body", "Foot") is None
leg, foot = bone("Inner", "Leg"), bone("Inner", "Foot")
assert leg["outer_parent"] == ("Body", "Hip") and leg["parent"] == "", leg
assert foot["parent"] == "Leg" and foot["outer_parent"] is None
assert leg["selected"] and foot["selected"] and leg["active"] and not bone("Inner", "Arm")["selected"]
assert layers.active.id == by_name("Inner").id
assert by_name("Art").parent.id == by_name("Inner").id, "the drawing bound to them alone goes along"
assert by_name("Skin").parent.id == by_name("Body").id
for f, seen in before.items():
    doc.frame_current = f
    for n in ("Leg", "Foot"):
        assert close(world("Inner", n), seen[n], 1e-3), (f, n, world("Inner", n), seen[n])
    art = [tuple(p) for p in by_name("Art").shown()[0]]
    assert all(close(a, b, 1e-3) for a, b in zip(art, seen["Art"])), (f, art, seen["Art"])
doc.frame_current = 0
assert ops.ed.undo() == {'FINISHED'}
assert bone("Body", "Leg") and bone("Inner", "Leg") is None and by_name("Art").parent.id == by_name("Body").id
assert ops.ed.redo() == {'FINISHED'}
assert bone("Inner", "Leg")

# --- Arm out of Inner into Body: a root where it rested (Inner turned and scaled); Body's action kept, Inner's not ----
rig()
doc.frame_current = 0
arm_rest = world("Inner", "Arm")
layers.active = by_name("Body")
assert ops.anim.action_set(name="swing") == {'FINISHED'}
doc.frame_current = 3
arm_swing = world("Inner", "Arm")
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0
pick("Inner", "Arm")
assert ops.armature.move_to_group(target="Body") == {'FINISHED'}
arm = bone("Body", "Arm")
assert arm and arm["parent"] == "" and arm["outer_parent"] is None and bone("Inner", "Arm") is None
assert close(world("Body", "Arm"), arm_rest), (world("Body", "Arm"), arm_rest)
assert ops.anim.action_set(name="swing") == {'FINISHED'}
doc.frame_current = 3
assert close(world("Body", "Arm"), arm_swing, 1e-3), (world("Body", "Arm"), arm_swing)
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0
# Back into Inner (going in, every action is kept): its keys in wave were left out on the way up.
pick("Body", "Arm")
assert ops.armature.move_to_group(target="Inner") == {'FINISHED'}
assert close(world("Inner", "Arm"), arm_rest)
layers.active = by_name("Inner")
assert ops.anim.action_set(name="wave") == {'FINISHED'}
doc.frame_current = 4
assert close(world("Inner", "Arm"), arm_rest, 1e-3), "no keys in wave any more"
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0

# --- NEW: a bone group made inside Body for Foot, hanging across from Leg, Art with it -------------------------------
rig()
before = looks("Body", ("Foot",))
pick("Body", "Foot")
count = len(layers.all())
assert ops.armature.move_to_group(target="NEW") == {'FINISHED'}
assert len(layers.all()) == count + 1
made = layers.active
assert made.parent.id == by_name("Body").id and made.name != "Body"
foot = next(b for b in made.bones if b["name"] == "Foot")
assert foot["outer_parent"] == ("Body", "Leg"), foot
for f, seen in before.items():
    doc.frame_current = f
    assert close(world(made.name, "Foot"), seen["Foot"], 1e-3), (f, world(made.name, "Foot"), seen["Foot"])
    art = [tuple(p) for p in by_name("Art").shown()[0]]
    assert all(close(a, b, 1e-3) for a, b in zip(art, seen["Art"])), (f, art, seen["Art"])
assert by_name("Art").parent.id == made.id
doc.frame_current = 0

# --- Selected Only: Leg goes, Foot (and Art) stay, Foot under Hip where it rests ---------------------------------------
rig()
before = looks("Body", ("Foot",), frames=(0,))
pick("Body", "Leg")
assert ops.armature.move_to_group(target="Inner", selected_only="1") == {'FINISHED'}
assert bone("Inner", "Foot") is None and bone("Body", "Foot")["parent"] == "Hip"
assert by_name("Art").parent.id == by_name("Body").id
assert close(world("Body", "Foot"), before[0]["Foot"]), (world("Body", "Foot"), before[0]["Foot"])
doc.frame_current = 5
assert not close(world("Body", "Foot"), before[0]["Foot"]), "it turns with Hip"
doc.frame_current = 0

# --- parent=: hung from a bone in the target ---------------------------------------------------------------------------
rig()
rest = world("Body", "Tail")
pick("Body", "Tail")
assert ops.armature.move_to_group(target="Inner", parent="Arm") == {'FINISHED'}
assert bone("Inner", "Tail")["parent"] == "Arm" and close(world("Inner", "Tail"), rest)
doc.frame_current = 5
pick("Inner", "Arm")
by_name("Inner").bone_set("Arm", angle=0.4)
assert not close(world("Inner", "Tail"), rest), "it follows Arm"
doc.frame_current = 0

# --- Bones elsewhere hanging from them follow them (into the target: its bones' parent); drivers naming them too ----
rig()
body = by_name("Body")
layers.active = by_name("Inner")
arm_rest = world("Inner", "Arm")
assert ops.armature.bone_parent_set(bone="Arm", parent="Tail", parent_layer=str(body.id)) == {'FINISHED'}
assert close(world("Inner", "Arm"), arm_rest), ("Set Parent across a scaled bone group keeps its length",
                                                world("Inner", "Arm"), arm_rest)
for name, inside in (("Deep", "Inner"), ("Second", "Body")):
    assert ops.layer.new_bone() == {'FINISHED'}
    layers.active.name = name
    assert ops.layer.move_to_group(group=str(by_name(inside).id)) == {'FINISHED'}
layers.active = by_name("Deep")
assert ops.armature.bone_add(name="Toe", head_x="-3", head_y="0", tail_x="-3.5", tail_y="0", parent="") == {'FINISHED'}
assert ops.armature.bone_parent_set(bone="Toe", parent="Tail", parent_layer=str(body.id)) == {'FINISHED'}
v = json.dumps([{"name": "t", "layer": body.id, "path": 'bones["Tail"].angle', "component": -1}])
assert ops.anim.driver_add(layer=str(by_name("Skin").id), path="opacity", vars=v, expression="t") == {'FINISHED'}
reopen()
rest = {(l, n): world(l, n) for l, n in (("Inner", "Arm"), ("Deep", "Toe"), ("Body", "Tail"))}
pick("Body", "Tail")
step = steps()
assert ops.armature.move_to_group(target="Second") == {'CANCELLED'}, "Toe (in Deep) couldn't reach Tail in Second"
assert steps() == step
assert ops.armature.move_to_group(target="Inner") == {'FINISHED'}
assert bone("Inner", "Arm")["parent"] == "Tail" and bone("Inner", "Arm")["outer_parent"] is None
assert bone("Deep", "Toe")["outer_parent"] == ("Inner", "Tail")
for (l, n), was in rest.items():
    l = "Inner" if n == "Tail" else l
    assert close(world(l, n), was), (l, n, world(l, n), was)
source = oanim.data.drivers[0]["vars"][0]["source"]
assert source["layer"] == by_name("Inner").id and source["path"] == 'bones["Tail"].angle', source
doc.frame_current = 5
pick("Inner", "Tail")
by_name("Inner").bone_set("Tail", angle=1.2)
assert not close(world("Deep", "Toe"), rest[("Deep", "Toe")]) and not close(world("Inner", "Arm"), rest[("Inner", "Arm")])
doc.frame_current = 0

# --- Refused, with no undo step -----------------------------------------------------------------------------------------
rig()
step = steps()
pick("Body", "Leg")
assert ops.armature.move_to_group(target="Body2") == {'CANCELLED'}, "another rig"
assert ops.armature.move_to_group(target="Body") == {'CANCELLED'}, "where they are"
assert ops.armature.move_to_group(target="Art") == {'CANCELLED'}, "not a bone group"
pick("Body", "Spine")
assert ops.armature.move_to_group(target="Inner") == {'CANCELLED'}, "Skin uses Spine, which would go, and Hip"
pick("Body", "Tail")
assert ops.armature.constraint_add(type="CHILD_OF", bone="Tail") == {'FINISHED'}
by_name("Body").bone_constraint_set("Tail", 0, target="Hip")
reopen()
step = steps()
pick("Body", "Tail")
assert ops.armature.move_to_group(target="Inner") == {'CANCELLED'}, "a constraint on Hip, which stays"
doc.frame_current = 5
pick("Body", "Foot")
assert ops.armature.move_to_group(target="Inner") == {'CANCELLED'}, "off the setup frame"
doc.frame_current = 0
assert steps() == step
assert bone("Body", "Foot") and bone("Body", "Tail")

# --- P opens the bone menu; its list is the rig's other bone groups, the ones moved into last first; Pick Bone -------
rig()
pick("Body", "Tail")
assert wm.event_simulate("P", area="Viewport"), "P opens Move to Bone Group"
assert _oanim.menu_request() == "move_to_group", _oanim.menu_request()
assert bone("Body", "Tail"), "a menu: nothing moved yet"
rows = _oanim.move_group_rows("")
assert rows == [by_name("Inner").id], (rows, "Body2 is another rig, Body holds them")
assert ops.layer.new_bone() == {'FINISHED'}
second = layers.active
second.name = "Second"
assert ops.layer.move_to_group(group=str(by_name("Body").id)) == {'FINISHED'}
pick("Body", "Tail")
assert sorted(_oanim.move_group_rows("")) == sorted([by_name("Second").id, by_name("Inner").id])
assert _oanim.move_group_rows("inn") == [by_name("Inner").id]
assert ops.armature.move_to_group(target="Inner") == {'FINISHED'}
pick("Inner", "Tail")
rows = _oanim.move_group_rows("")
assert by_name("Body").id in rows and by_name("Inner").id not in rows, rows
pick("Body", "Hip")
assert _oanim.move_group_rows("")[0] == by_name("Inner").id, "moved into last: first"
pick("Body", "Spine")
step = steps()
assert not _oanim.move_pick_click(by_name("Skin").id), "a drawing of the bones' own bone group: refused"
assert not _oanim.move_pick_click(by_name("Body2").id), "another rig: refused"
assert steps() == step
pick("Body", "Leg")
assert _oanim.move_pick_click(by_name("Inner").id, bone("Inner", "Arm")["id"]), "a bone clicked"
assert bone("Inner", "Leg")["parent"] == "Arm"
pick("Inner", "Leg")
assert _oanim.move_pick_click(by_name("Skin").id), "a drawing clicked: into its bone group"
assert bone("Body", "Leg") and by_name("Art").parent.id == by_name("Body").id

print("test_move_to_group: OK")
