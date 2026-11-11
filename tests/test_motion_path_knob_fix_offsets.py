"""Own Motion on a bone a knob's actions move, the knob followed by a fix: what the actions add is kept from the frames
worked out once and reused while only the bone's keys change, so dragging its keys or control points works no frame out
again (a head bone a head-turn knob moves took a third of a second a drag step, every frame worked out each time: the
fix's line in the knob's keys was taken as something moving the knob). A control point's frames are kept too, beside the
path's, which a drag keeps. The path comes out as working the frames out makes it.

Run with:  OpenAnimate --background --python tests/test_motion_path_knob_fix_offsets.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

ops.wm.read_homefile()
doc.auto_key = True
ops.layer.new_bone()
rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
ops.armature.select_none()
ops.armature.bone_add(name="Head", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
ops.armature.select_none()
ops.armature.bone_add(name="Lid", head_x="0.0", head_y="6.0", tail_x="1.0", tail_y="6.0")
ops.armature.select_none()


def settle():
    doc.frame_current += 1
    doc.frame_current -= 1


def mainline():
    ops.anim.action_set(name="")
    doc.frame_current = 0


def close(a, b, eps=1e-5):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    if isinstance(a, str) or a is None:
        return a == b
    return abs(a - b) < eps


def grab():
    return [(p["label"], [tuple(q) for q in p["points"]]) for p in wm.motion_paths(kept=False)]


def kept_frames():
    """Head's path worked out again: how many of its frames came from what the actions add, kept, of how many."""
    wm.motion_path_places_clear()
    wm.motion_paths(kept=False)
    c = wm.motion_path_places()
    return c["offsets"], c["frames"]


# The knob's sides move Head (as a head turn moves the head).
for side, move in (("Right", (0.4, 0.0)), ("Up", (0.0, 0.3))):
    assert ops.anim.action_new(name="Knob " + side) == {'FINISHED'}
    doc.frame_current = 24
    p = bone("Head")["position"]
    rig().bone_set("Head", position=(p[0] + move[0], p[1] + move[1]))
    doc.frame_current = 25
    mainline()
rig().select_bone("Knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
for side in ("RIGHT", "UP"):
    assert ops.armature.controller_side(side=side, action="Knob " + side.title()) == {'FINISHED'}
# A fix following the knob, turning Lid (not Head) where the knob ends up and right.
rig().select_bone("Knob")
assert ops.armature.bone_fix_new(bones="Knob") == {'FINISHED'}
doc.frame_current = 20
rig().bone_set("Knob", knob=(24.0, 24.0))
rig().bone_set("Lid", angle=bone("Lid")["angle"] + 0.5)
settle()
mainline()
assert rig().bone_fixes, "a fix follows the knob"
# On the mainline: the knob turns the head over 10-40; the head keyed on 10 and 40 too.
for f, knob, head in ((10, (0.0, 0.0), (0.0, 0.0)), (40, (20.0, 12.0), (0.3, 0.1))):
    doc.frame_current = f
    rig().bone_set("Knob", knob=knob)
    s = bone("Head")["setup_position"]
    rig().bone_set("Head", position=(s[0] + head[0], s[1] + head[1]))
settle()
doc.auto_key = False

doc.motion_paths = True
doc.path_all = True
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert doc.path_own_motion
layers.active = rig()
rig().select_bone("Head")
args = dict(bone="Head", head="1", layer=str(rig_id))
assert ops.anim.motion_path_select(frame="40", **args) == {'FINISHED'}
assert "Head head" in [p["label"] for p in wm.motion_paths()], [p["label"] for p in wm.motion_paths()]
doc.frame_current = 25

# --- Worked out once, then from its keys and what the actions add, kept ---------------------------------------------
dot = next(p for p in wm.motion_paths() if p["label"] == "Head head")
at = dot["points"][40 - dot["first"]]
assert ops.anim.motion_path_move(frame="40", x=str(at[0] + 0.05), y=str(at[1]), **args) == {'FINISHED'}
got, frames = kept_frames()
assert frames > 20 and got == frames, (f"after an edit to Head's key {got} of its path's {frames} frames came from what "
                                       "the knob's actions add, kept: the fix's line in the knob's keys moves nothing")
kept = grab()
wm.motion_path_own_from_keys(False)
frames = grab()
wm.motion_path_own_from_keys(True)
assert close(kept, frames), ("kept", kept, "worked out", frames)

# --- A control point dragged: its frames kept too, the path's kept beside them --------------------------------------
assert ops.anim.motion_path_control_add(frame="25", **args) == {'FINISHED'}
c = next(c for c in wm.motion_path_controls() if c["end"] == 40)
for i in range(3):
    assert ops.anim.motion_path_control_move(frame="40", index=str(c["index"]), x=str(c["at"][0] + 0.02 * (i + 1)),
                                             y=str(c["at"][1] - 0.01 * (i + 1)), **args) == {'FINISHED'}
    kept_frames()
got, frames = kept_frames()
assert got == frames, f"after dragging a control point {got} of Head's path's {frames} frames came from what was kept"
kept = grab()
wm.motion_path_own_from_keys(False)
frames = grab()
wm.motion_path_own_from_keys(True)
assert close(kept, frames), ("after a control point drag, kept", kept, "worked out", frames)

print("test_motion_path_knob_fix_offsets: ok")
