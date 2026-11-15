"""Several stretches picked with the Motion Path tool: each shaded teal, the active one (the last picked on, shown in Path
Timing) lighter; a timing edit to the active one is copied to the other picked stretches, each fitted to its own length
(a Custom curve by share of its time), one undo step; a picked stretch the edit changed itself keeps what it did; an
edit to a stretch not the active one, or with one stretch picked, goes nowhere else. Shift Alt click on the active one
unpicks it, the one picked before it active then.

Run with:  OpenAnimate --background --python tests/test_stretch_sync.py
"""

import oanim

doc = oanim.data.document
layers = oanim.data.layers
ops = oanim.ops
wm = oanim.wm


def close(a, b, eps=1e-3):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    return abs(a - b) < eps


def path_of(layer):
    return next(p for p in wm.motion_paths() if p["layer"] == layer.id)


def progress(layer, start):
    t = next(t for t in wm.motion_path_timing() if t["label"] == path_of(layer)["label"])
    return next(s for s in t["stretches"] if s["start"] == start)["progress"]


def key(layer, frame):
    return next(k for k in layer.keyframes("position") if k["frame"] == frame)


doc.motion_paths = True
doc.path_before, doc.path_after = 3, 3
doc.auto_key = False
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING", proportional="0") == {'FINISHED'}

ops.layer.new()
line = layers.active
line.key_together = False
line.add_curve([(0.0, 0.0), (0.1, 0.0)])
doc.frame_current = 0
line.location_x, line.location_y = -5.0, -5.0
for other in layers:
    other.selected = other.id == line.id
layers.active = line
# New keys Linear (no key selected: the header sets what new keys get), so every key is an operator's.
ops.anim.keys_deselect_all()
assert ops.anim.keys_interpolation_set(interp="LINEAR") == {'FINISHED'}
for f, x in ((10, 0.0), (20, 1.0), (30, 2.0), (45, 3.0)):
    assert ops.anim.motion_path_move(frame=str(f), x=str(x), y="0", layer=str(line.id)) == {'FINISHED'}
assert all(k["interp"] == "LINEAR" for k in line.keyframes("position") if k["frame"] > 0)
args = dict(layer=str(line.id))
even = {10: [k / 10 for k in range(11)], 20: [k / 10 for k in range(11)], 30: [k / 15 for k in range(16)]}


def pick(*frames):
    assert ops.anim.motion_path_select(none="1") == {'FINISHED'}
    for i, f in enumerate(frames):
        assert ops.anim.motion_path_select(frame=str(f), extend="1" if i else "0", **args) == {'FINISHED'}


def all_even():
    return all(close(progress(line, s), u) for s, u in even.items())


# --- Teal: both picked stretches, the active one (the last picked on) lighter ----------------------------------------
pick(15, 35)
panel = wm.motion_path_timing_panel()
assert (panel["start"], panel["end"]) == (30, 45), ("the active one shows in Path Timing", panel)
h = wm.timeline_key_header()
assert h["mode"] == "STRETCHES" and h["label"] == "2 stretches", h
spans = sorted({s for r in wm.timeline_row_details(as_shown=False) for s in r["teal_spans"]})
assert spans == [(10, 20, False), (30, 45, True)], spans

# --- A timing edit to the active one goes to the other, fitted to its length ------------------------------------------
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="35", **args) == {'FINISHED'}
assert close(progress(line, 30), [(k / 15) ** 2 for k in range(16)], 0.02), progress(line, 30)
assert close(progress(line, 10), [(k / 10) ** 2 for k in range(11)], 0.02), ("followed", progress(line, 10))
assert key(line, 20)["interp"] == "CUSTOM" and key(line, 20)["timing"] == key(line, 45)["timing"]
assert close(progress(line, 20), even[20]), "a stretch not picked keeps its timing"
# One undo step for both.
ops.ed.undo()
assert all_even(), "one undo step"
assert key(line, 20)["interp"] == "LINEAR" and key(line, 45)["interp"] == "LINEAR"

# The graph's own edits too: a point moved on the active curve.
pick(15, 35)
assert ops.anim.motion_path_stretch_shape(shape="EASE_OUT", frame="35", **args) == {'FINISHED'}
was = key(line, 45)["timing"]
assert ops.anim.timing_handle_move(frame="35", index="1", side="IN", x="-0.2", y="-0.4", **args) == {'FINISHED'}
assert key(line, 45)["timing"] != was
assert key(line, 20)["timing"] == key(line, 45)["timing"], "the moved handle copied"
ops.ed.undo()
assert key(line, 20)["timing"] == key(line, 45)["timing"], "undone on both"
ops.ed.undo()
assert all_even()

# Paste Interpolation onto the active one: onto both.
pick(25)
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN_OUT", frame="25", **args) == {'FINISHED'}
assert ops.anim.timing_interpolation_copy(frame="25", **args) == {'FINISHED'}
ops.ed.undo()
pick(15, 35)
assert ops.anim.timing_interpolation_paste(frame="31", end="45", **args) == {'FINISHED'}
assert key(line, 20)["interp"] == "CUSTOM" and key(line, 20)["timing"] == key(line, 45)["timing"]
ops.ed.undo()
assert all_even()

# --- An edit to a picked stretch that isn't the active one goes nowhere else ------------------------------------------
pick(15, 35)
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="15", **args) == {'FINISHED'}
assert key(line, 20)["interp"] == "CUSTOM" and key(line, 45)["interp"] == "LINEAR"
ops.ed.undo()

# --- One stretch picked: nothing else follows ------------------------------------------------------------------------
pick(35)
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="35", **args) == {'FINISHED'}
assert key(line, 20)["interp"] == "LINEAR" and key(line, 45)["interp"] == "CUSTOM"
ops.ed.undo()

# --- A picked stretch the edit changed itself keeps what it did --------------------------------------------------------
# Alt S around the picked dots: each stretch scaled around its own dot, as with it picked alone.
pick(15)
assert ops.anim.motion_path_scale_spacing(factor="0.5", **args) == {'FINISHED'}
alone = progress(line, 10)
ops.ed.undo()
pick(15, 35)
assert ops.anim.motion_path_scale_spacing(factor="0.5", **args) == {'FINISHED'}
assert close(progress(line, 10), alone), ("its own Alt S, not the active one's", progress(line, 10), alone)
assert not close(progress(line, 30), even[30]), "the active one scaled too"
ops.ed.undo()
assert all_even()

# --- Shift Alt click on the active one unpicks it ----------------------------------------------------------------------
pick(15, 35)
assert ops.anim.timeline_stretch_pick(frame="38", extend="1", layers=str(line.id)) == {'FINISHED'}
panel = wm.motion_path_timing_panel()
assert (panel["start"], panel["end"]) == (10, 20), ("the one left is active", panel)
assert [d["frame"] for d in wm.motion_path_dots()] == [15], wm.motion_path_dots()
# Shift Alt on a picked one not active makes it active.
pick(15, 35)
assert ops.anim.timeline_stretch_pick(frame="12", extend="1", layers=str(line.id)) == {'FINISHED'}
panel = wm.motion_path_timing_panel()
assert (panel["start"], panel["end"]) == (10, 20), ("made active", panel)
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="15", **args) == {'FINISHED'}
assert key(line, 45)["interp"] == "CUSTOM", "the other follows the one made active"
ops.ed.undo()

print("stretch sync: ok")
