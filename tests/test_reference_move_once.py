"""A reference's points moved in the same edit as its original's (a group with Edit Descendants moved, or both layers
picked) move once: the original's move already carries the reference, so its offset is only what is left to where the
edit put its points. Turned about a pivot with the reference placed away from its original, its points land where an
ordinary layer's would. Moved on their own they still take the whole move, and a locked reference moved with its
original says nothing about being locked.

Run with:  OpenAnimate --background --python tests/test_reference_move_once.py
"""

import math

import oanim

ops, L = oanim.ops, oanim.data.layers
CURVE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]


def scene(frame=0, edit_points=True):
    """A group holding a drawing, a reference of it placed 3 to the right, and an ordinary drawing like it there too."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_key = True
    doc.frame_current = 0
    orig = L.active
    orig.name = "Original"
    orig.add_curve(CURVE)
    ops.mesh.select_none()
    assert ops.layer.make_reference() == {'FINISHED'}
    ref = L.active
    if edit_points:
        assert ops.layer.reference_set(edit_points="1") == {'FINISHED'}
    ref.location_x = 3.0
    ops.layer.new()
    plain = L.active
    plain.name = "Plain"
    plain.add_curve(CURVE)
    plain.location_x = 3.0
    ops.mesh.select_none()
    for l in (orig, ref, plain):
        l.selected = True
    L.active = orig
    assert ops.layer.group() == {'FINISHED'}
    group = L.active
    assert group.edit_descendants and ref.parent == group and orig.parent == group
    doc.frame_current = frame
    return doc, group, orig, ref, plain


def points(layer):
    return [tuple(p[:2]) for p in layer.points]


def settle(doc):
    f = doc.frame_current
    doc.frame_current = f + 1
    doc.frame_current = f


def same(a, b, eps=1e-4):
    return all(math.dist(p, q) < eps for p, q in zip(a, b))


# --- The group moved: the reference moves once, on the setup frame and on a later one ------------------------------
for frame in (0, 10):
    doc, group, orig, ref, plain = scene(frame)
    L.active = group
    assert ops.mesh.select_all() == {'FINISHED'}
    assert ops.mesh.translate(move_x="0.5", move_y="0.25") == {'FINISHED'}
    settle(doc)
    moved = [(x + 0.5, y + 0.25) for x, y in CURVE]
    assert same(points(orig), moved), (frame, points(orig))
    assert same(points(ref), moved), ("moved once, with its original", frame, points(ref))
    assert ref.reference_overrides()["points"] == {}, ("no offset of its own", ref.reference_overrides()["points"])

# --- Turned about a pivot: its points land where an ordinary layer's do --------------------------------------------
doc, group, orig, ref, plain = scene(10)
L.active = group
assert ops.mesh.select_all() == {'FINISHED'}
assert ops.mesh.rotate(angle="30") == {'FINISHED'}
settle(doc)
assert not same(points(plain), CURVE), "the turn moved them"
assert same(points(ref), points(plain)), ("where the turn put them", points(ref), points(plain))
handles = lambda l: [h for _, h_in, h_out in l.curve_handles(0) for h in (h_in, h_out)]
assert same(handles(ref), handles(plain)), ("its handles turned once", handles(ref), handles(plain))

# --- Moved on their own, the reference's points take the whole move -----------------------------------------------
doc, group, orig, ref, plain = scene(0)
L.active = ref
ops.mesh.select_none()
assert ops.mesh.select_all() == {'FINISHED'}
assert ops.mesh.translate(move_x="0.5") == {'FINISHED'}
settle(doc)
assert same(points(orig), CURVE) and same(points(ref), [(x + 0.5, y) for x, y in CURVE]), (points(orig), points(ref))

# --- Locked, moved with its original: once, and no word about its points being locked -------------------------------
doc, group, orig, ref, plain = scene(0, edit_points=False)
L.active = group
assert ops.mesh.select_all() == {'FINISHED'}
shown = oanim.wm.banner_report()[0]
assert ops.mesh.translate(move_x="0.5") == {'FINISHED'}
settle(doc)
assert same(points(ref), [(x + 0.5, y) for x, y in CURVE]), points(ref)
assert oanim.wm.banner_report()[0] == shown, ("nothing refused", oanim.wm.banner_report())

print("reference move once: ok")
