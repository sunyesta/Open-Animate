"""P > Move to Layer: what Separate would take (the runs of selected points and the shapes they cover) goes into
another drawing (mesh.move_to_layer target=), on top and selected, the source losing it; it keeps its look (whatever
either layer's place), its keys, and its weights while the target follows the same bone layer (under other bones they
are weighed as new points). The target becomes active. P opens the menu (New Layer is Separate); Pick Layer's click and
the menu's list (the drawings moved into last first, found by typing) go the same way. One undo step; CANCELLED, with
no step, for a reference, the drawing the selection is in, or nothing to move.

Run with:  OpenAnimate --background --python tests/test_move_to_layer.py
"""

import math
import os
import tempfile

import _oanim
import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def all_close(a, b, eps=1e-4):
    return len(a) == len(b) and all(close(p, q, eps) for p, q in zip(a, b))


def fresh(layer):
    return next(l for l in oanim.data.layers.all() if l.id == layer.id)


def reopen():
    """Saved and opened again, so Python edits (no undo step of their own) are what undo goes back to."""
    path = os.path.join(tempfile.gettempdir(), "oa_move_to_layer_%d.oanim" % os.getpid())
    ops.wm.save_copy(filepath=path)
    assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
    os.remove(path)


def two_drawings():
    """A: a line of three points and a closed square; B: a triangle, moved, turned and scaled."""
    global doc, layers
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    assert ops.layer.new() == {'FINISHED'}
    a = layers.active
    a.name = "A"
    a.add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 1.0)])
    a.add_curve([(3.0, 0.0), (4.0, 0.0), (4.0, 1.0), (3.0, 1.0)], closed=True, fill=True)
    assert ops.layer.new() == {'FINISHED'}
    b = layers.active
    b.name = "B"
    b.add_curve([(-2.0, -2.0), (-1.0, -2.0), (-1.5, -1.0)], closed=True, fill=True)
    b.location_x = 0.7
    b.location_y = -0.3
    b.rotation = 30.0
    b.scale_x = 1.5
    reopen()
    return by_name("A"), by_name("B")


