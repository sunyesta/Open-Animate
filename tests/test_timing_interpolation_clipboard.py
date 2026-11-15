"""The Path Timing graph's Copy and Paste Interpolation (its right-click menu): the stretch's key settings and, when
Custom, its curve, which fits a stretch of any length; one clipboard with the timeline's Copy and Paste
Interpolation, whose paste now carries a Custom curve too; a span across breakdowns pasted whole; keys keep their
type, hold and interval; one undo step.

Run with:  OpenAnimate --background --python tests/test_timing_interpolation_clipboard.py
"""

import oanim

doc = oanim.data.document
layers = oanim.data.layers
ops = oanim.ops


def close(a, b, eps=1e-3):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    return abs(a - b) < eps


def path_of(layer):
    return next(p for p in oanim.wm.motion_paths() if p["layer"] == layer.id)


def progress(layer, start):
    t = next(t for t in oanim.wm.motion_path_timing() if t["label"] == path_of(layer)["label"])
    return next(s for s in t["stretches"] if s["start"] == start)["progress"]


def key(layer, frame):
    return next(k for k in layer.keyframes("position") if k["frame"] == frame)


def where(layer, frame):
    doc.frame_current = frame
    return (layer.location_x, layer.location_y)


def line_layer(keys):
    """A straight line keyed Linear at (frame, x) for each of `keys`."""
    ops.layer.new()
    line = layers.active
    line.key_together = False
    line.add_curve([(0.0, 0.0), (0.1, 0.0)])
    doc.frame_current = 0
    line.location_x, line.location_y = -5.0, -5.0
    for other in layers:
        other.selected = other.id == line.id
    layers.active = line
    for f, x in keys:
        assert ops.anim.motion_path_move(frame=str(f), x=str(x), y="0", layer=str(line.id)) == {'FINISHED'}
        line.keyframe_set("position", f, interp="LINEAR")
    return line


doc.motion_paths = True
doc.path_before, doc.path_after = 3, 3
doc.auto_key = False
assert ops.wm.tool_motion_path() == {'FINISHED'}

line = line_layer(((10, 0.0), (20, 1.0), (30, 2.0), (45, 3.0)))
args = dict(layer=str(line.id))
even10 = [k / 10 for k in range(11)]

# --- Nothing copied yet: Paste is greyed (its poll fails) ------------------------------------------------------------
assert ops.anim.timing_interpolation_paste(frame="13", **args) == {'CANCELLED'}, "nothing copied"
assert key(line, 20)["interp"] == "LINEAR"

# --- A Custom curve copied and pasted onto a stretch as long ----------------------------------------------------------
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="13", **args) == {'FINISHED'}
eased = progress(line, 10)
assert close(eased, [(k / 10) ** 2 for k in range(11)])
assert ops.anim.timing_interpolation_copy(frame="13", **args) == {'FINISHED'}
assert ops.anim.timing_interpolation_copy(frame="20", **args) == {'CANCELLED'}, "on a key: no stretch"
assert ops.anim.timing_interpolation_paste(frame="23", **args) == {'FINISHED'}
assert key(line, 30)["interp"] == "CUSTOM"
assert key(line, 30)["timing"] == key(line, 20)["timing"], "the same curve"
assert close(progress(line, 20), eased), progress(line, 20)
assert close(where(line, 20), (1.0, 0.0)) and close(where(line, 30), (2.0, 0.0)), "the keys stay"
assert close(progress(line, 30), [k / 15 for k in range(16)]), "the stretch after keeps its timing"

# One undo step.
ops.ed.undo()
assert key(line, 30)["interp"] == "LINEAR" and close(progress(line, 20), even10)

# --- The curve fitted to a longer stretch ------------------------------------------------------------------------------
assert ops.anim.timing_interpolation_paste(frame="31", **args) == {'FINISHED'}
assert close(progress(line, 30), [(k / 15) ** 2 for k in range(16)], 0.02), progress(line, 30)
ops.ed.undo()

