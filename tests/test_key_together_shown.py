"""Key Together and Key Whole Drawing turned on give keys the timing most of the layers (or points) have on their
frame: the frame shown takes the new timing at once, the same as leaving it and coming back (from a bug sweep: it
showed the old timing until the playhead moved). Each section starts from a new file.

Run with:  OpenAnimate --background --python tests/test_key_together_shown.py
"""

import oanim

ops, L = oanim.ops, oanim.data.layers


def fresh():
    assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    d = oanim.data.document
    d.auto_key = True
    d.auto_freeze_keys = False
    return d


def drawing(name, y=0.0):
    ops.layer.new()
    l = L.active
    l.name = name
    l.add_curve([(0.0, y), (1.0, y)])
    l.key_together = False
    l.key_whole_drawing = False
    return l


def group_of(ls):
    for l in L.all():
        l.selected = l.id in [x.id for x in ls]
    assert ops.layer.group() == {'FINISHED'}
    g = L.active
    g.key_together = False
    return g


def reached_again(d, read):
    f = d.frame_current
    d.frame_current = f + 1
    d.frame_current = f
    return read()


# --- Key Together: a layer's Ease In/Out stretch takes the Linear timing its group's other layers have ---------------
d = fresh()
a, b, c = drawing("a"), drawing("b", 2.0), drawing("c", 4.0)
group = group_of([a, b, c])
d.frame_current = 20
for l in (a, b, c):
    l.location_x = 3.0
a.keyframe_set("position", 20, interp="EASE_IN_OUT")
for l in (b, c):
    l.keyframe_set("position", 20, interp="LINEAR")
d.frame_current = 8
d.frame_current = 7          # between the keys, where the timing shows
eased = a.location_x
L.active = group
assert ops.anim.key_together_set(layer=str(group.id), on="1") == {'FINISHED'}
shown = a.location_x
again = reached_again(d, lambda: a.location_x)
assert abs(again - b.location_x) < 1e-5 and abs(again - eased) > 0.1, ("a takes the others' timing", eased, again)
assert abs(shown - again) < 1e-5, ("the frame shown takes the new timing at once", shown, again)

# --- Key Whole Drawing: a point's Ease In/Out stretch takes the Linear timing the drawing's other points have -------
d = fresh()
l = drawing("w")
l.add_curve([(0.0, 1.0), (1.0, 1.0)])
d.frame_current = 20
for i in range(4):
    p = l.points[i]
    l.set_point(i, (p[0] + 2.0, p[1]))
l.keyframe_set("points[0].pos", 20, interp="EASE_IN_OUT")
for i in (1, 2, 3):
    l.keyframe_set("points[%d].pos" % i, 20, interp="LINEAR")
d.frame_current = 8
d.frame_current = 7
eased = l.points[0][0]
L.active = l
assert ops.anim.key_together_set(layer=str(l.id), drawing="1", on="1") == {'FINISHED'}
shown = l.points[0][0]
again = reached_again(d, lambda: l.points[0][0])
assert abs(again - eased) > 0.1, ("the point takes the others' timing", eased, again)
assert abs(shown - again) < 1e-5, ("the frame shown takes the new timing at once", shown, again)

print("Key Together shown tests passed")
