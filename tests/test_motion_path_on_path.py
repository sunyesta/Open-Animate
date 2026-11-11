"""On Path: a bone head's path that a knob's action carries, edited as it shows.

The ear has no keys of its own; the knob's action carries it across. Putting its path On Path adds keys where the knob
has them (and the setup frame) and leaves the path as it was. Then a handle shapes the path as it shows (the dots
leave the key the handle's way, not the action's), a dot moved lands where it was put, it saves and opens as it was,
and back to Follow Action it still looks the same. An edit to a path without keys gives it keys (and On Path) first.

Run with:  OpenAnimate --background --python tests/test_motion_path_on_path.py
"""

import math
import pathlib
import tempfile

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def build():
    ops.wm.read_homefile()
    doc.auto_key = True
    ops.layer.new_bone()
    rig_id = layers.active.id
    rig = lambda: next(l for l in layers.all() if l.id == rig_id)
    bone = lambda n: next(b for b in rig().bones if b["name"] == n)
    ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
    ops.armature.select_none()
    ops.armature.bone_add(name="Ear", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
    ops.armature.select_none()
    assert ops.anim.action_new(name="Knob Right") == {'FINISHED'}
    doc.frame_current = 24
    p = bone("Ear")["position"]
    rig().bone_set("Ear", position=(p[0] - 0.6, p[1] - 0.2))
    doc.frame_current = 25
    ops.anim.action_set(name="")
    doc.frame_current = 0
    rig().select_bone("Knob")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action="Knob Right") == {'FINISHED'}
    for f, knob in ((6, (2.0, 0.0)), (30, (24.0, 0.0))):
        doc.frame_current = f
        rig().bone_set("Knob", knob=knob)
        doc.frame_current += 1
        doc.frame_current -= 1
    doc.auto_key = False
    doc.motion_paths = True
    doc.path_all = True
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    layers.active = rig()
    rig().select_bone("Ear")
    doc.frame_current = 18
    return rig_id, rig


def path():
    return next(p for p in wm.motion_paths(kept=False) if p["label"] == "Ear head")


def dots_at():
    p = path()
    return {p["first"] + i: tuple(d) for i, d in enumerate(p["points"])}


def worst(a, b, frames):
    return max(math.dist(a[f], b[f]) for f in frames)


rig_id, rig = build()
args = dict(bone="Ear", head="1", layer=str(rig_id))
assert not rig().keyframes('bones["Ear"].position'), "no keys of its own yet"
assert path()["on_path"] is False, path()["on_path"]
before = dots_at()
frames = range(0, 31)
travel = math.dist(before[6], before[30])
assert travel > 0.3, ("the action carries the ear across", before[6], before[30])

# On Path: keys where the knob has them, the path as it was.
assert ops.anim.motion_path_on_path(on="1", **args) == {'FINISHED'}
keys = rig().keyframes('bones["Ear"].position')
assert [k["frame"] for k in keys] == [0, 6, 30], keys
assert path()["on_path"] is True
on = dots_at()
assert worst(before, on, frames) < 0.01 * travel, ("On Path moved the path", worst(before, on, frames))
# Past the last key the actions still add what they do (only what they added there is left out).
doc.frame_current = 40
past = tuple(next(b for b in rig().bones if b["name"] == "Ear")["position"])
doc.frame_current = 18

# A handle shapes the path as it shows: out of 6 straight up, the dots leave 6 going up (the action goes across).
k6 = on[6]
assert ops.anim.motion_path_handle(frame="6", side="OUT", x=str(k6[0]), y=str(k6[1] + 0.3), **args) == {'FINISHED'}
d = dots_at()
assert math.dist(d[6], k6) < 1e-4 and math.dist(d[30], on[30]) < 1e-4, ("the keys stay", d[6], d[30])
lead = (d[8][0] - d[6][0], d[8][1] - d[6][1])
assert lead[1] > 0.0 and lead[1] > 2.0 * abs(lead[0]), ("the path leaves 6 the handle's way", lead)

# A dot moved lands where it is put, on the path as it shows.
want = (d[18][0] + 0.1, d[18][1] - 0.05)
assert ops.anim.motion_path_move(frame="18", x=str(want[0]), y=str(want[1]), **args) == {'FINISHED'}
d = dots_at()
assert math.dist(d[18], want) < 1e-3, ("the dot went where it was put", d[18], want)
assert math.dist(d[6], k6) < 1e-4 and math.dist(d[30], on[30]) < 1e-4, ("the other keys stay", d[6], d[30])

# Saved and opened, it is as it was.
saved = dots_at()
file = str(pathlib.Path(tempfile.mkdtemp(prefix="oanim_on_path_")) / "on_path.oanim")
assert ops.wm.save_as_mainfile(filepath=file) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=file, confirmed="1") == {'FINISHED'}
rig = lambda: next(l for l in layers.all() if any(b["name"] == "Ear" for b in (l.bones or [])))
layers.active = rig()
rig().select_bone("Ear")
assert ops.wm.tool_motion_path() == {'FINISHED'}
doc.frame_current = 18
args["layer"] = str(rig().id)
assert path()["on_path"] is True
assert worst(saved, dots_at(), frames) < 1e-4, "opened, the path moved"

# Back to Follow Action: the same path, the keys what is added to the action's moves.
assert ops.anim.motion_path_on_path(on="0", **args) == {'FINISHED'}
assert path()["on_path"] is False
assert all(k["path_offset"] == (0.0, 0.0) for k in rig().keyframes('bones["Ear"].position'))
assert worst(saved, dots_at(), frames) < 0.01 * travel, ("Follow Action moved the path", worst(saved, dots_at(), frames))
# Off stays off: an edit to the path keeps it on Follow Action.
d = dots_at()
assert ops.anim.motion_path_move(frame="18", x=str(d[18][0]), y=str(d[18][1] + 0.05), **args) == {'FINISHED'}
assert path()["on_path"] is False, "an edit put it back On Path"

# An edit to a path without keys adds them first, On Path.
rig_id, rig = build()
args = dict(bone="Ear", head="1", layer=str(rig_id))
d = dots_at()
want = (d[18][0], d[18][1] + 0.1)
assert ops.anim.motion_path_move(frame="18", x=str(want[0]), y=str(want[1]), **args) == {'FINISHED'}
keys = rig().keyframes('bones["Ear"].position')
assert [k["frame"] for k in keys] == [0, 6, 18, 30], keys
assert path()["on_path"] is True
d2 = dots_at()
assert math.dist(d2[18], want) < 1e-3, ("the dot went where it was put", d2[18], want)
assert math.dist(d2[6], d[6]) < 1e-3 and math.dist(d2[30], d[30]) < 1e-3, ("the knob's keys' dots stay", d2[6], d[6])
doc.frame_current = 40
assert math.dist(tuple(next(b for b in rig().bones if b["name"] == "Ear")["position"]), past) < 1e-3, "past the keys"

print("test_motion_path_on_path: ok")