# --- Not Custom: the settings pasted and the curve dropped -------------------------------------------------------------
line.keyframe_set("position", 30, interp="EASE_IN_OUT", ease="CUBIC")
assert ops.anim.timing_interpolation_copy(frame="25", **args) == {'FINISHED'}
assert ops.anim.timing_interpolation_paste(frame="15", **args) == {'FINISHED'}
k20 = key(line, 20)
assert k20["interp"] == "EASE_IN_OUT" and k20["ease"] == "CUBIC", k20
assert not k20.get("timing"), "a curve no longer Custom goes"
assert close(progress(line, 10), progress(line, 20)), "timed as the stretch copied"

# --- Keys keep their type, hold and interval ---------------------------------------------------------------------------
line.keyframe_set("position", 20, hold=0, interval=2)
line.keyframe_set("position", 30, interp="LINEAR", hold=3, interval=1)
assert ops.anim.timing_interpolation_copy(frame="25", **args) == {'FINISHED'}
assert ops.anim.timing_interpolation_paste(frame="15", **args) == {'FINISHED'}
k20 = key(line, 20)
assert k20["interp"] == "LINEAR" and k20["hold"] == 0 and k20["interval"] == 2, k20
line.keyframe_set("position", 20, interval=1)
line.keyframe_set("position", 30, hold=0)

# --- One clipboard with the timeline's: the timeline's paste carries the curve ----------------------------------------
assert ops.anim.motion_path_stretch_shape(shape="EASE_OUT", frame="13", **args) == {'FINISHED'}
curve = key(line, 20)["timing"]
assert curve
assert ops.anim.timing_interpolation_copy(frame="13", **args) == {'FINISHED'}
assert ops.anim.keys_select(frame_start="45") == {'FINISHED'}
assert ops.anim.interpolation_paste() == {'FINISHED'}
assert key(line, 45)["interp"] == "CUSTOM" and key(line, 45)["timing"] == curve, key(line, 45)
assert close(progress(line, 30), [1 - (1 - k / 15) ** 2 for k in range(16)], 0.02), progress(line, 30)

# And the timeline's copy of a Custom key pasted in the graph.
line.keyframe_set("position", 30, interp="LINEAR")
assert ops.anim.keys_select(frame_start="45") == {'FINISHED'}
assert ops.anim.interpolation_copy() == {'FINISHED'}
assert ops.anim.timing_interpolation_paste(frame="25", **args) == {'FINISHED'}
assert key(line, 30)["interp"] == "CUSTOM" and key(line, 30)["timing"] == curve
ops.anim.keys_deselect_all()

# --- A span across a breakdown: each of its stretches ------------------------------------------------------------------
span = line_layer(((10, 0.0), (15, 0.5), (20, 1.0), (30, 2.0)))
sargs = dict(layer=str(span.id))
span.keyframe_set("position", 15, type="BREAKDOWN")
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="25", **sargs) == {'FINISHED'}
assert ops.anim.timing_interpolation_copy(frame="25", **sargs) == {'FINISHED'}
assert ops.anim.timing_interpolation_paste(frame="11", end="20", **sargs) == {'FINISHED'}
for f in (15, 20):
    k = key(span, f)
    assert k["interp"] == "CUSTOM" and k["timing"] == key(span, 30)["timing"], (f, k)
assert key(span, 15)["type"] == "BREAKDOWN" and key(span, 20)["type"] == "KEYFRAME", "types kept"
assert close(where(span, 15), (0.5, 0.0)), "the breakdown's pose stays"
ops.ed.undo()
assert key(span, 15)["interp"] == "LINEAR" and key(span, 20)["interp"] == "LINEAR", "one undo step for the span"

# Without end=, only the stretch the frame is in.
assert ops.anim.timing_interpolation_paste(frame="11", **sargs) == {'FINISHED'}
assert key(span, 15)["interp"] == "CUSTOM" and key(span, 20)["interp"] == "LINEAR"

print("timing interpolation clipboard: ok")
