"""Handles through a deform, as the viewport shows them: the edit wire fits each bent segment's handle lengths so the
line follows the bend, but each handle is drawn and picked as bent at its own point, so moving a point leaves its
neighbours' handles where they were (only its own move), while the line still takes the fit.

Run with:  OpenAnimate --background --python tests/test_handles_shown_bent.py
"""

import math

import oanim

ops = oanim.ops
doc = oanim.data.document
layers = oanim.data.layers
wm = oanim.wm
doc.auto_key = True
doc.frame_current = 0

ops.layer.new()
grid = layers.active
grid.name = "Grid"
assert grid.add_primitive("GRID", [(-1, -1), (1, 1)], columns=3, rows=3)
ops.layer.new()
art = layers.active
art.name = "Brow"
art.add_curve([(-0.6, -0.1), (0.0, 0.45), (0.6, -0.05)])
assert ops.object.modifier_add(type="MESH_DEFORM") == {'FINISHED'}
art.modifier_set(0, curve_method="SMOOTH", cage_method="MEAN_VALUE", layer="Grid", shape=grid.shapes[0][0],
                 precision=0.0)

# The grid bent unevenly on frame 10, so each segment bends and the wire refits it.
doc.frame_current = 10
for i, p in enumerate(grid.points):
    grid.set_point(i, (p[0] * 1.2 + 0.25 * math.sin(p[1] * 2.0), p[1] + 0.3 * math.sin(p[0] * 2.5)))
doc.frame_current = 11
doc.frame_current = 10
layers.active = art


def close(a, b, eps=1e-5):
    return all(abs(x - y) < eps for x, y in zip(a, b))


ends = wm.handle_ends_shown(art)
wire = art.evaluated_handles(0, shown=True)
ops.mesh.select_none()
art.select_points([0])
assert ops.mesh.translate(move_x="0.15", move_y="0.1") == {'FINISHED'}
ends_after = wm.handle_ends_shown(art)
wire_after = art.evaluated_handles(0, shown=True)

# The line refits: the middle point's in handle, on the segment from the moved point, changes length.
assert not close(wire[1][1], wire_after[1][1], 1e-4), ("the wire still fits the bent segment", wire[1][1], wire_after[1][1])
# Shown, it stays put: both of the middle point's handles, and the far point's.
assert close(ends[1][0], ends_after[1][0]), ("a neighbour's handle doesn't move", ends[1][0], ends_after[1][0])
assert close(ends[1][1], ends_after[1][1]) and close(ends[2][0], ends_after[2][0]) and close(ends[2][1], ends_after[2][1])
# The moved point's own handles go with it.
assert not close(ends[0][1], ends_after[0][1], 1e-3)

print("handles shown bent: ok")
