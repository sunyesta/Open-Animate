"""What a reference shows is kept when its offsets go into points: Break Reference, Push to Original, and deleting its
original (which does what Break Reference does). A handle's keyed offset adds as a straight move between its keys, but
the keys it went into turn and stretch the handle, so between them the handle moved (0.12 on frame 5); deleting the
original only let go of it, dropping the Resample it showed through (16 points became 4) and its keyed offsets.

Run with:  OpenAnimate --background --python tests/test_reference_keeps_shown.py
"""

import math

import oanim

ops, L = oanim.ops, oanim.data.layers
SQ = [(0.2, -0.2), (0.8, -0.2), (0.8, 0.2), (0.2, 0.2)]
FRAMES = range(0, 13)


def find(name):
    return next(l for l in L.all() if l.name == name)


def handle_scene():
    """A line and a reference of it with Edit Points, its point 1's out handle offset keyed one way on frame 1 and the
    other on frame 10. The handle as shown on every frame."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new()
    L.active.name = "Orig"
    L.active.add_curve([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], closed=False, fill=False)
    assert ops.layer.make_reference() == {'FINISHED'}
    ref = L.active
    ref.name = "Ref"
    assert ops.layer.reference_set(edit_points="1") == {'FINISHED'}
    doc.auto_key = True
    doc.frame_current = 1
    ref.move_handle(0, 1, "OUT", (1.3, 0.3))
    doc.frame_current = 10
    ref.move_handle(0, 1, "OUT", (0.7, 0.3))
    doc.frame_current = 11
    return doc, ref, shown_handles(doc, "Ref")


def shown_handles(doc, name):
    out = {}
    for f in FRAMES:
        doc.frame_current = f
        out[f] = find(name).curve_handles(0)[1][2]
    return out


def same_handles(a, b, what):
    worst = max(math.dist(a[f], b[f]) for f in FRAMES)
    assert worst < 1e-4, (what, worst)


# --- Break Reference: the handle shows as it did on every frame, between its keys too ---------------------------------
doc, ref, before = handle_scene()
L.active = ref
assert ops.layer.break_reference() == {'FINISHED'}
same_handles(before, shown_handles(doc, "Ref"), "Break Reference kept the handle")

# --- Push to Original: the original takes the handle as the reference showed it, the reference showing it still -------
doc, ref, before = handle_scene()
L.active = ref
assert ops.layer.reference_apply(kind="POINTS") == {"FINISHED"}
same_handles(before, shown_handles(doc, "Ref"), "the reference after Push to Original")
same_handles(before, shown_handles(doc, "Orig"), "the original after Push to Original")

# --- Deleting the original: the reference keeps what it showed, the original's Resample and its keyed offsets -----------
ops.wm.read_homefile(confirmed="1")
doc = oanim.data.document
doc.auto_freeze_keys = False
doc.frame_current = 0
ops.layer.new()
orig = L.active
orig.name = "Orig"
orig.add_curve(SQ, closed=True, fill=True)
assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
orig.modifier_set(0, split="COUNT", pieces=4)
assert ops.layer.make_reference() == {'FINISHED'}
ref = L.active
ref.name = "Ref"
assert ops.layer.reference_set(edit_points="1") == {'FINISHED'}
doc.auto_key = True
doc.frame_current = 10
L.active = orig
orig.set_point(2, (1.0, 0.4))
for f, d in ((1, (0.0, 0.1)), (10, (0.1, -0.1))):
    doc.frame_current = f
    L.active = ref
    ops.mesh.select_none()
    ref.select_points([1])
    assert ops.mesh.translate(move_x=repr(d[0]), move_y=repr(d[1])) == {'FINISHED'}


def shows():
    out = {}
    for f in FRAMES:
        doc.frame_current = f
        out[f] = find("Ref").evaluated()[0]
    return out


before = shows()
assert len(before[5]) == 16, "it shows the original's Resample"
L.active = orig
doc.frame_current = 0
assert ops.layer.delete() == {'FINISHED'}
assert find("Ref").reference_source is None, "an ordinary layer now"
after = shows()
for f in FRAMES:
    assert len(after[f]) == len(before[f]), ("the Resample it showed is kept", f, len(before[f]), len(after[f]))
    off = max(math.dist(p, q) for p, q in zip(before[f], after[f]))
    assert off < 1e-4, ("the reference shows as it did, its keyed offset too", f, off)
# One undo step brings the original back and the reference with it.
ops.ed.undo()
assert find("Ref").reference_source is not None and find("Orig")
again = shows()
assert max(math.dist(p, q) for f in FRAMES for p, q in zip(before[f], again[f])) < 1e-6, "undone exactly"

print("reference keeps shown: ok")
