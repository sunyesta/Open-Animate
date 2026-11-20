"""F on a whole loop makes a shape of it, as Blender's F makes a face and Moho's Create Shape: a loop with no fill
round it gets a new shape in the draw style (filled and outlined), a line all the way round it is filled. Merging an
open curve's two ends closes it, so the loop is one. A file saved before that, its curve ending on its first point
again, is closed by F too.

Run with:  OpenAnimate --background --python tests/test_fill_loop.py
"""

import json
import os
import tempfile
import zipfile

import oanim

ops, L = oanim.ops, oanim.data.layers

SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def scene():
    ops.wm.read_homefile(confirmed="1")
    return L.active


def bare_curve(layer, points, closed=False):
    """A curve with no shape on it, as points added one by one (E) leave it."""
    layer.add_curve(points, closed=closed)
    ops.mesh.select_all()
    assert ops.mesh.delete_shape() == {'FINISHED'}
    assert layer.shape_count == 0 and layer.point_count == len(points)


def closed(layer, curve=0):
    return layer.shown()[1][curve][1]


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


# --- Merging an open curve's two ends closes it ---------------------------------------------------------------------
layer = scene()
bare_curve(layer, SQUARE + [(0.05, 0.05)])
ops.mesh.select_none()
layer.select_points([0, 4])
assert ops.mesh.merge() == {'FINISHED'}
assert layer.point_count == 4 and layer.curve_count == 1
assert closed(layer), "a loop"
assert len(layer.curve_points(0)) == 4, ("its last point its first, once", layer.curve_points(0))
# Nothing was on it: it shows as a shape now, filled and outlined.
assert layer.shape_count == 1 and layer.shape_style(0)["has_fill"] and layer.shape_style(0)["has_outline"], layer.shapes
assert layer.shape_contains(0, (0.5, 0.5))
# A line along it goes round with it, the segment into the merged end too: F fills that line.
layer = scene()
layer.add_curve(SQUARE + [(0.05, 0.05)])
assert layer.shape_count == 1
ops.mesh.select_none()
layer.select_points([0, 4])
assert ops.mesh.merge() == {'FINISHED'}
assert closed(layer) and layer.shape_count == 1
ops.mesh.select_all()
assert ops.mesh.make_segment() == {'FINISHED'}
assert layer.shape_count == 1 and layer.shape_style(0)["has_fill"], layer.shapes
assert layer.shape_contains(0, (0.5, 0.5))
# A short one (two points left) can't go round.
layer = scene()
bare_curve(layer, [(0.0, 0.0), (1.0, 0.0), (0.02, 0.0)])
layer.select_points([0, 2])
ops.mesh.merge()
assert all(not c[1] for c in layer.shown()[1]), layer.shown()[1]

# --- F on a line's two ends closes it: with nothing on it, a shape fills it ------------------------------------------
layer = scene()
oanim.wm.set_draw(fill_color=(0.3, 0.5, 0.7, 1.0))
bare_curve(layer, SQUARE)
ops.mesh.select_none()
layer.select_points([0, 3])
assert ops.mesh.make_segment() == {'FINISHED'}
assert closed(layer) and layer.shape_count == 1, layer.shapes
look = layer.shape_style(0)
assert look["has_fill"] and look["has_outline"] and close(look["fill"], (0.3, 0.5, 0.7, 1.0)), look
assert layer.shape_contains(0, (0.5, 0.5))
ops.ed.undo()
assert not closed(layer) and layer.shape_count == 0, "one undo step"
# A line along it runs on round it and fills (as it always has), with no second shape.
layer = scene()
layer.add_curve(SQUARE)
ops.mesh.select_none()
layer.select_points([0, 3])
assert ops.mesh.make_segment() == {'FINISHED'}
assert closed(layer) and layer.shape_count == 1 and layer.shape_style(0)["has_fill"], layer.shapes

