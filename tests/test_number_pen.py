"""Number fields scrubbed with a pen (editors/number_pen.hh, editors/number_field.cc). A mouse's scrub hides the cursor
and reads only how far the mouse moves; a pen's follows the pen with the cursor shown. Moving the pen up or down off the
field's row makes each pixel across count for less (Shift is awkward with a pen in hand). A pen's tap must go further
before it is a drag, as its tip wobbles touching down. Lifting the pen and putting it back on the same field within half
a second carries on the same drag, one undo step (ops/undo.hh's undo_join_next).

The field's drag needs the window: checked live with a tablet.

Run with:  OpenAnimate --background --python tests/test_number_pen.py
"""

import oanim

pen = oanim._oanim.number_pen
ops = oanim.ops

# --- A pen goes further than the mouse's 3 before a press is a drag ------------------------------------------------------
assert pen(20.0, 0.0, 0.0, True)[0] == 6.0
assert pen(40.0, 0.0, 0.0, True)[0] == 12.0, "bigger fields, a bigger wobble allowed"

# --- Finer off the row: all of each pixel on it, half two field heights off, a quarter at six, a tenth at most -----------
h = 20.0
assert pen(h, 0.0, 0.0, True)[1] == 1.0
assert pen(h, h * 0.5, 0.0, True)[1] == 1.0, "still on the row"
assert abs(pen(h, h * 0.5 + 2 * h, 0.0, True)[1] - 0.5) < 1e-9
assert abs(pen(h, -(h * 0.5 + 6 * h), 0.0, True)[1] - 0.25) < 1e-9, "above as below"
assert pen(h, 5000.0, 0.0, True)[1] == 0.1
steps = [pen(h, h * 0.5 + d, 0.0, True)[1] for d in range(0, 400, 10)]
assert all(a >= b for a, b in zip(steps, steps[1:])), "finer the further it goes"

# --- Put back on the same field at once: the same drag ---------------------------------------------------------------------
assert pen(h, 0.0, 0.2, True)[2]
assert pen(h, 0.0, 0.5, True)[2]
assert not pen(h, 0.0, 0.6, True)[2], "too late: a new drag"
assert not pen(h, 0.0, 0.2, False)[2], "another field: a new drag"
assert not pen(h, 0.0, -0.1, True)[2]


# --- Carried on, one undo step: the next push named as the last replaces it -------------------------------------------------
def layers():
    return len(oanim.data.layers)


ops.wm.read_homefile(confirmed="1")
start = layers()
names, active = oanim.wm.undo_history()
ops.layer.new()
oanim._oanim.undo_join_next()
ops.layer.new()
names2, active2 = oanim.wm.undo_history()
assert active2 == active + 1 and names2[-1] == names2[active2], (names, names2)
assert layers() == start + 2
ops.ed.undo()
assert layers() == start, "both undone together"
ops.ed.redo()
assert layers() == start + 2, "and redone together"

# Not asked: two steps.
ops.wm.read_homefile(confirmed="1")
_, active = oanim.wm.undo_history()
ops.layer.new()
ops.layer.new()
assert oanim.wm.undo_history()[1] == active + 2

# A step of another name is never joined.
ops.wm.read_homefile(confirmed="1")
_, active = oanim.wm.undo_history()
ops.layer.new()
oanim._oanim.undo_join_next()
ops.layer.new_bone()
assert oanim.wm.undo_history()[1] == active + 2

# The ask lapses after two frames (the field's push comes the frame after it lets go), and once used.
ops.wm.read_homefile(confirmed="1")
_, active = oanim.wm.undo_history()
ops.layer.new()
oanim._oanim.undo_join_next()
oanim._oanim.undo_join_frame_end()
oanim._oanim.undo_join_frame_end()
ops.layer.new()
assert oanim.wm.undo_history()[1] == active + 2, "lapsed"
oanim._oanim.undo_join_next()
ops.layer.new()
ops.layer.new()
assert oanim.wm.undo_history()[1] == active + 3, "used once"

print("number pen: ok")
