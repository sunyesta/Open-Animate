"""The Draw tool's newer settings: Size Unit (View or Scene), the nib (a line along its edge thinner), the brush
button's Recently Used line brushes, and Prediction as a preference.

The header, its popovers and the brush tiles need the window: checked live on a private copy.

Run with:  OpenAnimate --background --python tests/test_draw_size_nib.py
"""

import math
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


def stroke_text(path, count=80, seconds=0.5, pressure=0.8):
    rows = []
    for i in range(count):
        u = i / (count - 1)
        x, y = path(u)
        rows.append("%f,%f,%f,%f" % (x, y, pressure, u * seconds))
    return ";".join(rows)


line = stroke_text(lambda u: (-0.5 + u, 0.1))

# --- Size Unit View: the line as wide as it was on screen ---------------------------------------------------------------
layer, pixel = fresh()
width = wm.draw_settings()["line_width"]
ops.draw.stroke(samples=line, pixel=pixel)
assert close(layer.shape_style(0)["line_width"], width), "Scene: the width field's"
wm.set_draw(size_view=True, view_size=12.0)
ops.draw.stroke(samples=line, pixel=pixel)
assert close(layer.shape_style(1)["line_width"], 12.0 * pixel, 1e-6), (layer.shape_style(1)["line_width"], 12.0 * pixel)
# Zoomed in twice as far (a screen pixel half as much of the drawing), half as wide in the drawing.
ops.draw.stroke(samples=line, pixel=pixel * 0.5)
assert close(layer.shape_style(2)["line_width"], 6.0 * pixel, 1e-6)
wm.set_draw(size_view=False)
ops.draw.stroke(samples=line, pixel=pixel * 0.5)
assert close(layer.shape_style(3)["line_width"], width), "Scene again: whatever the zoom"

# --- The nib: thin along its edge, full across it ----------------------------------------------------------------------
def radii(points, **settings):
    samples = [(x, y, 1.0, 0.0, 0.0, i * 0.004) for i, (x, y) in enumerate(points)]
    settings.setdefault("min_size", 0.0)
    out = wm.ink_stroke(samples, pixel=1.0, line_width=10.0, stabilizer="OFF", use_pressure=False, **settings)
    rs = [r for _, _, r, _ in out["points"]]
    return rs[len(rs) // 4: 3 * len(rs) // 4]


across = [(i * 2.0, 0.0) for i in range(100)]
up = [(0.0, i * 2.0) for i in range(100)]
assert all(close(r, 1.0) for r in radii(across)), "no nib: as before"
assert max(radii(across, nib_direction=1.0, nib_angle=0.0)) < 0.05, "along the nib's edge: thin"
assert min(radii(up, nib_direction=1.0, nib_angle=0.0)) > 0.95, "across it: full"
half = radii(across, nib_direction=0.5, nib_angle=0.0)
assert all(close(r, 0.5, 0.05) for r in half), half
diagonal = [(i * 2.0, i * 2.0) for i in range(100)]
assert min(radii(diagonal, nib_direction=1.0, nib_angle=45.0)) < 0.05, "held at 45 degrees, a 45 degree line is thin"
assert min(radii(diagonal, nib_direction=1.0, nib_angle=135.0)) > 0.95
# Min Size still holds it up.
assert min(radii(across, nib_direction=1.0, nib_angle=0.0, min_size=0.3)) > 0.29

# --- A pen saves them ---------------------------------------------------------------------------------------------------
layer, pixel = fresh()
library = tempfile.mkdtemp(prefix="oanim_draw_nib_")
ops.preferences.asset_library_set(directory=library)
wm.set_draw(size_view=True, view_size=9.0, nib_angle=60.0, nib_direction=0.7)
ops.draw.preset_save(name="Nib Pen")
assert os.path.exists(os.path.join(library, "Draw Presets", "Nib Pen.oadraw"))
ops.preferences.asset_library_set(directory=library)
saved = {p["name"]: p for p in wm.draw_presets()}["Nib Pen"]
assert saved["size_view"] and close(saved["view_size"], 9.0) and close(saved["nib_angle"], 60.0)
assert close(saved["nib_direction"], 0.7)
ops.draw.preset_load(name="Ink")
assert not wm.draw_settings()["size_view"] and wm.draw_settings()["nib_direction"] == 0.0

# --- Recently Used line brushes ------------------------------------------------------------------------------------------
layer, pixel = fresh()
library = tempfile.mkdtemp(prefix="oanim_draw_recent_")
ops.preferences.asset_library_set(directory=library)
ops.draw.stroke(samples=line, pixel=pixel)
recent = wm.draw_settings()["brush_recent"]
assert len(recent) == 1 and recent[0]["name"] == "", ("the solid line drawn with", recent)
assert ops.brush.preset_load(preset="Hard Round", library="1", target="TOOL") == {"FINISHED"}
ops.draw.stroke(samples=line, pixel=pixel)
recent = wm.draw_settings()["brush_recent"]
assert [r["preset"] for r in recent] == ["Hard Round", ""], recent
# Drawn with again: to the front, not twice.
assert ops.brush.recent_pick(index="1") == {"FINISHED"}
assert layer.shape_brush(0)["name"] == "" and wm.draw_settings()["brush_recent"][1]["preset"] == ""
ops.draw.stroke(samples=line, pixel=pixel)
recent = wm.draw_settings()["brush_recent"]
assert [r["preset"] for r in recent] == ["", "Hard Round"], recent
assert layer.shape_brush(2)["name"] == "", "the picked brush draws"
assert ops.brush.recent_pick(index="5") == {"CANCELLED"}
# Fills and erasers aren't line brushes.
ops.wm.tool_draw(mode="FILL_PEN")
ops.draw.stroke(samples=line, pixel=pixel)
assert len(wm.draw_settings()["brush_recent"]) == 2

# --- Prediction is a preference now -------------------------------------------------------------------------------------
fresh()
wm.set_draw(prediction=12)
assert wm.draw_settings()["prediction"] == 12.0
ops.wm.read_homefile(confirmed="1")
assert wm.draw_settings()["prediction"] == 12.0, "a new file keeps it"
wm.set_draw(prediction=8)

print("draw size, nib and recent brushes: ok")
