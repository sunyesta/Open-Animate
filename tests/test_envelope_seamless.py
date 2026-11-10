"""Envelope Deform's Seamless method: Standard (each point turns and stretches with its nearest place on the shape) but
blended where two places are about as near, so the drawing never tears.

The shape is an L: (-0.6, 0) along to the corner (0, 0), then up to (0, 0.6); its top end is moved to (0.3, 0.6), so the
upright arm turns and the lying one stays. Inside the bend Standard binds a point to whichever arm is nearer and tears
along the line where they tie; past the corner its wedge follows the lying arm's end and tears where the upright arm's
slab begins. Seamless goes smoothly across both, and is Standard where one place is nearest by far.

Run with:  OpenAnimate --background --python tests/test_envelope_seamless.py
"""
import math
import os
import shutil
import tempfile

import oanim

ops = oanim.ops
doc = oanim.data.document
layers = oanim.data.layers
doc.frame_current = 0


def new_layer(name):
    ops.layer.new()
    layer = layers.active
    layer.name = name
    return layer


def straight_handles(points, closed):
    n = len(points)
    r = []
    for i, p in enumerate(points):
        prev = points[i - 1] if closed or i > 0 else None
        nxt = points[(i + 1) % n] if closed or i + 1 < n else None
        h_in = (p[0] + (prev[0] - p[0]) / 3, p[1] + (prev[1] - p[1]) / 3) if prev else None
        h_out = (p[0] + (nxt[0] - p[0]) / 3, p[1] + (nxt[1] - p[1]) / 3) if nxt else None
        r.append((h_in, h_out))
    return r


def pose(layer, points, closed):
    """The shape's points, straight between them (each handle a third of the way to its neighbour)."""
    for i, p in enumerate(points):
        layer.set_point(i, p)
    for i, (h_in, h_out) in enumerate(straight_handles(points, closed)):
        for side, h in (("IN", h_in), ("OUT", h_out)):
            if h is not None:
                layer.place_handle(0, i, side, h, keep_other=True)


def shape_layer(name, points, closed):
    layer = new_layer(name)
    layer.add_curve(points, closed=closed)
    pose(layer, points, closed)
    return layer


def bent_by(shape, name, points, kind="ENVELOPE_DEFORM", **settings):
    art = new_layer(name)
    art.add_curve(points)
    assert ops.object.modifier_add(type=kind) == {'FINISHED'}
    args = dict(layer=shape.name, shape=shape.shapes[0][0], precision=0.0, envelope_method="SEAMLESS")
    if kind == "CURVE_DEFORM":
        args["curve_method"] = "ENVELOPE"
    args.update(settings)
    art.modifier_set(0, **args)
    m = art.modifiers[0]
    assert m["envelope_method"] == "SEAMLESS", m
    return art


def evaluated(art, method):
    art.modifier_set(0, envelope_method=method)
    got = art.evaluated()[0]
    art.modifier_set(0, envelope_method="SEAMLESS")
    return got


def worst_jump(got):
    return max(math.dist(a, b) for a, b in zip(got, got[1:]))


REST_L = [(-0.6, 0.0), (0.0, 0.0), (0.0, 0.6)]
BENT_L = [(-0.6, 0.0), (0.0, 0.0), (0.3, 0.6)]
N = 401

l_shape = shape_layer("L", REST_L, False)
# Inside the bend, across the line where the two arms tie (x = -y): 0.3 above the lying arm, from 0.45 to 0.15 left of
# the upright one.
across_bend = [(-0.45 + 0.3 * i / (N - 1), 0.3) for i in range(N)]
bend = bent_by(l_shape, "Bend", across_bend)
# Past the corner, round it at 0.3: from below the lying arm's end, through the wedge, into the upright arm's slab.
round_corner = [(0.3 * math.cos(a), 0.3 * math.sin(a))
                for a in (math.radians(-120.0 + 140.0 * i / (N - 1)) for i in range(N))]
corner = bent_by(l_shape, "Corner", round_corner, kind="CURVE_DEFORM")
# Near the lying arm, far from the upright one: one place is nearest by far.
lone = [(-0.5 + 0.2 * i / 20, 0.05 + 0.02 * (i % 3)) for i in range(21)]
alone = bent_by(l_shape, "Alone", lone)

square_pts = [(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3)]
square = shape_layer("Square", square_pts, True)
ring = [(0.45 * math.cos(a), 0.45 * math.sin(a)) for a in (2 * math.pi * i / 720 for i in range(721))]
loop = bent_by(square, "Loop", ring)
# A smooth S-curve (its handles left to the curve), where below its rise a point is about as near two places on it with
# a low ridge between them, and nearer a third: the two swap which is nearer, and the blend mustn't jump as they do
# (here Standard, following only the nearest, doesn't either).
REST_S = [(-0.6, 0.0), (-0.2, 0.25), (0.2, -0.25), (0.6, 0.0)]
BENT_S = [(-0.6, 0.0), (-0.2, 0.4), (0.2, -0.1), (0.6, 0.15)]
s_shape = new_layer("S")
s_shape.add_curve(REST_S)
under_rise = [(-0.26 + 0.03 * i / (N - 1), 0.0917) for i in range(N)]
twins = bent_by(s_shape, "Twins", under_rise)
lower_down = [(-0.25 + 0.1 * i / (N - 1), 0.0) for i in range(N)]
twins_low = bent_by(s_shape, "Twins low", lower_down)
capsule = bent_by(l_shape, "Capsule", across_bend, influence="CAPSULE", influence_symmetric=True,
                  influence_left=0.5, influence_right=0.5, influence_begin=0.2, influence_end=0.2,
                  influence_fade=0.1)

