"""The Select tool drags bones as the IK mockup does. Posing, a press on a bone drags that bone alone (picked alone first
unless it is already), by the part pressed, one undo step (Drag Bone):
- its body: a root moves, a bone with a parent turns about its base by the angle the mouse goes round it. Alt: a
  connected bone moves whole, its parent turning and stretching to reach it (the parent's other connected children
  keeping their tips); any other bone turns and stretches with the mouse's reach from its base;
- its tip: the bone turns to point at the mouse, its length kept. Alt: the tip goes exactly to the mouse, the bone
  stretching, its connected children keeping their tips and the others staying put;
- the head of a bone not connected: it moves, with its children. Alt: the head alone moves, the bone keeping its tip.
On the setup frame a drag moves the picked joints as G does. A press on empty space still draws a box, and a point over
a bone's body still takes the press. (A press on a bone only ever box-selected, and an Alt press always went to picking
a layer, so Alt drags did nothing.)

Run with:  OpenAnimate --background --python tests/test_bone_drag.py
"""

import math

import oanim

ops, wm = oanim.ops, oanim.wm
zoom = 100.0
R2 = math.sqrt(0.5)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def scene():
    global doc, layers, rig
    ops.wm.read_homefile(confirmed="1")
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = layers.active
    for name, head, tail, parent in (("Upper", (0, 0), (1, 0), ""), ("Fore", (1, 0), (2, 0), "Upper"),
                                     ("Hand", (2, 0), (2.4, 0), "Fore"), ("Elbow", (1, 0), (1, -0.5), "Upper"),
                                     ("Loose", (1.5, 0.5), (1.5, 1.0), "Fore"), ("Other", (0, 2), (1, 2), "")):
        assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                     tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    for name in ("Fore", "Hand", "Elbow"):
        assert ops.armature.bone_relations_set(bone=name, connected="1") == {'FINISHED'}
    for name in ("Upper", "Fore", "Hand", "Elbow", "Loose", "Other"):
        assert ops.armature.bone_relations_set(bone=name, keep_end_distance="0") in ({'FINISHED'}, {'CANCELLED'})
    doc.auto_key = True
    doc.frame_current = 10
    rig.select_bone("Hand")
    assert ops.wm.tool_select() == {'FINISHED'}


def bones():
    doc.frame_current = doc.frame_current
    return {b["name"]: b for b in rig.bones}


def picked():
    return sorted(b["name"] for b in rig.bones if b["selected"])


def same(a, b, tol=1e-5):
    return all(dist(a[n][k], b[n][k]) < tol for n in a for k in ("head", "tail"))


def drag(bone, part, at, to, alt=False):
    """The press at `at` dragged to `to` (through a step half way); checked to have taken `bone` by `part`, to be one
    undo step, and to be what the operator does from the same press and mouse. The pose before and after."""
    b0 = bones()
    mid = ((at[0] + to[0]) / 2, (at[1] + to[1]) / 2)
    assert wm.bone_drag(at, [mid, to], alt=alt, zoom=zoom), ("the press takes a bone", bone, part)
    got = bones()
    global picked_after
    picked_after = picked()
    assert bone in picked_after, (bone, picked_after)
    ops.ed.undo()
    assert same(bones(), b0), (bone, part, "one undo step takes it back")
    assert ops.armature.bone_drag(bone=bone, part=part, x=repr(at[0]), y=repr(at[1]), to_x=repr(to[0]),
                                  to_y=repr(to[1]), stretch="1" if alt else "0") == {'FINISHED'}
    assert same(bones(), got), (bone, part, "the press took that bone by that part, as the operator does")
    return b0, got


def near(a, b, what, tol=1e-4):
    assert dist(a, b) < tol, (what, a, b)


# --- A body with a parent: turned about its base by the angle the mouse goes round it ----------------------------------
scene()
b0, b = drag("Fore", "BODY", (1.5, 0.0), (1.5, 0.5))
assert picked_after == ["Fore"], ("picked alone", picked_after)
near(b["Fore"]["head"], (1, 0), "its base stays")
near(b["Fore"]["tail"], (1 + R2, R2), "turned 45 degrees, its length kept")
near(b["Hand"]["tail"], (1 + 1.4 * R2, 1.4 * R2), "its children follow")
near(b["Upper"]["tail"], (1, 0), "its parent stays")

# --- A root's body: moved, its children with it -------------------------------------------------------------------------
scene()
b0, b = drag("Other", "BODY", (0.5, 2.0), (0.7, 2.5))
near(b["Other"]["head"], (0.2, 2.5), "a root moves")
near(b["Other"]["tail"], (1.2, 2.5), "whole")

