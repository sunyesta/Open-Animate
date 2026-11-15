"""Own Motion on two pupils (2 Axis Controllers with no sides, so playing nothing) that a look knob's side actions move,
the look knob itself moved by another controller's side (a head turn): what the actions add to each pupil is kept from
the frames worked out once, and stays kept while both pupils' timing is edited together, so a Path Timing drag works no
frame out again (it worked every frame out on every step: a controller was never counted as apart, nor a knob another
action moves, and each pupil's keys changing threw out the other's). The paths come out as working the frames out
makes them.

Run with:  OpenAnimate --background --python tests/test_motion_path_pupil_offsets.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

ops.wm.read_homefile()
doc = oanim.data.document
doc.path_show_all = True
doc.auto_key = True
ops.layer.new_bone()
rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
for name, x, y in (("Head", 6.0, 3.0), ("Look", 3.0, 3.0), ("Pupil_L", -1.0, 0.0), ("Pupil_R", 1.0, 0.0)):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(x), head_y=str(y), tail_x=str(x + 0.5), tail_y=str(y),
                                 parent="") == {'FINISHED'}


def mainline():
    ops.anim.action_set(name="")
    doc.frame_current = 0


def settle():
    doc.frame_current += 1
    doc.frame_current -= 1


def close(a, b, eps=1e-5):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    if isinstance(a, str) or a is None:
        return a == b
    return abs(a - b) < eps


def grab():
    return [(p["label"], [tuple(q) for q in p["points"]]) for p in wm.motion_paths(kept=False)]


def kept_frames():
    """The pupils' paths worked out again: how many of their frames came from what the actions add, kept, of how many."""
    wm.motion_path_places_clear()
    wm.motion_paths(kept=False)
    c = wm.motion_path_places()
    return c["offsets"], c["frames"]


# The pupils: controllers with no sides, keyed on the mainline.
for p in ("Pupil_L", "Pupil_R"):
    rig().select_bone(p)
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    # (With no sides its box has no size: kept in it, the knob couldn't move.)
    rig().bone_set(p, contain_knob=False)
# Look's Up side moves both pupils up.
assert ops.anim.action_new(name="Look Up") == {'FINISHED'}
doc.frame_current = 24
for p in ("Pupil_L", "Pupil_R"):
    k = bone(p)["knob"]
    rig().bone_set(p, knob=(k[0], k[1] + 0.3))
doc.frame_current = 25
mainline()
rig().select_bone("Look")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="UP", action="Look Up") == {'FINISHED'}
# Head's Right side moves Look's knob up (a head turn moving where the eyes look).
assert ops.anim.action_new(name="Head Right") == {'FINISHED'}
doc.frame_current = 24
rig().bone_set("Look", knob=(0.0, 20.0))
doc.frame_current = 25
mainline()
rig().select_bone("Head")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="Head Right") == {'FINISHED'}
settle()
mainline()
# The mainline: the head turns over 0-30, the pupils keyed on 10 and 30.
for f, head, d in ((10, (8.0, 0.0), 0.2), (30, (20.0, 0.0), 0.5)):
    doc.frame_current = f
    rig().bone_set("Head", knob=head)
    for p in ("Pupil_L", "Pupil_R"):
        k = bone(p)["knob"]
        rig().bone_set(p, knob=(k[0] + d, k[1]))
settle()
doc.auto_key = False

doc.motion_paths = True
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert doc.path_own_motion
layers.active = rig()
rig().select_bone("Pupil_L")
rig().select_bone("Pupil_R", extend=True)
labels = sorted(p["label"] for p in wm.motion_paths())
assert "Pupil_L head" in labels and "Pupil_R head" in labels, labels
doc.frame_current = 20

# Both pupils' 10-30 stretches picked, so a timing edit to one goes to the other.
row = lambda p: dict(layers=str(rig_id), path='bones["%s"].position' % p, kinds="304")
assert ops.anim.timeline_stretch_pick(frame="20", **row("Pupil_L")) == {'FINISHED'}
assert ops.anim.timeline_stretch_pick(frame="20", extend="1", **row("Pupil_R")) == {'FINISHED'}
wm.motion_paths(kept=False)

# --- Worked out once, then each pupil from its keys and what the actions add, kept --------------------------------------
args = dict(bone="Pupil_L", head="1", layer=str(rig_id))
for i, shape in enumerate(("EASE_IN", "EASE_OUT", "EASE_IN_OUT")):
    assert ops.anim.motion_path_stretch_shape(shape=shape, frame="20", **args) == {'FINISHED'}
    got, frames = kept_frames()
    assert frames > 15 and got == frames, (f"after a timing edit to both pupils {got} of their paths' {frames} frames "
                                           "came from what the actions add, kept")
    kept = grab()
    wm.motion_path_own_from_keys(False)
    worked = grab()
    wm.motion_path_own_from_keys(True)
    assert close(kept, worked), (shape, "kept", kept, "worked out", worked)
    assert len(set(tuple(pt) for lab, pts in kept for pt in pts)) > 10, "the paths move"

# --- A pupil with a side of its own plays it: never kept, worked out each time ------------------------------------------
assert ops.anim.action_new(name="Pupil_L Right") == {'FINISHED'}
doc.frame_current = 24
rig().bone_set("Look", knob=(0.0, 5.0))
doc.frame_current = 25
mainline()
rig().select_bone("Pupil_L")
assert ops.armature.controller_side(side="RIGHT", action="Pupil_L Right") == {'FINISHED'}
rig().select_bone("Pupil_L")
rig().select_bone("Pupil_R", extend=True)
doc.frame_current = 20
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="20", **args) == {'FINISHED'}
kept = grab()
wm.motion_path_own_from_keys(False)
worked = grab()
wm.motion_path_own_from_keys(True)
assert close(kept, worked), ("a pupil playing a side", kept, worked)

print("motion path pupil offsets: ok")