# At rest nothing moves.
for art, points in ((bend, across_bend), (corner, round_corner), (alone, lone), (loop, ring), (capsule, across_bend),
                    (twins, under_rise), (twins_low, lower_down)):
    got = art.evaluated()[0]
    assert all(math.dist(g, p) < 1e-5 for g, p in zip(got, points)), (art.name, "moved at rest")

doc.frame_current = 8
pose(l_shape, BENT_L, False)
pose(square, [(-0.3, -0.3), (0.3, -0.3), (0.5, 0.45), (-0.3, 0.3)], True)
for i, q in enumerate(BENT_S):
    s_shape.set_point(i, q)

step = math.dist(across_bend[0], across_bend[1])

# Across the bend Standard tears and Seamless doesn't.
standard = worst_jump(evaluated(bend, "STANDARD"))
seamless = worst_jump(bend.evaluated()[0])
assert standard > 0.03, ("Standard tears inside the bend", standard)
assert seamless < 5 * step, ("Seamless goes smoothly across the bend", seamless, step)
print("bend: Standard jumps %.4f, Seamless at most %.5f (step %.5f)" % (standard, seamless, step))
# Each side, away from the tie, it goes the way its nearer arm goes, mostly.
got = bend.evaluated()[0]
std = evaluated(bend, "STANDARD")
assert math.dist(got[0], std[0]) < math.dist(got[N // 2], std[N // 2]) + 0.05

# Round the corner too.
step_c = math.dist(round_corner[0], round_corner[1])
standard = worst_jump(evaluated(corner, "STANDARD"))
seamless = worst_jump(corner.evaluated()[0])
assert standard > 0.03, ("Standard tears past the corner", standard)
assert seamless < 5 * step_c, ("Seamless turns smoothly round the corner", seamless, step_c)
print("corner: Standard jumps %.4f, Seamless at most %.5f (step %.5f)" % (standard, seamless, step_c))

# Under the S-curve's rise, where two places swap which is nearer.
step_t = math.dist(under_rise[0], under_rise[1])
standard = worst_jump(evaluated(twins, "STANDARD"))
seamless = worst_jump(twins.evaluated()[0])
# (Counting only the first lower dip past each, it tears here by 0.013. Its frames are Standard's, which step by up to
# 0.0003 here as a point passes from one to the next.)
assert seamless < 0.004, ("Seamless goes smoothly where two places swap", seamless, step_t)
print("twins: Standard jumps %.4f, Seamless at most %.5f" % (standard, seamless))
# Lower down, where the twins swap without the third nearer: without the pair's says growing as they tie, 0.037.
standard = worst_jump(evaluated(twins_low, "STANDARD"))
seamless = worst_jump(twins_low.evaluated()[0])
assert standard > 0.03, ("Standard tears lower down", standard)
assert seamless < 0.004, ("Seamless goes smoothly lower down", seamless)
print("twins lower down: Standard jumps %.4f, Seamless at most %.5f" % (standard, seamless))

# One place nearest by far: Standard exactly.
got, std = alone.evaluated()[0], evaluated(alone, "STANDARD")
worst = max(math.dist(a, b) for a, b in zip(got, std))
assert worst < 1e-5, ("Seamless is Standard where one place is nearest", worst)

# A loop: smooth all round, its closing corner too, and it moves.
got = loop.evaluated()[0]
step_l = math.dist(ring[0], ring[1])
assert worst_jump(got) < 5 * step_l, ("the loop", worst_jump(got), step_l)
assert max(math.dist(g, p) for g, p in zip(got, ring)) > 0.05
assert math.dist(got[0], got[-1]) < 1e-5

# With Influence's Capsule (each segment on its own): smooth, and it moves.
got = capsule.evaluated()[0]
assert worst_jump(got) < 5 * step, ("the capsule", worst_jump(got))
assert max(math.dist(g, p) for g, p in zip(got, across_bend)) > 0.01

# Saved and opened again, the method comes back.
folder = tempfile.mkdtemp()
try:
    path = os.path.join(folder, "seamless.oanim")
    assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
    for name in ("Bend", "Corner", "Loop"):
        m = next(l for l in oanim.data.layers.all() if l.name == name).modifiers[0]
        assert m["envelope_method"] == "SEAMLESS", (name, m)
finally:
    shutil.rmtree(folder, ignore_errors=True)

print("test_envelope_seamless: OK")
