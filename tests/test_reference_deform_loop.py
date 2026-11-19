"""A drawing bent by a reference of itself is a loop, and the deform does nothing. The reference shows the drawing's own
points, so its change of shape bent the drawing a second time (a corner moved 0.28 moved the outline 0.28 more), and
each frame was slow to work out. The same through a group's deform whose cage is such a reference, and for another
reference of the same original bent by it (both show the original).

Run with:  OpenAnimate --background --python tests/test_reference_deform_loop.py
"""

import math

import oanim

ops, L = oanim.ops, oanim.data.layers
SQ = [(0.2, -0.2), (0.8, -0.2), (0.8, 0.2), (0.2, 0.2)]
CAGE_METHODS = ("ENVELOPE", "MEAN_VALUE", "OUTLINE", "RIGID")


def far(a, b):
    return max(max(min(math.dist(p, q) for q in b) for p in a), max(min(math.dist(p, q) for q in a) for p in b))


def find(name):
    return next(l for l in L.all() if l.name == name)


def scene(match=True):
    """Orig, a square, and Ref, a reference of it; Orig's corner moved on frame 10. Orig's outline there, alone."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new()
    o = L.active
    o.name = "Orig"
    o.add_curve(SQ, closed=True, fill=True)
    assert ops.layer.make_reference() == {'FINISHED'}
    L.active.name = "Ref"
    if not match:
        assert ops.layer.reference_set(match_original="0") == {'FINISHED'}
    doc.auto_key = True
    doc.frame_current = 10
    L.active = o
    o.set_point(2, (1.0, 0.4))
    doc.frame_current = 11
    doc.frame_current = 10
    return doc, o, o.evaluated_outline(0, 64)[0]


def cage(layer, shape_layer):
    L.active = layer
    assert ops.object.modifier_add(type="CAGE_DEFORM") == {'FINISHED'}
    layer.modifier_set(len(layer.modifiers) - 1, layer=shape_layer.name, shape=shape_layer.shapes[0][0])
    return len(layer.modifiers) - 1


def unmoved(doc, deformed, index, layers, alone, what):
    for method in CAGE_METHODS:
        deformed.modifier_set(index, cage_method=method)
        doc.frame_current = 0
        doc.frame_current = 10
        for layer in layers:
            moved = far(alone, layer.evaluated_outline(0, 64)[0])
            assert moved < 1e-4, (what, layer.name, method, moved)


# --- A drawing whose Cage Deform's cage is a reference of it: nothing bends ----------------------------------------------
for match in (True, False):
    doc, o, alone = scene(match)
    unmoved(doc, o, cage(o, find("Ref")), [o], alone, ("bent by a reference of itself", match))

# --- A group's Cage Deform whose cage is a reference of a drawing in it: that drawing and the reference stay as they are --
doc, o, alone = scene()
doc.frame_current = 0
assert ops.layer.new_group() == {'FINISHED'}
group = L.active
group.name = "Group"
for name in ("Orig", "Ref"):
    L.active = find(name)
    assert ops.layer.move_to_group(group=str(group.id)) == {'FINISHED'}
group = find("Group")
unmoved(doc, group, cage(group, find("Ref")), [find("Orig"), find("Ref")], alone, "a group's deform on a reference of it")

# --- Another reference of the same original, bent by the first: it shows the original, so it stays as the original -----
doc, o, alone = scene()
doc.frame_current = 0
L.active = o
assert ops.layer.make_reference() == {'FINISHED'}
L.active.name = "Ref2"
twin = find("Ref2")
assert ops.layer.reference_set(match_original="0") == {'FINISHED'}
unmoved(doc, twin, cage(twin, find("Ref")), [twin], alone, "a reference bent by another of its original")

print("reference deform loop: ok")
