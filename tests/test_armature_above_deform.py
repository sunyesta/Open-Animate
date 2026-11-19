"""A drawing with a deform, moved into a bone layer, gets its Armature modifier above the deform: the deform then measures
from the drawing as it was before the bones, so the shape's movement counts once. The Armature went in at the bottom,
below the deform, and a drawing bent by a cage that the same bone carries was moved by the bone twice: once along with
the cage and again by its own weights (a pants leg's creases in the clay file, the leg raised, floated off above it).

Run with:  OpenAnimate --background --python tests/test_armature_above_deform.py
"""

import math

import oanim

ops = oanim.ops

CAGE = [(0.2, -0.2), (0.8, -0.2), (0.8, 0.2), (0.2, 0.2)]
CREASES = [(0.35, -0.1), (0.5, 0.05), (0.65, -0.05)]
TURN = 0.6


def find(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def drawing(name, points, closed):
    ops.layer.new()
    oanim.data.layers.active.name = name
    oanim.data.layers.active.add_curve(points, closed=closed, fill=closed)
    return find(name)


def into(layer, rig):
    oanim.data.layers.active = layer
    assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
    oanim.data.layers.active = find(layer.name)
    assert ops.layer.parent_bone_set(bone="Leg") == {'FINISHED'}
    return find(layer.name)


def shown(layer):
    return [layer.to_document(q) for q in layer.evaluated()[0]]


def turned(p, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


# --- A drawing bent by a cage, moved into the bone layer the cage's bone is in: the bone moves it once -----------------
ops.wm.read_homefile(confirmed="1")
doc = oanim.data.document
doc.auto_freeze_keys = False
doc.frame_current = 0
ops.layer.new_bone()
rig = oanim.data.layers.active
assert ops.armature.bone_add(name="Leg", head_x="0.0", head_y="0.0", tail_x="1.0", tail_y="0.0", parent="") == {
    'FINISHED'}
cage = into(drawing("Cage", CAGE, True), rig)
oanim.data.layers.active = rig
creases = drawing("Creases", CREASES, False)
assert creases.modifiers == [], "drawn outside the bone layer"
assert ops.object.modifier_add(type="CAGE_DEFORM") == {'FINISHED'}
creases.modifier_set(0, layer="Cage", shape=cage.shapes[0][0], cage_method="ENVELOPE")
creases = into(creases, rig)
assert [m["type"] for m in creases.modifiers] == ["ARMATURE", "CAGE_DEFORM"], creases.modifiers

doc.auto_key = True
doc.frame_current = 10
rig.bone_set("Leg", angle=TURN)
doc.frame_current = 11
doc.frame_current = 10
# The cage turns with the bone; the creases inside it turn with it, once.
angle = math.atan2(shown(cage)[0][1], shown(cage)[0][0]) - math.atan2(CAGE[0][1], CAGE[0][0])
assert abs(abs(angle) - TURN) < 1e-3, ("the cage turns with its bone", angle)
off = max(math.dist(p, turned(q, angle)) for p, q in zip(shown(creases), CREASES))
assert off < 1e-3, ("the creases turn with the cage, once", off)

print("armature above deform: ok")
