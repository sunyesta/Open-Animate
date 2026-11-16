"""Point opacity (MeshPoint::opacity): Opacity's pressure toggle makes a freehand line fainter where the pen pressed
lightly, each point's opacity multiplying the line's (Min Opacity the faintest), not animated. Saved and opened,
carried through subdivide and Symmetrize, drawn by the solid line's triangles and a brush's dabs, and Mean Opacity
beside Mean Radius.

The header's toggle and the Properties field need the window: checked live on a private copy.

Run with:  OpenAnimate --background --python tests/test_point_opacity.py
"""

import os
import tempfile

import oanim

wm = oanim.wm
ops = oanim.ops


def close(a, b, tolerance=1e-4):
    return abs(a - b) < tolerance


def fresh():
    ops.wm.read_homefile(confirmed="1")
    ops.layer.new()
    doc = oanim.data.document
    doc.frame_current = 0
    ops.draw.preset_load(name="Ink")
    return oanim.data.layers.active, 2.0 / doc.height


def stroke_text(path, pressure, count=80, seconds=0.5):
    rows = []
    for i in range(count):
        u = i / (count - 1)
        x, y = path(u)
        rows.append("%f,%f,%f,%f" % (x, y, pressure(u), u * seconds))
    return ";".join(rows)


# A line pressed lightly at its start, hard at its end.
ramp = stroke_text(lambda u: (-0.5 + u, 0.1), lambda u: 0.05 + 0.95 * u)

# --- The engine: pressure sets each point's opacity through the pressure curve, from Min Opacity -----------------------
samples = [(i * 2.0, 0.0, 0.05 + 0.95 * i / 99.0, 0.0, 0.0, i * 0.004) for i in range(100)]
plain = wm.ink_stroke(samples, pixel=1.0, line_width=10.0, stabilizer="OFF", pressure_smoothing=0.0)
assert all(o == 1.0 for o in plain["opacity"]) and all(o == 1.0 for o in plain["knot_opacity"]), "off: solid"
faded = wm.ink_stroke(samples, pixel=1.0, line_width=10.0, stabilizer="OFF", opacity_pressure=True, min_opacity=0.2,
                      pressure_smoothing=0.0)
o = faded["opacity"]
assert o[0] < 0.35 and o[-1] > 0.95, (o[0], o[-1])
assert all(b >= a - 1e-4 for a, b in zip(o, o[1:])), "pressing harder, more solid"
assert min(o) >= 0.2 - 1e-6, "never fainter than Min Opacity"
k = faded["knot_opacity"]
assert k[0] < 0.35 and k[-1] > 0.95, k
# The fit keeps it: a straight line pressed hard in its middle only needs a point there for its opacity.
swell = [(i * 2.0, 0.0, 1.0 - abs(i - 49.5) / 49.5 * 0.95, 0.0, 0.0, i * 0.004) for i in range(100)]
even = wm.ink_stroke(swell, pixel=1.0, line_width=10.0, stabilizer="OFF", use_pressure=False, pressure_smoothing=0.0)
swelled = wm.ink_stroke(swell, pixel=1.0, line_width=10.0, stabilizer="OFF", use_pressure=False, pressure_smoothing=0.0,
                        opacity_pressure=True, min_opacity=0.0)
assert len(even["knots"]) == 2, "a straight line of one width: its two ends"
k = swelled["knot_opacity"]
assert len(k) >= 3 and max(k) > 0.9 and k[0] < 0.2 and k[-1] < 0.2, k
# The width as it was: Opacity's pressure doesn't touch Size.
assert [p[2] for p in faded["points"]] == [p[2] for p in plain["points"]]
# Off, Size's pressure still on alone.
alone = wm.ink_stroke(samples, pixel=1.0, line_width=10.0, stabilizer="OFF", opacity_pressure=True, use_pressure=False)
assert alone["opacity"][0] < 0.5 and all(close(p[2], 1.0) for p in alone["points"]), "each toggle on its own"

# --- Drawn: the points take it; off, every point is solid ---------------------------------------------------------------
layer, pixel = fresh()
assert not wm.draw_settings()["opacity_pressure"], "off by default"
ops.draw.stroke(samples=ramp, pixel=pixel)
assert all(o == 1.0 for o in layer.opacities), layer.opacities
wm.set_draw(opacity_pressure=True, min_opacity=0.1)
first_count = len(layer.opacities)
ops.draw.stroke(samples=ramp, pixel=pixel)
line = layer.opacities[first_count:]
assert len(line) >= 2 and line[0] < 0.4 and line[-1] > 0.95, line
# Undo takes the line and its opacities away together.
count = layer.point_count
ops.ed.undo()
assert layer.point_count < count and all(o == 1.0 for o in layer.opacities)
ops.ed.redo()
assert min(layer.opacities) < 0.4
wm.set_draw(opacity_pressure=False)

# --- Not animated: the same on another frame -----------------------------------------------------------------------------
before = list(layer.opacities)
oanim.data.document.frame_current = 6
assert layer.opacities == before
oanim.data.document.frame_current = 0

