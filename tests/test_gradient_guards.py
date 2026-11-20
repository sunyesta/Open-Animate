"""Gradient layers kept whole at their edges: a number no place reaches (NaN, inf) shows nothing rather than crashing,
Resample and Bevel add no points to them, Move to Layer leaves them and the drawing moved from as they were, a
script's extra point is put back on any frame, a CANCELLED operator changes nothing, a hex colour is hex digits only,
and + puts the new stop on the tick as it is drawn on a bent gradient.

Run with:  OpenAnimate --background --python tests/test_gradient_guards.py
"""

import json
import math
import os
import tempfile
import zipfile

import oanim

ops, L = oanim.ops, oanim.data.layers
doc = oanim.data.document


def scene(**kw):
    ops.wm.read_homefile(confirmed="1")
    args = dict(x1="-1", y1="0", x2="1", y2="0")
    args.update(kw)
    assert ops.layer.new_gradient(**args) == {'FINISHED'}
    return L.active


def finite(color):
    return all(math.isfinite(c) for c in color)


# --- A NaN Squash isn't stored: the setter and the handle drag leave it as it was ------------------------------------
g = scene()
g.gradient_type = 'RADIAL'
g.gradient_squash = float('nan')
assert g.gradient["squash"] == 1.0, g.gradient["squash"]
g.gradient_squash = 1e30
assert g.gradient["squash"] == 100.0, g.gradient["squash"]
g.gradient_squash = 1.0
assert g.gradient_handle_drag(-1, float('nan'), 0.0) == 1.0
assert g.gradient["squash"] == 1.0
assert finite(g.gradient_sample(0.0, 0.3)["color"])
assert finite(g.gradient_sample(float('nan'), 0.3)["color"])

# --- A stop at NaN, or a file's at 1e39, shows nothing and doesn't crash ------------------------------------------------
g = scene()
g.set_point(0, (float('nan'), 0.0))
c = g.gradient_sample(0.0, 0.0)["color"]
assert finite(c) and c[3] == 0.0, c
assert len(g.gradient_image(8, 8)) == 8 * 8 * 4
g = scene()
folder = tempfile.mkdtemp()
a, b = os.path.join(folder, "a.oanim"), os.path.join(folder, "b.oanim")
assert ops.wm.save_as_mainfile(filepath=a) == {'FINISHED'}
d = json.loads(zipfile.ZipFile(a).read("document.json"))
layer = next(l for l in d["document"]["layers"] if "gradient" in l)
layer["drawing"]["points"][0]["pos"] = [1e39, 0.0]
layer["gradient"]["squash"] = 1e300
with zipfile.ZipFile(b, "w") as z:
    z.writestr("document.json", json.dumps(d))
assert ops.wm.open_mainfile(filepath=b) == {'FINISHED'}
g = next(l for l in L.all() if l.type == 'VECTOR' and l.is_gradient)
assert g.gradient["squash"] == 1.0, g.gradient["squash"]
c = g.gradient_sample(0.0, 0.0)["color"]
assert finite(c) and c[3] == 0.0, c
L.active = g
assert ops.gradient.stop_add() == {'CANCELLED'}

# --- Resample, Bevel and Resample Self leave a gradient's stops its only points -------------------------------------
g = scene(color1="#2040a0", color2="#ffe080")
before = g.gradient_sample(0.0, 0.3)["color"]
assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
g = L.active
after = g.gradient_sample(0.0, 0.3)["color"]
assert after[3] > 0.99 and all(abs(x - y) < 1e-4 for x, y in zip(before, after)), (before, after)
assert max(g.gradient_image(16, 9)[3::4]) == 255
assert len(g.gradient_places()["stops"]) == 2
g = scene()
assert ops.gradient.stop_add() == {'FINISHED'}
g = L.active
g.set_point(2, (0.0, 0.8))
ops.mesh.select_none()
g.select_points([2])
assert ops.mesh.peak() == {'FINISHED'}
assert ops.object.modifier_add(type="BEVEL") == {'FINISHED'}
g = L.active
g.modifier_set(0, amount=0.3)
assert g.gradient_sample(0.0, 0.3)["color"][3] > 0.99
assert len(g.gradient_places()["stops"]) == 3
ops.wm.read_homefile(confirmed="1")
ops.layer.new()
line = L.active
line.name = "Line"
line.add_curve([(-1.5, 0.0), (-0.5, 0.0), (0.5, 0.0), (1.5, 0.0)], closed=False, fill=False)
assert ops.layer.new_gradient(x1="-1", y1="0", x2="1", y2="0") == {'FINISHED'}
gn = L.active.name
assert ops.object.modifier_add(type="CURVE_DEFORM") == {'FINISHED'}
L[gn].modifier_set(0, layer="Line", shape=line.shapes[0][0], precision=0.0, resample_self=True)
assert L[gn].gradient_sample(0.0, 0.2)["color"][3] > 0.99

# --- Move to Layer into a gradient is refused, and out of one moves nothing -----------------------------------------
grad = scene()
gname, gid = grad.name, grad.id
assert ops.layer.new() == {'FINISHED'}
art = L.active
aname = art.name
art.add_curve([(0.0, 0.5), (0.5, 0.6), (0.8, 0.2)])
ops.mesh.select_all()
assert ops.mesh.move_to_layer(target=str(gid)) == {'CANCELLED'}
assert len(L[aname].points) == 3 and len(L[gname].points) == 2
L.active = L[gname]
ops.mesh.select_all()
assert ops.mesh.move_to_layer(target=str(art.id)) == {'CANCELLED'}
assert len(L[aname].points) == 3 and len(L[gname].points) == 2

# --- A script's extra point is put back on another frame too, the stops kept -----------------------------------------
g = scene()
was = g.gradient_sample(-0.5, 0.0)["color"]
doc.frame_current = 5
g.split_segment(0, 0, 0.5)
assert len(g.points) == 3
assert ops.gradient.stop_set(stop="1", color="#ffffff") == {'FINISHED'}
assert len(g.points) == 2 and len(g.gradient["stops"]) == 2, (g.points, g.gradient["stops"])
assert all(abs(c - 1.0) < 1e-6 for c in g.gradient["stops"][1]["color"][:3]), g.gradient["stops"]

# --- CANCELLED leaves the stops and picks as they were ----------------------------------------------------------------
g = scene()
assert ops.gradient.stop_add() == {'FINISHED'}
g = L.active
ops.gradient.pick(stop="0")
before = g.gradient
assert ops.gradient.span_set(span="0", midpoint="0.2", falloff="BAD") == {'CANCELLED'}
assert g.gradient["stops"][0]["midpoint"] == before["stops"][0]["midpoint"]
assert ops.gradient.pick(stop="1", span="99") == {'CANCELLED'}
assert g.gradient["active_stop"] == before["active_stop"]

# --- A hex colour is hex digits only --------------------------------------------------------------------------------
g = scene()
had = g.gradient["stops"][0]["color"]
for text in ("#-12345", "#+12345", "# 12345", "#12345g"):
    assert ops.gradient.stop_set(stop="0", color=text) == {'CANCELLED'}, text
assert g.gradient["stops"][0]["color"] == had
assert ops.gradient.stop_set(stop="0", color="#ff8000") == {'FINISHED'}
assert abs(g.gradient["stops"][0]["color"][1] - 128 / 255) < 1e-6

print("gradient guards: ok")
