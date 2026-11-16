"""Bugs a sweep of the draw tools found, each section its own scene: a split point's opacity, Simplify and Decimate
keeping the point a faded line's opacity needs, a Boolean merge keeping the lines' opacity, nan and huge numbers
refused by set_draw, Mean Opacity and Hold to Shape, and saved pens with a wrong-typed or huge key.

Run with:  OpenAnimate --background --python tests/test_draw_sweep_fixes.py
"""

import json
import math
import os
import tempfile

import oanim

wm = oanim.wm
ops = oanim.ops


def fresh():
    ops.wm.read_homefile(confirmed="1")
    ops.layer.new()
    doc = oanim.data.document
    doc.frame_current = 0
    doc.auto_key = False
    ops.draw.preset_load(name="Ink")
    return oanim.data.layers.active, 2.0 / doc.height


def ramp_text(pressure=lambda u: 0.8):
    return ";".join("%f,0.1,%f,%f" % (-0.5 + i / 79, pressure(i / 79), i / 79 * 0.5) for i in range(80))


def library_with(name, **changes):
    """A library holding the pen Good and a copy of it saved as `name` with `changes` written over its keys."""
    library = tempfile.mkdtemp(prefix="oanim_draw_sweep_")
    ops.preferences.asset_library_set(directory=library)
    ops.draw.preset_load(name="Ink")
    assert ops.draw.preset_save(name="Good") == {"FINISHED"}
    folder = os.path.join(library, "Draw Presets")
    with open(os.path.join(folder, "Good.oadraw")) as f:
        good = json.load(f)
    with open(os.path.join(folder, name + ".oadraw"), "w") as f:
        json.dump(dict(good, name=name, **changes), f)
    return library


# --- A split point takes the opacity the line shows where it splits, not the 1/32 sample's before it -------------------
layer, pixel = fresh()
ops.draw.quick_shape(shape="LINE", a="0,0", b="1,0", pixel=pixel)
ops.mesh.select_none(); layer.select_points([0]); layer.mean_opacity = 0.0
ops.mesh.select_none(); layer.select_points([1]); layer.mean_opacity = 1.0
ops.mesh.select_none()
d = layer.split_segment(0, 0, 0.53)
x = layer.points[d][0]
assert abs(layer.opacities[d] - x) < 0.005, (x, layer.opacities[d])


# --- Simplify and Decimate keep the point a faded line's opacity needs, as they keep a width's ---------------------------
def bump_line(kind):
    layer, pixel = fresh()
    layer.key_whole_drawing = False
    layer.add_curve([(x * 0.1 - 0.5, 0.0) for x in range(11)])
    for i in range(11 if kind != "none" else 0):
        ops.mesh.select_none(); layer.select_points([i])
        if kind == "opacity":
            layer.mean_opacity = 1.0 if i == 5 else 0.1
        else:
            layer.mean_radius = 1.0 if i == 5 else 0.1
    ops.mesh.select_all()
    return layer


w = bump_line("radius")
assert ops.sculpt.simplify(resolution="12") == {"FINISHED"}
assert max(w.radii) > 0.99, "the width's point stays"
o = bump_line("opacity")
assert ops.sculpt.simplify(resolution="12") == {"FINISHED"}
assert max(o.opacities) > 0.99, ("Simplify", o.opacities)
o = bump_line("opacity")
assert ops.mesh.decimate(ratio="0.5") == {"FINISHED"}
assert max(o.opacities) > 0.99, ("Decimate", o.opacities)
# A line of one opacity still simplifies to as few points as before.
plain = bump_line("none")
count = plain.point_count
assert ops.sculpt.simplify(resolution="12") == {"FINISHED"}
assert plain.point_count < count

