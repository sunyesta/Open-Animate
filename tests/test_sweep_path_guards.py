"""Motion path guards from a bug sweep: a dot slid to where it already is changes nothing, also where an overshoot turns
(an Elastic stretch's swing past its key: held between its two neighbours, both on one side of it, it was pulled onto
one, 0.25 off) and slid again and again on a Custom stretch that turns. Each section failed on the build before.

Run with:  OpenAnimate --background --python tests/test_sweep_path_guards.py
"""

import math
import os
import tempfile

import oanim

ops, wm, L = oanim.ops, oanim.wm, oanim.data.layers
D = lambda: oanim.data.document
FOLDER = tempfile.mkdtemp(prefix="oanim_path_guards_")


def start():
    assert ops.wm.read_homefile() == {'FINISHED'}
    D().motion_paths = True
    D().auto_key = False
    D().frame_end = 200
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    assert ops.anim.motion_path_brush_set(brush="EDIT", proportional="0") == {'FINISHED'}


def pick(layer):
    for o in L:
        o.selected = o.id == layer.id
    L.active = layer


def path_layer(keys, interp):
    ops.layer.new()
    layer = L.active
    layer.add_curve([(0.0, 0.0), (0.1, 0.0)])
    layer.key_whole_drawing = False
    D().frame_current = 0
    layer.location_x, layer.location_y = -1.0, 0.0
    pick(layer)
    for f, (x, y) in sorted(keys.items()):
        assert ops.anim.motion_path_move(frame=str(f), x=str(x), y=str(y), layer=str(layer.id)) == {'FINISHED'}
        layer.keyframe_set("position", f, interp=interp)
    return layer


def reopen(layer_id):
    """Saved and opened again, so the Python edits above are the file's and every slide its own step."""
    path = os.path.join(FOLDER, "base.oanim")
    assert ops.wm.save_copy(filepath=path) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
    ops.wm.tool_motion_path()
    ops.anim.motion_path_brush_set(brush="EDIT", proportional="0")
    layer = next(l for l in L.all() if l.id == layer_id)
    pick(layer)
    return layer


def loc(layer, f):
    D().frame_current = f
    return (layer.location_x, layer.location_y)


KEYS = {10: (0.0, 0.0), 20: (1.0, 0.6), 32: (2.0, -0.2)}


def elastic_slid_to_itself(hold, frame):
    start()
    lay = path_layer(KEYS, "ELASTIC")
    for f in KEYS:
        lay.keyframe_set("position", f, hold=hold)
    lay = reopen(lay.id)
    before = {f: loc(lay, f) for f in range(20, 33)}
    x, y = before[frame]
    assert ops.anim.motion_path_slide(frame=str(frame), x=repr(x), y=repr(y), layer=str(lay.id)) == {'FINISHED'}
    after = {f: loc(lay, f) for f in range(20, 33)}
    worst, at = max((math.dist(before[f], after[f]), f) for f in before)
    assert worst < 1e-3, ("Elastic: a dot slid to where it is moved one", hold, frame, at, worst)


# --- Elastic, no hold: the dot where the swing turns, slid to where it is, stays
elastic_slid_to_itself(0, 22)

# --- Elastic with a hold of 3 on its keys: the same
elastic_slid_to_itself(3, 24)

# --- A Custom stretch that turns: dots slid to where they are, twenty times over, don't drift
start()
lay = path_layer(KEYS, "EASE_IN_OUT")
assert ops.anim.timing_point_add(frame="25", x="0.4", y="0.7", layer=str(lay.id)) == {'FINISHED'}
lay = reopen(lay.id)
base = {f: loc(lay, f) for f in range(20, 33)}
for n in range(20):
    f = 24 + n % 4
    x, y = base[f]
    assert ops.anim.motion_path_slide(frame=str(f), x=repr(x), y=repr(y), layer=str(lay.id)) == {'FINISHED'}
now = {g: loc(lay, g) for g in base}
worst, at = max((math.dist(base[g], now[g]), g) for g in base)
assert worst < 1e-3, ("Custom: twenty slides to where they are drifted a dot", at, worst)

print("test_sweep_path_guards: all passed")