# --- Alt on a root's body: turned and stretched with the mouse's reach from its base ------------------------------------
scene()
b0, b = drag("Other", "BODY", (0.5, 2.0), (0.0, 3.0), alt=True)
near(b["Other"]["head"], (0, 2), "its base stays")
near(b["Other"]["tail"], (0, 4), "a quarter turn, twice as long")

# Its children ride along as one piece: a connected one on its tip, turned with it and as long as it was, and those
# hanging from them with them.
scene()
b0, b = drag("Upper", "BODY", (0.5, 0.0), (0.0, 1.0), alt=True)
near(b["Upper"]["tail"], (0, 2), "a quarter turn, twice as long")
near(b["Fore"]["head"], (0, 2), "the connected child on its tip")
near(b["Fore"]["tail"], (0, 3), "turned with it, as long as it was")
near(b["Hand"]["tail"], (0, 3.4), "and its child")
near(b["Elbow"]["tail"], (0.5, 2), "the other connected child, turned with it")
near(b["Loose"]["head"], (-0.5, 2.5), "a child not connected, turned with its parent")

# --- Alt on a connected bone's body: it moves whole, its parent turning and stretching to reach it; the parent's other
# connected child keeps its tip, its own children come along ------------------------------------------------------------
scene()
b0, b = drag("Fore", "BODY", (1.5, 0.0), (1.7, 0.3), alt=True)
near(b["Fore"]["head"], (1.2, 0.3), "moved whole")
near(b["Fore"]["tail"], (2.2, 0.3), "its way and length kept")
near(b["Upper"]["head"], (0, 0), "the parent's base stays")
near(b["Upper"]["tail"], (1.2, 0.3), "the parent reaching it")
near(b["Hand"]["tail"], (2.6, 0.3), "its child comes along")
near(b["Loose"]["head"], (1.7, 0.8), "and the one not connected")
near(b["Elbow"]["head"], (1.2, 0.3), "the parent's other child on its tip")
near(b["Elbow"]["tail"], (1, -0.5), "keeping its own tip")

# --- A tip: the bone turns to point at the mouse, its length kept --------------------------------------------------------
scene()
b0, b = drag("Hand", "TIP", (2.4, 0.0), (2.4, 0.4))
near(b["Hand"]["head"], (2, 0), "its base stays")
near(b["Hand"]["tail"], (2 + 0.4 * R2, 0.4 * R2), "pointing at the mouse, as long as it was")

# --- Alt on a tip: exactly to the mouse, the bone stretching; its connected child keeps its tip, the other stays -------
scene()
b0, b = drag("Fore", "TIP", (2.0, 0.0), (2.2, 0.3), alt=True)
near(b["Fore"]["head"], (1, 0), "its base stays")
near(b["Fore"]["tail"], (2.2, 0.3), "Alt: the tip goes exactly there")
near(b["Hand"]["head"], (2.2, 0.3), "the connected child rides the tip")
near(b["Hand"]["tail"], (2.4, 0), "keeping its own tip")
near(b["Loose"]["head"], (1.5, 0.5), "the child not connected stays put")
near(b["Loose"]["tail"], (1.5, 1.0), "whole")

# --- Under a parent Alt stretched: a plain drag keeps the bone as long as it is (the stretch skews what it carries) ----
scene()
drag("Upper", "BODY", (0.5, 0.0), (0.5, 0.5), alt=True)
for part, at, to in (("TIP", "tail", (0.3, 0.4)), ("BODY", "mid", (-0.2, 0.5))):
    b0 = bones()
    h, t = b0["Fore"]["head"], b0["Fore"]["tail"]
    at = t if at == "tail" else ((h[0] + t[0]) / 2, (h[1] + t[1]) / 2)
    b0, b = drag("Fore", part, at, (at[0] + to[0], at[1] + to[1]))
    assert abs(dist(b["Fore"]["head"], b["Fore"]["tail"]) - dist(h, t)) < 1e-4, (part, "as long as it was",
                                                                                 dist(h, t), b["Fore"])
    near(b["Fore"]["head"], h, (part, "its base stays"))

# --- The head of a bone not connected: it moves with its children; Alt moves the head alone ------------------------------
scene()
b0, b = drag("Loose", "HEAD", (1.5, 0.5), (1.7, 0.6))
near(b["Loose"]["head"], (1.7, 0.6), "moved")
near(b["Loose"]["tail"], (1.7, 1.1), "whole")
scene()
b0, b = drag("Loose", "HEAD", (1.5, 0.5), (1.7, 0.6), alt=True)
near(b["Loose"]["head"], (1.7, 0.6), "Alt: the head goes there")
near(b["Loose"]["tail"], (1.5, 1.0), "the tip stays")

