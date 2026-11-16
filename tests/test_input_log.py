"""The input log (wm/input_log.hh): off until asked, cleared when started, taken once. What it logs (Windows' messages
and SDL's events) needs the window: read live with a tablet.

Run with:  OpenAnimate --background --python tests/test_input_log.py
"""

import oanim

wm = oanim.wm
log = oanim._oanim

log.input_log_add("SDL_MOUSE_MOTION", 1.0, 2.0)
wm.input_log(True)
assert wm.input_log_take() == [], "nothing logged while off, and starting clears"
log.input_log_add("SDL_MOUSE_MOTION", 1.0, 2.0)
log.input_log_add("SDL_PEN_MOTION", 3.0, 4.0)
got = wm.input_log_take()
assert [(e["what"], e["x"], e["y"]) for e in got] == [("SDL_MOUSE_MOTION", 1.0, 2.0), ("SDL_PEN_MOTION", 3.0, 4.0)], got
assert got[0]["time"] <= got[1]["time"]
assert wm.input_log_take() == [], "taken once"
wm.input_log(False)
log.input_log_add("SDL_MOUSE_MOTION", 1.0, 2.0)
assert wm.input_log_take() == []

print("input log: ok")