# --- A Boolean merge of faded lines keeps their opacity on its outline -----------------------------------------------------
layer, pixel = fresh()
wm.set_draw(fill=True)
head = layer
head.name = "head"
ops.draw.quick_shape(shape="ELLIPSE", center="0,0", radii="0.3,0.3", pixel=pixel, opacity="0.3", radius="0.8")
ops.layer.new()
ear = oanim.data.layers.active
ear.name = "ear"
ops.draw.quick_shape(shape="ELLIPSE", center="0.4,0", radii="0.2,0.2", pixel=pixel, opacity="0.3", radius="0.8")
ops.layer.select_at(layer=str(head.id))
assert ops.object.modifier_add(type="BOOLEAN", targets="ear") == {"FINISHED"}
assert ops.object.modifier_apply(index="0") == {"FINISHED"}
assert all(math.isclose(o, 0.3, abs_tol=0.02) for o in head.opacities), head.opacities
alpha = [a for x, y, a in oanim._oanim.layer_shape_stroke(head.id, 0)]
assert alpha and max(alpha) < 0.35, max(alpha)
wm.set_draw(fill=False)

# --- set_draw refuses nan and inf for the pen's numbers -----------------------------------------------------------------
fresh()
for key, value in [("min_opacity", float("nan")), ("view_size", float("nan")), ("nib_angle", float("inf")),
                   ("nib_angle", float("nan")), ("nib_direction", float("nan"))]:
    was = wm.draw_settings()[key]
    try:
        wm.set_draw(**{key: value})
    except ValueError:
        pass
    else:
        raise AssertionError("%s=%s taken" % (key, value))
    assert wm.draw_settings()[key] == was, (key, wm.draw_settings()[key])
wm.set_draw(min_opacity=0.25, nib_angle=30.0)
assert math.isclose(wm.draw_settings()["min_opacity"], 0.25) and math.isclose(wm.draw_settings()["nib_angle"], 30.0)

# --- Mean Opacity = nan leaves the points as they were ----------------------------------------------------------------------
layer, pixel = fresh()
ops.draw.quick_shape(shape="LINE", a="-0.5,0", b="0.5,0", pixel=pixel, opacity="0.5")
ops.mesh.select_all()
layer.mean_opacity = float("nan")
layer.mean_radius = float("nan")
assert all(math.isclose(o, 0.5) for o in layer.opacities), layer.opacities
assert all(math.isfinite(r) for r in layer.radii), layer.radii

# --- Hold to Shape refuses an end past the drawing's numbers ---------------------------------------------------------------
layer, pixel = fresh()
assert ops.draw.quick_shape(shape="LINE", a="1e30,0", b="0.5,0", pixel=pixel) == {"CANCELLED"}
assert layer.point_count == 0
assert ops.draw.quick_shape(shape="ELLIPSE", center="0,0", radii="1e30,0.2", pixel=pixel) == {"CANCELLED"}
assert ops.draw.quick_shape(shape="LINE", a="-0.5,0", b="0.5,0", pixel=pixel) == {"FINISHED"}, "a plain line as before"

# --- A saved pen with a wrong-typed key: the others still load, it with that key's default ---------------------------------
fresh()
library = library_with("Odd", viewSize="big", opacityPressure="yes")
ops.preferences.asset_library_set(directory=library)
names = [p["name"] for p in wm.draw_presets()]
assert "Good" in names and "Odd" in names, names
assert ops.draw.preset_load(name="Odd") == {"FINISHED"}
assert math.isfinite(wm.draw_settings()["view_size"]) and not wm.draw_settings()["opacity_pressure"]

# --- A saved pen with a number past a float falls back to that key's default ----------------------------------------------
layer, pixel = fresh()
library = library_with("Huge", nibAngle=1e39, nibDirection=1.0)
ops.preferences.asset_library_set(directory=library)
assert ops.draw.preset_load(name="Huge") == {"FINISHED"}
assert math.isfinite(wm.draw_settings()["nib_angle"]), wm.draw_settings()["nib_angle"]
ops.draw.stroke(samples=ramp_text(), pixel=pixel)
assert layer.radii and all(math.isfinite(r) for r in layer.radii), layer.radii

print("draw sweep fixes: ok")
