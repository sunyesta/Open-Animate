"""Motion path edits a sweep found going wrong: Key Whole Drawing keying a point inside a stretch shaped by path handles
puts the key in place, so its motion stays; Decimate keeps an aligned timing point's handles in line when one stands
straight up; a key is never put past the last frame a scene can have; the timing graph's points and handles stay
within ten stretches' way past either end; a breakdown on a curved path goes on the path.

Run with:  OpenAnimate --background --python tests/test_motion_path_sweep_guards.py
"""

import math

import oanim

ops, wm, layers = oanim.ops, oanim.wm, oanim.data.layers
doc = oanim.data.document


def go(f):
    doc.frame_current = f + 1
    doc.frame_current = f


def scene(whole=False):
    ops.wm.read_homefile()
    doc.motion_paths = True
    doc.path_all = True
    doc.auto_key = False
    ops.wm.tool_motion_path()
    ops.layer.new()
    a = layers.active
    a.add_curve([(0.0, 0.0), (0.1, 0.0)] if not whole else [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
    a.key_whole_drawing = whole
    for o in layers:
        o.selected = o.id == a.id
    layers.active = a
    return a


# --- Key Whole Drawing inside a stretch shaped by path handles: the point's motion stays -------------------------------
w = scene(whole=True)
doc.auto_freeze_keys = False
doc.auto_key = True
doc.frame_current = 10
w.set_point(0, (0.0, 0.5))
doc.frame_current = 30
w.set_point(0, (1.0, 0.8))
go(0)
doc.auto_key = False
w.select_points([0])
assert ops.anim.motion_path_handle(frame="30", side="IN", x="0.2", y="1.4", layer=str(w.id),
                                   point=str(w.point_ids[0])) == {'FINISHED'}


def track():
    out = {}
    for f in range(10, 31):
        go(f)
        out[f] = tuple(w.points[0])
    return out


before = track()
doc.auto_key = True
go(24)
w.set_point(2, (2.0, 0.7))
go(0)
doc.auto_key = False
assert 24 in [k["frame"] for k in w.keyframes("points[0].pos")], "Key Whole Drawing keyed point 0 there"
after = track()
gap = max(math.dist(before[f], after[f]) for f in before)
assert gap < 2e-4, ("point 0's motion changed by the key put inside its handle-shaped stretch", gap)

# --- Decimate: an aligned point with a handle straight up stays in line ------------------------------------------------
a = scene()
a.location_x = -1.0
T = dict(layer=str(a.id))
for f, (x, y) in ((10, (0.0, 0.0)), (40, (1.0, 0.0))):
    assert ops.anim.motion_path_move(frame=str(f), x=str(x), y=str(y), **T) == {'FINISHED'}
    a.keyframe_set("position", f, interp="LINEAR")
for x, y in (("0.3", "0.2"), ("0.5", "0.5"), ("0.7", "0.8")):
    assert ops.anim.timing_point_add(frame="20", x=x, y=y, **T) == {'FINISHED'}, x


def curve():
    return next(k for k in a.keyframes("position") if k["frame"] == 40)["timing"]


def misaligned(c):
    bad = []
    for i, p in enumerate(c[1:-1], 1):
        (ix, iy), (ox, oy), aligned = p[2], p[3], p[4]
        li, lo = math.hypot(ix, iy), math.hypot(ox, oy)
        if aligned and li > 1e-6 and lo > 1e-6 and abs((ix * oy - iy * ox) / (li * lo)) > 2e-3:
            bad.append((i, p[2], p[3]))
    return bad


c = curve()
mid = min(range(1, len(c) - 1), key=lambda i: abs(c[i][0] - 0.5))
assert ops.anim.timing_handle_move(frame="20", index=str(mid), side="IN", x="0.0", y="-0.06", **T) == {'FINISHED'}
assert not misaligned(curve()), misaligned(curve())
for ratio in ("0.67", "0.5", "0.34"):
    assert ops.anim.timing_decimate(frame="20", ratio=ratio, **T) == {'FINISHED'}, ratio
    assert not misaligned(curve()), ("decimate left an aligned point's handles out of line", ratio, misaligned(curve()))
    assert ops.ed.undo() == {'FINISHED'}

# --- A key past the last frame a scene can have: refused -------------------------------------------------------------
a = scene()
for f, (x, y) in ((10, (0.0, 0.0)), (30, (1.0, 0.5)), (50, (2.0, 0.0))):
    assert ops.anim.motion_path_move(frame=str(f), x=str(x), y=str(y), layer=str(a.id)) == {'FINISHED'}
frames = [k["frame"] for k in a.keyframes("position")]
for far in ("2147483647", "1048575"):
    assert ops.anim.motion_path_key_add(frame=far, layer=str(a.id)) == {'CANCELLED'}, far
assert [k["frame"] for k in a.keyframes("position")] == frames
assert ops.anim.motion_path_key_add(frame="200", layer=str(a.id)) == {'FINISHED'}, "past the scene's end is fine"

# --- The timing graph's points and handles stay within reach (numbers past ten million are refused as nan is) ---------------------------------------------------------
a = scene()
for f, (x, y) in ((10, (0.0, 0.0)), (30, (1.0, 0.5))):
    assert ops.anim.motion_path_move(frame=str(f), x=str(x), y=str(y), layer=str(a.id)) == {'FINISHED'}
assert ops.anim.motion_path_slide(frame="20", x="0.3", y="0.15", layer=str(a.id)) == {'FINISHED'}
pts = next(k for k in a.keyframes("position") if k["frame"] == 30)["timing"]
mid = str(min(range(1, len(pts) - 1), key=lambda i: abs(pts[i][0] - 0.5)))
for call in (lambda: ops.anim.timing_point_move(frame="20", index=mid, y="1e6", layer=str(a.id)),
             lambda: ops.anim.timing_handle_move(frame="20", index=mid, side="IN", x="-0.05", y="9e6", free="1",
                                                 layer=str(a.id))):
    assert call() == {'FINISHED'}
    far = 0.0
    for f in range(10, 31):
        go(f)
        x, y = a.location_x, a.location_y
        assert math.isfinite(x) and math.isfinite(y), (f, x, y)
        far = max(far, abs(x), abs(y))
    assert far < 40, ("the layer within reach of its path", far)
    timing = next(k for k in a.keyframes("position") if k["frame"] == 30)["timing"]
    assert all(-10.0 - 1e-4 <= p[1] <= 11.0 + 1e-4 for p in timing), timing
    assert ops.ed.undo() == {'FINISHED'}

# --- A breakdown on a curved path: on the path, not on the straight line between the keys -----------------------------
def seg_d(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0 if l2 == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


for variant in ("control point", "path handle", "smooth through 3 keys"):
    a = scene()
    a.location_x, a.location_y = 0.0, -1.0
    T = dict(layer=str(a.id))
    keys = {10: (0.0, 0.0), 40: (2.0, 0.0), 60: (2.0, 2.0)} if variant != "smooth through 3 keys" else         {10: (0.0, 0.0), 25: (1.0, 1.0), 40: (2.0, 0.0)}
    for f, (x, y) in keys.items():
        assert ops.anim.motion_path_move(frame=str(f), x=str(x), y=str(y), **T) == {'FINISHED'}
        a.keyframe_set("position", f, interp="SMOOTH")
    if variant == "control point":
        assert ops.anim.motion_path_control_add(frame="25", **T) == {'FINISHED'}
        c = wm.motion_path_controls()[0]
        assert ops.anim.motion_path_control_move(frame="40", index=str(c["index"]), x=str(c["at"][0]),
                                                 y=str(c["at"][1] + 0.8), **T) == {'FINISHED'}
    elif variant == "path handle":
        assert ops.anim.motion_path_handle(frame="40", side="IN", x="1.5", y="0.9", **T) == {'FINISHED'}
    frame = 30 if variant != "smooth through 3 keys" else 17
    path = wm.motion_paths()[0]["points"]
    assert ops.anim.motion_path_breakdown(frame=str(frame), factor="0.3", **T) == {'FINISHED'}
    go(frame)
    at = (a.location_x, a.location_y)
    off = min(seg_d(at, path[i], path[i + 1]) for i in range(len(path) - 1))
    # (What is left is the drawn path's chords between its dots.)
    assert off < 2e-3, ("the breakdown off the path it was on", variant, off)
    assert math.dist(at, keys[10]) > 0.1, ("on its way from the key before", variant, at)

print("test_motion_path_sweep_guards: ok")