# --- Only the bone pressed moves; the bones picked stay picked ------------------------------------------------------------
scene()
rig.select_bone("Upper")
rig.select_bone("Other", extend=True)
b0, b = drag("Other", "BODY", (0.5, 2.0), (0.5, 2.5))
assert picked_after == ["Other", "Upper"], ("both stay picked", picked_after)
near(b["Upper"]["head"], (0, 0), "the other picked bone stays")
near(b["Other"]["head"], (0, 2.5), "the bone pressed moves")

# --- A pinned ankle holds while the pelvis above it is dragged -----------------------------------------------------------
scene()
doc.frame_current = 0
for name, head, tail, parent in (("Pelvis", (3, 0), (3, 0.4), ""), ("Thigh", (3, 0), (3.1, -1), "Pelvis"),
                                 ("Calf", (3.1, -1), (3, -2), "Thigh"), ("Foot", (3, -2), (3.3, -2.05), "Calf")):
    assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                 tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
    ops.armature.select_none()
assert ops.armature.ik_base_add(bone="Pelvis") == {'FINISHED'}
assert ops.armature.ik_end_add(bone="Foot") == {'FINISHED'}
doc.frame_current = 10
rig.select_bone("Foot")
assert ops.armature.ik_pin_toggle() == {'FINISHED'}
b0, b = drag("Pelvis", "BODY", (3.0, 0.2), (3.2, -0.1))
near(b["Pelvis"]["head"], (3.2, -0.3), "the pelvis moves")
near(b["Foot"]["head"], b0["Foot"]["head"], "the pinned ankle holds")

# --- Let go with Esc or a right-click: nothing changed ------------------------------------------------------------------
scene()
b0 = bones()
assert wm.bone_drag((1.5, 0.0), [(1.5, 0.5)], zoom=zoom, confirm=False)
assert same(bones(), b0), "cancelled, the pose is as it was"

# --- The setup frame: the picked joints move as G -----------------------------------------------------------------------
scene()
doc.frame_current = 0
assert wm.bone_drag((0.5, 2.0), [(0.5, 2.5)], zoom=zoom)
b = bones()
near(b["Other"]["head"], (0, 2.5), "moved as G on the setup frame")
assert picked() == ["Other"], picked()

# --- Empty space: no bone taken (a box) ----------------------------------------------------------------------------------
scene()
b0 = bones()
assert not wm.bone_drag((1.5, -1.5), [(2.0, -2.0)], zoom=zoom), "a press on empty space takes no bone"
assert same(bones(), b0) and picked() == ["Hand"], picked()

# --- A point of a drawing edited with the bones, over a bone's body, takes the press -------------------------------------
scene()
ops.layer.new()
layers.active.name = "Sleeve"
layers.active.add_curve([(0.5, 0.0), (0.5, -0.6), (0.9, -0.6)], closed=False)
ops.layer.move_to_group(group=str(rig.id))
sleeve = next(l for l in layers.all() if l.name == "Sleeve")
sleeve.edit_with_bones = True
layers.active = rig
rig.select_bone("Hand")
assert not wm.bone_drag((0.5, 0.0), [(0.5, 0.5)], zoom=zoom), "the point over the body wins"
assert wm.bone_drag((0.2, 0.0), [(0.2, 0.3)], zoom=zoom), "the body away from the point is the bone's"
assert picked() == ["Upper"], picked()

# --- Alt from another tool picks a layer, as before: no bone dragged -------------------------------------------------
scene()
b0 = bones()
assert ops.wm.tool_transform_layer() == {'FINISHED'}
assert not wm.bone_drag((1.5, 0.0), [(1.5, 0.5)], alt=True, zoom=zoom), "the Transform Layer tool's Alt press picks"
assert not wm.bone_drag((1.5, 0.0), [(1.5, 0.5)], zoom=zoom), "and its plain press moves the layer"
assert same(bones(), b0), "nothing moved"

# --- The operator refuses what it can't do -------------------------------------------------------------------------------
scene()
assert ops.armature.bone_drag(bone="Nope", part="BODY", to_x="1") == {'CANCELLED'}
assert ops.armature.bone_drag(bone="Fore", part="ELBOW", to_x="1") == {'CANCELLED'}
doc.frame_current = 0
assert ops.armature.bone_drag(bone="Fore", part="BODY", to_x="1") == {'CANCELLED'}, "posing only"

print("bone drag: ok")
