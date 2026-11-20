"""Key Together on a reference keeps the layer channels it follows following: a filler key would take one over at
the frame shown's value, so the original's animation stopped showing on the reference's other frames.

Run with:  OpenAnimate --background --python tests/test_key_together_reference.py
"""

import oanim

ops, L, doc = oanim.ops, oanim.data.layers, oanim.data.document


def scene():
    ops.wm.read_homefile(confirmed="1")
    orig = L.active
    orig.add_curve([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    assert ops.layer.make_reference() == {'FINISHED'}
    return orig, L.active


def poses(orig, ref, frames=(0, 53)):
    out = {}
    for f in frames:
        doc.frame_current = f
        out[f] = ([(round(p[0], 5), round(p[1], 5)) for p in ref.shown()[0]],
                  round(ref.location_y, 5), round(ref.scale_x, 5), round(orig.location_y, 5))
    return out


# --- The original moves on frame 53, the reference its own size there: Key Together leaves the move followed --------
orig, ref = scene()
doc.frame_current = 53
ref.scale_x = ref.scale_x - 0.41
orig.location_y = orig.location_y + 0.0735
doc.frame_current = 0
doc.frame_current = 53
before = poses(orig, ref)
assert before[0][1] == 0.0 and before[53][1] == 0.0735, before
doc.frame_current = 53
assert ops.anim.key_together_set(layer=str(ref.id), on="1") == {'FINISHED'}
assert poses(orig, ref) == before, (before, poses(orig, ref))
assert "position" not in ref.reference_overrides()["channels"], ref.reference_overrides()
# Moved again later, the original still carries the reference.
doc.frame_current = 20
orig.location_y = 0.3
doc.frame_current = 0
doc.frame_current = 20
assert abs(ref.location_y - orig.location_y) < 1e-5, (ref.location_y, orig.location_y)

print("key together reference: ok")