# --- Saved and opened (written only where it isn't 1) --------------------------------------------------------------------
path = os.path.join(tempfile.mkdtemp(prefix="oanim_point_opacity_"), "opacity.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {"FINISHED"}
ops.wm.read_homefile(confirmed="1")
assert ops.wm.open_mainfile(filepath=path) == {"FINISHED"}
layer = oanim.data.layers.active
assert all(close(a, b, 1e-6) for a, b in zip(layer.opacities, before)) and len(layer.opacities) == len(before)

# --- Drawn: the solid line's triangles fade where its points do ----------------------------------------------------------
layer, pixel = fresh()
wm.set_draw(opacity_pressure=True, min_opacity=0.1)
ops.draw.stroke(samples=ramp, pixel=pixel)
wm.set_draw(opacity_pressure=False)
tris = oanim._oanim.layer_shape_stroke(layer.id, 0)
assert tris, "triangles"
left = [a for x, y, a in tris if x < -0.45]
right = [a for x, y, a in tris if x > 0.45]
assert left and right and max(left) < 0.45 and min(right) > 0.9, (max(left), min(right))
ops.layer.new()
solid = oanim.data.layers.active
ops.draw.stroke(samples=ramp, pixel=pixel)
assert all(a > 0.99 for x, y, a in oanim._oanim.layer_shape_stroke(solid.id, 0)), "a line of solid points draws as before"

# --- Mean Opacity: the selected points' mean, each moved by as much --------------------------------------------------------
layer, pixel = fresh()
wm.set_draw(opacity_pressure=True, min_opacity=0.1)
ops.draw.stroke(samples=ramp, pixel=pixel)
wm.set_draw(opacity_pressure=False)
ops.mesh.select_none()
assert layer.mean_opacity is None
was = list(layer.opacities)
layer.select_points([0, 1])
mean = (was[0] + was[1]) / 2.0
assert close(layer.mean_opacity, mean)
layer.mean_opacity = mean + 0.1
assert close(layer.opacities[0], min(was[0] + 0.1, 1.0)) and close(layer.opacities[1], min(was[1] + 0.1, 1.0))
assert all(close(a, b) for a, b in list(zip(layer.opacities, was))[2:]), "the others as they were"
layer.mean_opacity = 5.0
assert all(o <= 1.0 for o in layer.opacities), "kept to 1"

# --- Subdivide: a new point between two takes the opacity the line had there -------------------------------------------
layer, pixel = fresh()
ops.draw.quick_shape(shape="LINE", a="-0.5,0", b="0.5,0", pixel=pixel)
ops.mesh.select_none()
layer.select_points([0])
layer.mean_opacity = 0.2
layer.select_points([0, 1])
assert ops.mesh.subdivide() == {"FINISHED"}
assert layer.point_count == 3
assert close(layer.opacities[2], 0.6, 1e-3), layer.opacities

# --- Hold to Shape keeps the stroke's opacity ---------------------------------------------------------------------------
layer, pixel = fresh()
assert ops.draw.quick_shape(shape="LINE", a="-0.5,0", b="0.5,0", pixel=pixel, opacity="0.3") == {"FINISHED"}
assert all(close(o, 0.3) for o in layer.opacities), layer.opacities
assert wm.redo_last(opacity="0.6") == "FINISHED" and all(close(o, 0.6) for o in layer.opacities)

# --- Symmetrize: the mirrored point takes its partner's opacity ------------------------------------------------------------
layer, pixel = fresh()
ops.draw.quick_shape(shape="LINE", a="-0.5,0.2", b="-0.1,0.3", pixel=pixel, opacity="0.4")
ops.draw.quick_shape(shape="LINE", a="0.5,0.2", b="0.1,0.3", pixel=pixel)
assert [round(o, 4) for o in layer.opacities] == [0.4, 0.4, 1.0, 1.0], layer.opacities
ops.mesh.select_all()
assert ops.mesh.symmetrize(direction="LEFT_TO_RIGHT") == {"FINISHED"}
assert layer.point_count == 4 and all(close(o, 0.4) for o in layer.opacities), layer.opacities

# --- A brushed line's dabs fade with the points ----------------------------------------------------------------------------
layer, pixel = fresh()
library = tempfile.mkdtemp(prefix="oanim_point_opacity_brush_")
ops.preferences.asset_library_set(directory=library)
assert ops.brush.preset_load(preset="Hard Round", library="1", target="TOOL") == {"FINISHED"}
wm.set_draw(opacity_pressure=True, min_opacity=0.1)
ops.draw.stroke(samples=ramp, pixel=pixel)
wm.set_draw(opacity_pressure=False)
dabs = oanim._oanim.layer_shape_dabs(layer.id, 0)
first = [a for x, y, a in dabs if x < -0.4]
last = [a for x, y, a in dabs if x > 0.4]
assert first and last and max(first) < 0.5 * max(last), (max(first), max(last))

# --- A pen saves them -------------------------------------------------------------------------------------------------------
layer, pixel = fresh()
library = tempfile.mkdtemp(prefix="oanim_point_opacity_pen_")
ops.preferences.asset_library_set(directory=library)
wm.set_draw(opacity_pressure=True, min_opacity=0.35)
ops.draw.preset_save(name="Faint Pen")
ops.preferences.asset_library_set(directory=library)
saved = {p["name"]: p for p in wm.draw_presets()}["Faint Pen"]
assert saved["opacity_pressure"] and close(saved["min_opacity"], 0.35), saved
ops.draw.preset_load(name="Ink")
assert not wm.draw_settings()["opacity_pressure"]

print("point opacity: ok")
