"""Lifting the pen doesn't flash the cursor where the mouse was (wm/pointer_track.hh): the pen's own messages never move
the system cursor, so as the pen lifts or leaves, the mouse move Windows reports, and ImGui's read of the cursor, are the
mouse's old place. While the pen is the pointer those are dropped and the pen's place kept; the mouse moved anywhere is
the pointer again.

SDL's events need the window: the pen and the mouse together are checked by hand with a tablet.

Run with:  OpenAnimate --background --python tests/test_pointer_track.py
"""

import oanim

track = oanim._oanim.pointer_track

# --- A stroke, then the pen lifts: the report of the cursor where the mouse left it is dropped --------------------------
mouse = (300.0, 200.0)
moves = [("mouse",) + mouse]
moves += [("pen", 500.0 + i, 400.0, mouse[0], mouse[1]) for i in range(5)]
moves += [("mouse",) + mouse]                  # Windows' WM_MOUSEMOVE as the pen lifts
moves += [("mouse", mouse[0] + 0.5, mouse[1])]  # within the system cursor's rounding
assert track(moves) == [True, False, False], track(moves)

# --- ImGui's read of the cursor off the window, while the pen is the pointer: the pen's place --------------------------
assert track(moves[:6] + [("read",) + mouse]) == [True, (504.0, 400.0)]
# A read anywhere else (the pen leaving the window: far off) is as it is.
assert track(moves[:6] + [("read", -1000.0, -1000.0)]) == [True, (-1000.0, -1000.0)]

# --- The mouse moved: the pointer again, everywhere, even back where it was ---------------------------------------------
got = track(moves[:6] + [("mouse", 320.0, 210.0), ("mouse",) + mouse, ("read",) + mouse])
assert got == [True, True, True, mouse], got

# --- No pen: every mouse move is taken, even standing still -------------------------------------------------------------
assert track([("mouse", 10.0, 10.0), ("mouse", 10.0, 10.0), ("read", 10.0, 10.0)]) == [True, True, (10.0, 10.0)]

# --- A cursor that follows the pen (WinTab, a driver that moves it): reports at the pen's place, nothing lost ---------
got = track([("pen", 50.0, 60.0, 50.0, 60.0), ("mouse", 50.0, 60.0), ("mouse", 90.0, 60.0)])
assert got == [False, True], got

# --- A release while the pen is down is held back, and sent as it lifts: the stroke goes on ------------------------------
got = track([("touch", True), ("up",), ("up",), ("touch", False)])
assert got == [False, False, False, True], got
# Once only: the next stroke with no stray release has nothing to send as it lifts.
got = track([("touch", True), ("up",), ("touch", False), ("touch", True), ("touch", False)])
assert got == [False, False, True, False, False], got

# --- With the pen up, every release is taken, and nothing waits for the next stroke --------------------------------------
got = track([("up",), ("touch", True), ("touch", False), ("up",)])
assert got == [True, False, False, True], got

print("pointer track: ok")
