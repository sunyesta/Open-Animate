"""Motion paths during a timing drag: with Own Motion only the paths' own position keys change (a stretch's shape, a
dot slid, a timing curve's point or handle moved), so the viewport slides each dot by its value's change through the
path's own slopes instead of working every frame out again on each step of the drag (motion_paths_slide), and works them
out once the drag ends. The slid dots and the lines between them come out as working them out makes them, on a curved
path drawn turned and scaled (a layer in a turned group, a bone in a turned rig), past the key in an overshoot, each
slide from the last as a drag goes; anything else changing can't be slid, and the paths are worked out again, as a
knob kept in its box can't.

Run with:  OpenAnimate --background --python tests/test_motion_path_timing_slide.py
"""

import math

import oanim

ops, wm = oanim.ops, oanim.wm
doc = oanim.data.document
layers = oanim.data.layers


def worst(slid, made):
    """The furthest a slid dot, or a point of a slid line between dots, is from working them out."""
    assert slid is not None, "only the timing changed: the paths slide"
    made = {p["label"]: p for p in made}
    assert sorted(made) == sorted(p["label"] for p in slid), (sorted(made), [p["label"] for p in slid])
    far = 0.0
    for s in slid:
        m = made[s["label"]]
        assert s["first"] == m["first"] and len(s["points"]) == len(m["points"])
        for a, b in zip(s["points"], m["points"]):
            far = max(far, math.dist(a, b))
        for i, (la, lb) in enumerate(zip(s["shape"], m["shape"])):
            # The line between two dots: its points as many and in the same places (it is cut from one line).
            assert abs(len(la) - len(lb)) <= 1, (s["label"], i, len(la), len(lb))
            for a, b in zip(la, lb):
                far = max(far, math.dist(a, b))
    return far


def check(what, eps=2e-3):
    slid = wm.motion_paths_held_slid()
    far = worst(slid, wm.motion_paths(kept=False))
    assert far < eps, (what, "slid dots off where working them out puts them by", far)
    moved = sum(len(p["points"]) for p in slid)
    assert moved > 20, (what, moved)


doc.motion_paths = True
doc.path_before, doc.path_after = 40, 40
doc.auto_key = False
assert ops.wm.tool_motion_path() == {'FINISHED'}

# --- A layer's origin on a curve, in a group turned and scaled ---------------------------------------------------------
ops.layer.new()
dot = layers.active
dot.key_together = False
dot.add_curve([(0.0, 0.0), (0.1, 0.0)])
assert ops.layer.group() == {'FINISHED'}
group = next(l for l in layers.all() if l.id == layers.active.id)
doc.frame_current = 0
group.rotation, group.scale_x, group.scale_y = 0.6, 1.7, 1.7
dot = next(l for l in layers.all() if l.id == dot.id)
dot.location_x, dot.location_y = -3.0, -3.0
for other in layers.all():
    other.selected = other.id == dot.id
layers.active = dot
for f, x, y in ((10, 0.0, 0.0), (20, 2.0, 1.5), (30, 4.0, -0.5), (40, 5.0, 2.0)):
    assert ops.anim.motion_path_move(frame=str(f), x=str(x), y=str(y), layer=str(dot.id)) == {'FINISHED'}
    dot.keyframe_set("position", f, interp="SMOOTH")
doc.frame_current = 25
args = dict(layer=str(dot.id))
assert len(wm.motion_paths(kept=False)) == 1

assert wm.motion_paths_hold() == 1
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="25", **args) == {'FINISHED'}
check("a stretch eased in")
assert ops.anim.motion_path_slide(frame="24", progress="0.15", **args) == {'FINISHED'}
check("a dot slid (each slide from the last)")
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN_OUT", frame="15", **args) == {'FINISHED'}
check("another stretch")
assert ops.anim.timing_point_move(frame="25", index="1", x="0.4", y="0.7", **args) in ({'FINISHED'}, {'CANCELLED'})
check("a timing point moved")

# Past the key and back before the start (a timing curve going over 1 and under 0): the dots go past it too.
assert ops.anim.motion_path_slide(frame="28", progress="1.2", **args) == {'FINISHED'}
assert ops.anim.motion_path_slide(frame="21", progress="-0.15", **args) == {'FINISHED'}
over = wm.motion_paths(kept=False)[0]["overshoot"]
assert 28 in over and 21 in over, ("it overshoots", over)
check("an overshoot")
# A key's value moved changes only its keys too: the dots move with it.
assert ops.anim.motion_path_move(frame="20", x="2.5", y="1.0", layer=str(dot.id)) == {'FINISHED'}
check("a key moved")

# Anything else changing (what holds the rest as shown) can't be slid: worked out again.
wm.motion_paths_hold()
group = next(l for l in layers.all() if l.id == group.id)
group.rotation = 0.9
assert wm.motion_paths_held_slid() is None, "the group turned: worked out again"

# --- A bone's head in a rig turned and scaled --------------------------------------------------------------------------
ops.layer.new_bone()
rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
doc.frame_current = 0
rig().rotation, rig().scale_x, rig().scale_y = -0.4, 0.8, 0.8
assert ops.armature.bone_add(name="Hand", head_x="1", head_y="1", tail_x="2", tail_y="1", parent="") == {'FINISHED'}
doc.auto_key = True
for f, x, y in ((10, 1.0, 1.0), (20, 3.0, 4.0), (30, 6.0, 2.0)):
    doc.frame_current = f
    rig().bone_set("Hand", position=(x, y))
doc.auto_key = False
for other in layers.all():
    other.selected = other.id == rig_id
layers.active = rig()
rig().select_bone("Hand")
doc.frame_current = 15
labels = [p["label"] for p in wm.motion_paths(kept=False)]
assert labels == ["Hand tip"], labels
bargs = dict(bone="Hand", layer=str(rig_id))
assert wm.motion_paths_hold() >= 1
assert ops.anim.motion_path_stretch_shape(shape="EASE_OUT", frame="15", **bargs) == {'FINISHED'}
check("a bone's stretch eased out")
assert ops.anim.motion_path_slide(frame="16", progress="0.8", **bargs) == {'FINISHED'}
check("a bone's dot slid")

# A knob kept in its box goes with its value only inside it: never slid.
doc.frame_current = 0
rig().select_bone("Hand")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
rig().bone_set("Hand", contain_knob=True)
doc.frame_current = 15
rig().select_bone("Hand")
assert wm.motion_paths_hold() >= 1
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="15", **bargs) == {'FINISHED'}
assert wm.motion_paths_held_slid() is None, "a contained knob: worked out again"

print("motion path timing slide: ok")
