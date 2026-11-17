"""R dragged on bones with points picked too (A on a bone layer picks the points of the drawings edited with its bones):
every update starts again from the drawings as the drag began, so the handles of the points a turning bone bends turn
with them as long as they were, however many updates the drag takes (each update grew them a little more from the last:
34% longer after ten), and the drag ends where Rotate Bones puts them.

Run with:  OpenAnimate --background --python tests/test_bone_drag_points.py
"""

import math

import oanim

doc = oanim.data.document
layers = oanim.data.layers


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def turned(p, degrees):
    a = math.radians(degrees)
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a))


def fresh(layer):
    return next(l for l in layers.all() if l.id == layer.id)


# A jaw bone and a top lip bone sharing a lip's weights (one turning bends it unevenly, which is what grew the handles),
# the lip inside a group inside the bone layer (as a face's mouth is), posed on frame 10.
assert oanim.ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
assert oanim.ops.armature.bone_add(name="Jaw", head_x="3", head_y="0", tail_x="3", tail_y="-1", parent="") == {'FINISHED'}
assert oanim.ops.armature.bone_add(name="Top", head_x="2.6", head_y="0.4", tail_x="3.4", tail_y="0.4", parent="") == {'FINISHED'}
assert oanim.ops.layer.new_group() == {'FINISHED'}
mouth = layers.active
assert oanim.ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
oanim.ops.layer.new()
lip = layers.active
assert oanim.ops.layer.move_to_group(group=str(fresh(mouth).id)) == {'FINISHED'}
lip = fresh(lip)
lip.add_curve([(3.3, 0.0), (3.0, 0.1), (2.7, 0.0), (3.0, -0.1)])
lip.edit_with_bones = True
layers.active = lip
assert oanim.ops.weight.automatic() == {'FINISHED'}
doc.auto_key = True
doc.frame_current = 10
layers.active = rig
oanim.ops.armature.select_none()
rig.select_bone("Jaw")
lip.selected = True
lip.select_points(range(4))
layers.active = rig


def handles():
    """Each handle's end from its point, as they show."""
    pts, curves = lip.shown()
    return [(c[1][0] - pts[c[0]][0], c[1][1] - pts[c[0]][1], c[2][0] - pts[c[0]][0], c[2][1] - pts[c[0]][1])
            for c in curves[0][0]]


was = handles()
assert sum(math.hypot(h[0], h[1]) > 1e-3 for h in was) >= 2, was


def want(degrees):
    return [turned(h[:2], degrees) + turned(h[2:], degrees) for h in was]


# --- The same angle held over many updates: the handles stay put, turned as far as the bone -----------------------------
seen = []
assert oanim.wm.bone_rotate_drag([20.0] * 8, confirm=False, during=lambda d: seen.append(handles()))
for i, h in enumerate(seen):
    assert all(close(a, b) for a, b in zip(h, want(20.0))), ("update %d" % (i + 1), h, want(20.0))
assert all(close(a, b) for a, b in zip(handles(), was)), "cancelled: as they were"

# --- A drag turning a little more each update, confirmed: as long as they were all along, and where Rotate Bones puts them
seen = []
assert oanim.wm.bone_rotate_drag([3.0 * i for i in range(1, 11)], during=lambda d: seen.append((d, handles())))
for d, h in seen:
    assert all(close(a, b) for a, b in zip(h, want(d))), (d, h, want(d))
assert all(close(a, b) for a, b in zip(handles(), want(30.0))), handles()

print("test_bone_drag_points: OK")