def by_name(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def pick(layer, picked):
    layers.active = layer
    ops.mesh.select_none()
    layer.select_points(picked)


def shown_world(layer, indexes=None):
    pts = fresh(layer).shown()[0]
    return [pts[i] for i in (range(len(pts)) if indexes is None else indexes)]


def steps():
    return wm.undo_history()[1]


# --- The square into B: gone from A, on top of B and selected, looking as it did; B active; one undo step -----------
a, b = two_drawings()
pick(a, [3, 4, 5, 6])
square = shown_world(a, [3, 4, 5, 6])
had_a, had_b = a.point_count, b.point_count
step = steps()
assert ops.mesh.move_to_layer(target=str(b.id)) == {'FINISHED'}
assert steps() == step + 1
a, b = fresh(a), fresh(b)
assert a.point_count == had_a - 4 and a.shape_count == 1, (a.point_count, a.shapes)
assert b.point_count == had_b + 4 and b.shape_count == 2, (b.point_count, b.shapes)
assert [p[2] for p in b.points] == [False] * had_b + [True] * 4, "the moved points selected"
assert not any(p[2] for p in a.points)
assert all_close(shown_world(b, range(had_b, had_b + 4)), square), (shown_world(b), square)
assert layers.active.id == b.id
assert ops.ed.undo() == {'FINISHED'}
assert fresh(a).point_count == had_a and fresh(b).point_count == had_b, "undone together"
assert ops.ed.redo() == {'FINISHED'}
assert fresh(b).point_count == had_b + 4

# --- By name too; a piece of line takes its run, the point other curves don't use goes ------------------------------
a, b = two_drawings()
pick(a, [0, 1])
assert ops.mesh.move_to_layer(target="B") == {'FINISHED'}
assert fresh(b).curve_count == 2 and fresh(b).point_count == 5, (fresh(b).curve_count, fresh(b).point_count)

# --- Refused, with no undo step: a reference, the drawing the selection is in, nothing there, a group -----------------
a, b = two_drawings()
layers.active = b
assert ops.layer.make_reference() == {'FINISHED'}
ref = layers.active
assert ops.layer.new_group() == {'FINISHED'}
group = layers.active
pick(fresh(a), [3, 4, 5, 6])
step = steps()
for target in (ref.id, a.id, group.id, 999999):
    assert ops.mesh.move_to_layer(target=str(target)) == {'CANCELLED'}, target
assert steps() == step
pick(fresh(a), [0])
assert ops.mesh.move_to_layer(target=str(b.id)) == {'CANCELLED'}, "a lone point: no piece to move"
assert steps() == step

# --- Keys go along: each keyed frame shows as it did --------------------------------------------------------------------
a, b = two_drawings()
doc.auto_key = True
doc.frame_current = 10
fresh(a).set_point(4, (4.5, -0.5))
doc.frame_current = 0
reopen()
a, b = by_name("A"), by_name("B")
looks = {}
for f in (0, 5, 10):
    doc.frame_current = f
    looks[f] = shown_world(a, [3, 4, 5, 6])
doc.frame_current = 5
pick(a, [3, 4, 5, 6])
had_b = b.point_count
assert ops.mesh.move_to_layer(target=str(b.id)) == {'FINISHED'}
for f in (0, 10, 5):
    doc.frame_current = f
    assert all_close(shown_world(b, range(had_b, had_b + 4)), looks[f], 1e-3), (f, shown_world(b), looks[f])


# --- Weights: kept under the same bones, weighed as new points under others --------------------------------------------
def rigged():
    """Two bone layers, each with a bone turned on frame 5; R1 holds drawings Art (weighted to its bone) and Same, R2
    holds Other."""
    global doc, layers
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    made = {}
    for rig_name, drawings in (("R1", ("Art", "Same")), ("R2", ("Other",))):
        layers.active = layers.all()[0]
        assert ops.layer.new_bone() == {'FINISHED'}
        rig = layers.active
        rig.name = rig_name
        assert ops.armature.bone_add(name="Bone", head_x="0", head_y="0", tail_x="3", tail_y="0", parent="") == {'FINISHED'}
        ops.armature.select_none()
        for name in drawings:
            assert ops.layer.new() == {'FINISHED'}
            l = layers.active
            l.name = name
            assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
            l = fresh(l)
            l.add_curve([(0.5, 0.2), (1.5, 0.3), (2.5, 0.2)])
            l.edit_with_bones = True
            layers.active = l
            assert ops.weight.automatic() == {'FINISHED'}
        made[rig_name] = rig
    doc.auto_key = True
    doc.frame_current = 5
    for rig in made.values():
        fresh(rig).bone_set("Bone", angle=math.radians(40.0))
    doc.frame_current = 0
    reopen()


rigged()
art, same = by_name("Art"), by_name("Same")
weights = [dict(w) for w in art.weights]
pick(art, [0, 1, 2])
assert ops.mesh.move_to_layer(target=str(same.id)) == {'FINISHED'}
assert [dict(w) for w in fresh(same).weights][3:] == weights, (fresh(same).weights, weights)
doc.frame_current = 5
assert fresh(same).shown()[0][3:] == fresh(same).shown()[0][:3], "bent by the bone as Same's own line is"

rigged()
art, other = by_name("Art"), by_name("Other")
pick(art, [0, 1, 2])
assert ops.mesh.move_to_layer(target=str(other.id)) == {'FINISHED'}
# Connected to none of Other's points: none (R1's bone ids mean nothing in R2, though R2 has a bone of that id too).
assert [dict(w) for w in fresh(other).weights][3:] == [{}] * 3, fresh(other).weights

# --- P opens the menu; its list puts the drawings moved into last first and finds by typing; Pick Layer's click -----
a, b = two_drawings()
assert ops.layer.new() == {'FINISHED'}
c = layers.active
c.name = "Cup"
c.add_curve([(5.0, 5.0), (6.0, 5.0), (6.0, 6.0)])
reopen()
a, b, c = by_name("A"), by_name("B"), by_name("Cup")
pick(a, [3, 4, 5, 6])
count = len(layers.all())
assert wm.event_simulate("P", area="Viewport"), "P opens Move to Layer"
assert len(layers.all()) == count and fresh(a).point_count == 7, "a menu: nothing separated yet"
rows = _oanim.move_menu_rows("")
assert rows[:2] == [c.id, b.id] and a.id not in rows, (rows, c.id, b.id)
assert _oanim.move_menu_rows("cu") == [c.id], _oanim.move_menu_rows("cu")
assert ops.mesh.move_to_layer(target=str(b.id)) == {'FINISHED'}
pick(fresh(a), [0, 1])
assert _oanim.move_menu_rows("")[:2] == [b.id, c.id], "moved into last: first"
step = steps()
assert not _oanim.move_pick_click(fresh(a).id), "the drawing it is in: refused, still picking"
assert steps() == step
assert _oanim.move_pick_click(c.id)
assert steps() == step + 1 and fresh(c).point_count == 5

print("test_move_to_layer: OK")