# --- F on the loop: a new shape, filled and outlined in the draw style ------------------------------------------------
layer = scene()
oanim.wm.set_draw(fill_color=(0.2, 0.6, 0.4, 1.0), line_color=(0.1, 0.1, 0.3, 1.0))
bare_curve(layer, SQUARE, closed=True)
ops.mesh.select_all()
assert ops.mesh.make_segment() == {'FINISHED'}
assert layer.shape_count == 1, layer.shapes
look = layer.shape_style(0)
assert look["has_fill"] and look["has_outline"], look
assert close(look["fill"], (0.2, 0.6, 0.4, 1.0)) and close(look["line"], (0.1, 0.1, 0.3, 1.0)), look
assert layer.shape_contains(0, (0.5, 0.5))
names, at = oanim.wm.undo_history()
assert names[at] == "Fill Loop", (names, at)
ops.ed.undo()
assert layer.shape_count == 0, "undone"
ops.ed.redo()
assert layer.shape_count == 1
# Pressed again: it is filled, nothing to do.
shown = oanim.wm.banner_report()[0]
assert ops.mesh.make_segment() == {'CANCELLED'} and layer.shape_count == 1
assert oanim.wm.banner_report()[0] > shown
# Not every point of the loop: nothing.
layer = scene()
bare_curve(layer, SQUARE, closed=True)
ops.mesh.select_none()
layer.select_points([0, 1, 2])
assert ops.mesh.make_segment() == {'CANCELLED'} and layer.shape_count == 0
# An open curve isn't a loop.
layer = scene()
bare_curve(layer, SQUARE)
ops.mesh.select_all()
assert ops.mesh.make_segment() == {'CANCELLED'} and layer.shape_count == 0

# --- A line all the way round it is filled, not doubled ----------------------------------------------------------------
layer = scene()
layer.add_curve(SQUARE, closed=True)
assert layer.shape_count == 1 and not layer.shape_style(0)["has_fill"]
ops.mesh.select_all()
assert ops.mesh.make_segment() == {'FINISHED'}
assert layer.shape_count == 1 and layer.shape_style(0)["has_fill"], layer.shapes

# --- Two loops: each filled, then one shape of both, the inner one a hole ---------------------------------------------
layer = scene()
bare_curve(layer, SQUARE, closed=True)
layer.add_curve([(0.3, 0.3), (0.7, 0.3), (0.7, 0.7), (0.3, 0.7)], closed=True)
ops.mesh.select_all()
assert ops.mesh.delete_shape() == {'FINISHED'}
ops.mesh.select_all()
assert ops.mesh.make_segment() == {'FINISHED'}
assert layer.shape_count == 1, layer.shapes
assert layer.shape_contains(0, (0.1, 0.1)) and not layer.shape_contains(0, (0.5, 0.5))

# --- A file whose loop ends on its first point again (merged before merging closed it) --------------------------------
layer = scene()
bare_curve(layer, SQUARE + [(0.05, 0.05)])
folder = tempfile.mkdtemp()
path = os.path.join(folder, "loop.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
with zipfile.ZipFile(path) as z:
    files = {n: z.read(n) for n in z.namelist()}
doc = json.loads(files["document.json"])
drawing = [l for l in doc["document"]["layers"] if l.get("drawing", {}).get("curves")][0]["drawing"]
curve = drawing["curves"][0]
assert not curve["closed"] and len(curve["points"]) == 5
curve["points"][4]["point"] = curve["points"][0]["point"]
drawing["points"].pop(4)
files["document.json"] = json.dumps(doc).encode("utf-8")
with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
    for n, data in files.items():
        z.writestr(n, data)
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
layer = [l for l in L.all() if l.type == 'VECTOR'][0]
L.active = layer
assert layer.point_count == 4 and layer.shape_count == 0
ops.mesh.select_all()
assert ops.mesh.make_segment() == {'FINISHED'}, oanim.wm.banner_report()
assert layer.shape_count == 1 and layer.shape_style(0)["has_fill"] and closed(layer)
assert len(layer.curve_points(0)) == 4, layer.curve_points(0)
assert layer.shape_contains(0, (0.5, 0.5))

print("fill loop: ok")
