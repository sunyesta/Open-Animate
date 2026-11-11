"""Own Motion on a knob a fix follows: the fix's keys on the knob are its line, which it never plays onto the knob, so the
knob's path comes from its own keys, with no frame of the document worked out (a head-turn knob in a rig whose pupils
look inside bent eyes took a fifth of a second a drag, every frame worked out). The path, its key handles and control
points come out as working the frames out makes them.

Run with:  OpenAnimate --background --python tests/test_motion_path_fix_line.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def grab(kept):
    """The paths' dots and their keys' handles, as numbers."""
    out = []
    for p in wm.motion_paths(kept=kept):
        assert p["own_motion"], p["label"]
        out.append((p["label"], [tuple(q) for q in p["points"]],
                    [(h["frame"], h["in"], h["out"]) for h in p["handles"]]))
    return out


def close(a, b, eps=1e-5):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    if isinstance(a, str) or a is None:
        return a == b
    return abs(a - b) < eps


def worked():
    """How many copies of the document the knob's path was worked out on."""
    wm.motion_path_places_clear()
    wm.motion_paths(kept=False)
    return wm.motion_path_places()["copies"]


ops.wm.read_homefile()
doc.auto_key = True
ops.layer.new_bone()
rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
ops.armature.select_none()
ops.armature.bone_add(name="Lid", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
ops.armature.select_none()


def settle():
    doc.frame_current += 1
    doc.frame_current -= 1


def mainline():
    ops.anim.action_set(name="")
    doc.frame_current = 0


# The knob's sides turn Lid; a fix following the knob alone turns Lid more where the knob ends up and right.
for side in ("Right", "Up"):
    assert ops.anim.action_new(name="Knob " + side) == {'FINISHED'}
    doc.frame_current = 24
    rig().bone_set("Lid", angle=bone("Lid")["setup_angle"] + 0.1)
    doc.frame_current = 25
    mainline()
rig().select_bone("Knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
for side in ("RIGHT", "UP"):
    assert ops.armature.controller_side(side=side, action="Knob " + side.title()) == {'FINISHED'}
rig().select_bone("Knob")
assert ops.armature.bone_fix_new(bones="Knob") == {'FINISHED'}
doc.frame_current = 20
rig().bone_set("Knob", knob=(24.0, 24.0))
rig().bone_set("Lid", angle=bone("Lid")["angle"] + 0.5)
settle()
mainline()
fix = rig().bone_fixes[0]["name"]
# The knob keyed on the mainline: rest on 10, up and right on 30.
doc.frame_current = 10
rig().bone_set("Knob", knob=(0.0, 0.0))
doc.frame_current = 30
rig().bone_set("Knob", knob=(20.0, 12.0))
settle()
doc.auto_key = False

doc.motion_paths = True
doc.path_all = True
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert doc.path_own_motion
rig().select_bone("Knob")
layers.active = rig()
assert ops.anim.motion_path_select(bone="Knob", frame="30", head="1", layer=str(rig_id)) == {'FINISHED'}
assert [p["label"] for p in wm.motion_paths()] == ["Knob head"], [p["label"] for p in wm.motion_paths()]

# --- From its keys: no copy worked out, the same path as working the frames out -------------------------------------
doc.frame_current = 15
copies = worked()
assert copies == 0, (f"the knob's path, its only actions the line of fix {fix!r}, was worked out on {copies} copies of "
                     "the document instead of coming from its keys")
from_keys = grab(False)
wm.motion_path_own_from_keys(False)
frames = grab(False)
wm.motion_path_own_from_keys(True)
assert close(from_keys, frames), ("from the keys", from_keys, "worked out", frames)
p = wm.motion_paths()[0]
assert p["first"] <= 10 and len(p["points"]) > 20, ("the path runs over the keys", p["first"], len(p["points"]))

# --- An edit to its key: still from the keys, still as worked out ---------------------------------------------------
dot = p["points"][30 - p["first"]]
assert ops.anim.motion_path_move(frame="30", layer=str(rig_id), bone="Knob", head="1", x=str(dot[0] + 0.05),
                                 y=str(dot[1])) == {'FINISHED'}
assert worked() == 0, "an edit to the knob's key: from its keys again"
from_keys = grab(False)
wm.motion_path_own_from_keys(False)
frames = grab(False)
wm.motion_path_own_from_keys(True)
assert close(from_keys, frames), ("after an edit, from the keys", from_keys, "worked out", frames)

print("test_motion_path_fix_line: ok")
