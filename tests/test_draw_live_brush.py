"""A brushed line paints with its brush as it is drawn (as Toon Boom does): the Stroke Pen's line still being drawn is
the line it will end as (draw_live_line in src/ops/draw_ops.cc), its dabs laid as the finished line's, seeded the
same, and the dabs already down staying put as it grows. A solid line is drawn by the tool's own preview.

The viewport laying it over the canvas needs the window: checked live on a private copy.

Run with:  OpenAnimate --background --python tests/test_draw_live_brush.py
"""

import math
import tempfile

import oanim

ops = oanim.ops
live_dabs = oanim._oanim.draw_live_dabs


def fresh(brush=True):
    ops.wm.read_homefile(confirmed="1")
    ops.layer.new()
    doc = oanim.data.document
    doc.frame_current = 0
    ops.draw.preset_load(name="Ink")
    if brush:
        ops.preferences.asset_library_set(directory=tempfile.mkdtemp(prefix="oanim_live_brush_"))
        assert ops.brush.preset_load(preset="Hard Round", library="1", target="TOOL") == {"FINISHED"}
    return oanim.data.layers.active, 2.0 / doc.height


def wave(dy=0.0):
    return [(-0.5 + i / 79, 0.1 + dy + 0.15 * math.sin(i / 12), 0.3 + 0.7 * i / 79, i / 79 * 0.5) for i in range(80)]


def finish(rows, pixel):
    assert ops.draw.stroke(samples=";".join("%f,%f,%f,%f" % r for r in rows), pixel=pixel) == {"FINISHED"}


def nearest(p, dabs):
    return min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in dabs)


# --- A solid line is drawn by the tool's preview, not stamped (first: a brush once picked stays the pen's) ----------------
layer, pixel = fresh(brush=False)
assert live_dabs(wave(), pixel, 80) is None
assert live_dabs(wave(), pixel, 0) is None

# --- A brushed line's dabs as it is drawn are the finished line's, to within a pixel (its tapers too) ---------------------
layer, pixel = fresh()
oanim.wm.set_draw(taper_start=60.0, taper_end=60.0)
rows = wave()
live = live_dabs(rows, pixel, len(rows))
finish(rows, pixel)
final = oanim._oanim.layer_shape_dabs(layer.id, 0)
assert live and abs(len(live) - len(final)) <= len(final) * 0.01, (len(live), len(final))
worst = max(nearest(p, final) for p in live)
assert worst < pixel, ("a live dab off the finished line", worst, pixel)
assert all(math.isclose(a[2], b[2], abs_tol=1e-3) for a, b in zip(live[:50], final[:50])), "as solid"
oanim.wm.set_draw(taper_start=0.0, taper_end=0.0)

# --- The dabs already down stay put as the line grows --------------------------------------------------------------------
layer, pixel = fresh()
for setting, value in (("scatter", "0.6"), ("sizeJitter", "0.5"), ("count", "2"), ("spacing", "0.5")):
    assert ops.brush.setting_set(setting=setting, value=value, target="TOOL") == {"FINISHED"}
rows = wave()
whole = live_dabs(rows, pixel, len(rows))
for upto in (20, 40, 60):
    part = live_dabs(rows, pixel, upto)
    # The last few wait for the pen's next samples (the tail and the taper at the tip move as it goes).
    settled = part[:len(part) * 3 // 4]
    assert settled == whole[:len(settled)], ("dabs moved as the line grew", upto)

# --- Seeded as the finished line: each new line's scatter starts where its finished line's does ---------------------------
first = []
for k in range(2):
    rows = wave(-0.25 * k)
    live = live_dabs(rows, pixel, len(rows))
    finish(rows, pixel)
    final = oanim._oanim.layer_shape_dabs(layer.id, k)
    first.append(live[:12])
    gaps = [math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(live[:12], final[:12])]
    assert max(gaps) < pixel, ("line", k, "scattered elsewhere than it ends", max(gaps))
# The two lines' scatter differs (each shape its own seed), so the match above is the seed's.
offsets = [[(x - first[k][0][0], y - first[k][0][1]) for x, y, _ in first[k]] for k in range(2)]
assert max(math.hypot(a[0] - b[0], a[1] - b[1] + 0.0) for a, b in zip(offsets[0], offsets[1])) > pixel

print("draw live brush: ok")
