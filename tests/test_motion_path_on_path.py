"""On Path: a bone head's path that a knob's action carries, edited as it shows.

The ear has no keys of its own; the knob's action carries it across. Putting its path On Path adds keys where the knob
has them (and the setup frame) and leaves the path as it was. Then a handle shapes the path as it shows (the dots
leave the key the handle's way, not the action's), a dot moved lands where it was put, it saves and opens as it was,
and back to Follow Action it still looks the same. An edit to a path without keys gives it keys (and On Path) first.

Run with:  OpenAnimate --background --python tests/test_motion_path_on_path.py
"""

import json
import math
import os
import shutil
import zipfile
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

doc.frame_current = 40
past_before = tuple(next(b for b in rig().bones if b["name"] == "Ear")["position"])
doc.frame_current = 18

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
assert math.dist(past, past_before) < 1e-4, ("past the last key the actions add again, as before", past, past_before)
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

# Its keys all deleted, then the ear moved with Auto Keying: keyed as any bone is, onto the action, which still carries it
# (On Path was left on with no keys, and the next keys made the action's moves left out with nothing holding them).
keys = rig().keyframes('bones["Ear"].position')
for k in keys[1:]:
    assert ops.anim.motion_path_key_delete(frame=str(k["frame"]), **args) == {'FINISHED'}
# (Frame 0's key, the setup, stays: a path can't delete it.)
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0]
assert path()["on_path"] is False, "one key holds no path: not On Path"
# A file with On Path left on over one key (saved before a delete let go of it): opened, still not On Path.
folder = tempfile.mkdtemp(prefix="oanim_onpath_")
saved = os.path.join(folder, "one_key.oanim")
assert ops.wm.save_as_mainfile(filepath=saved) == {'FINISHED'}
with zipfile.ZipFile(saved) as z:
    data = json.loads(z.read("document.json"))
ears = []


def find_ear(node):
    if isinstance(node, dict):
        if node.get("name") == "Ear" and "position_keys" in node:
            ears.append(node)
        for v in node.values():
            find_ear(v)
    elif isinstance(node, list):
        for v in node:
            find_ear(v)


find_ear(data)
assert len(ears) == 1, len(ears)
ears[0]["position_keys_on_path"] = True
old = os.path.join(folder, "old.oanim")
with zipfile.ZipFile(old, "w") as z:
    z.writestr("document.json", json.dumps(data))
assert ops.wm.open_mainfile(filepath=old, confirmed="1") == {'FINISHED'}
doc, layers = oanim.data.document, oanim.data.layers
layers.active = rig()
rig().select_bone("Ear")
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert path()["on_path"] is False, "On Path over one key left on in a file: not On Path"
shutil.rmtree(folder, ignore_errors=True)
doc.auto_key = True
doc.frame_current = 18
e = next(b for b in rig().bones if b["name"] == "Ear")["position"]
rig().bone_set("Ear", position=(e[0] + 0.004, e[1]))
doc.frame_current = 17
doc.frame_current = 18
doc.auto_key = False
assert rig().keyframes('bones["Ear"].position'), "keyed"
assert path()["on_path"] is False, "keyed again, not On Path"
d = dots_at()
assert math.dist(d[24], before[24]) < 0.05 * travel, ("the action still carries it", d[24], before[24])

# No keys of its own: the knob's diamonds on its path show the handles the ear's keys will have, adding nothing until one
# is dragged; dragged, the ear is keyed where the knob is (On Path) and the handle goes where it is put.
rig_id, rig = build()
args = dict(bone="Ear", head="1", layer=str(rig_id))
assert ops.anim.motion_path_select(frame="30", **args) == {'FINISHED'}
p = path()
assert 30 in p["keys"], p["keys"]
shown = {h["frame"]: h for h in p["handles"]}
assert 30 in shown and shown[30]["in"] is not None, ("the knob's key shows the ear's handles", p["handles"])
# Picked, so the viewport shows its handles (no key of the ear's to select there).
assert 30 in p["keys_picked"], p["keys_picked"]
assert not rig().keyframes('bones["Ear"].position'), "showing them keys nothing"
k30 = dots_at()[30]
want_in = (k30[0] + 0.05, k30[1] - 0.2)
# Its tip's path too, which its position keys move as they do its head (the ear doesn't turn).
tip = dict(args, head="0")
assert ops.anim.motion_path_select(frame="30", **tip) == {'FINISHED'}
t = next(p for p in wm.motion_paths(kept=False) if p["label"] == "Ear tip")
assert 30 in t["keys_picked"], t["keys_picked"]
assert {h["frame"]: h for h in t["handles"]}.get(30, {}).get("in") is not None, ("the tip's diamond shows its handles", t["handles"])
assert not rig().keyframes('bones["Ear"].position'), "showing them keys nothing"
assert ops.anim.motion_path_select(frame="30", **args) == {'FINISHED'}
assert ops.anim.motion_path_handle(frame="30", side="IN", x=str(want_in[0]), y=str(want_in[1]), **args) == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 6, 30]
assert path()["on_path"] is True
got = {h["frame"]: h for h in path()["handles"]}[30]["in"]
assert math.dist(got, want_in) < 1e-3, ("the handle went where it was put", got, want_in)
assert math.dist(dots_at()[30], k30) < 1e-4, "the key stays"

# The tip's handle dragged: keyed (On Path) as the head's is, the handle where it is put.
rig_id, rig = build()
tip = dict(bone="Ear", head="0", layer=str(rig_id))
tip_path = lambda: next(p for p in wm.motion_paths(kept=False) if p["label"] == "Ear tip")
t30 = tip_path()["points"][30 - tip_path()["first"]]
want_in = (t30[0] + 0.05, t30[1] - 0.2)
assert ops.anim.motion_path_handle(frame="30", side="IN", x=str(want_in[0]), y=str(want_in[1]), **tip) == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 6, 30]
got = {h["frame"]: h for h in tip_path()["handles"]}[30]["in"]
assert math.dist(got, want_in) < 1e-3, ("the tip's handle went where it was put", got, want_in)

# The path's start too: frame 0, the setup, shows a diamond (its out handle) with no key of the ear's there.
rig_id, rig = build()
args = dict(bone="Ear", head="1", layer=str(rig_id))
assert ops.anim.motion_path_select(frame="0", **args) == {'FINISHED'}
assert 0 in path()["keys_picked"], ("the setup's diamond picked", path()["keys_picked"])
assert not rig().keyframes('bones["Ear"].position'), "picking it keys nothing"
k0 = dots_at()[0]
assert ops.anim.motion_path_handle(frame="0", side="OUT", x=str(k0[0]), y=str(k0[1] + 0.3), **args) == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 6, 30]
assert path()["on_path"] is True
d = dots_at()
assert math.dist(d[0], k0) < 1e-4, ("the setup stays", d[0], k0)
lead = (d[2][0] - d[0][0], d[2][1] - d[0][1])
assert lead[1] > 0.0 and lead[1] > 2.0 * abs(lead[0]), ("the path leaves 0 the handle's way", lead)

# A lone key (the setup's, as left when the rest are deleted) holds no path: picked, it shows the handles it will have
# all the same.
rig_id, rig = build()
args = dict(bone="Ear", head="1", layer=str(rig_id))
doc.frame_current = 0
assert ops.anim.keyframe_insert() == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0]
doc.frame_current = 18
assert ops.anim.motion_path_select(frame="0", **args) == {'FINISHED'}
p = path()
assert 0 in p["keys_picked"], p["keys_picked"]
shown = {h["frame"]: h for h in p["handles"]}
assert 0 in shown and shown[0]["out"] is not None, ("the lone key shows its handle", p["handles"])
k0 = dots_at()[0]
assert ops.anim.motion_path_handle(frame="0", side="OUT", x=str(k0[0]), y=str(k0[1] + 0.3), **args) == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 6, 30]
d = dots_at()
lead = (d[2][0] - d[0][0], d[2][1] - d[0][1])
assert lead[1] > 0.0 and lead[1] > 2.0 * abs(lead[0]), ("the path leaves 0 the handle's way", lead)

# Keys of its own either side of a knob's key (the ear keyed on 0 and 30, the knob on 6): the knob's diamond between, with
# no key of the ear's there, shows the handles the ear's key will have; dragged, the ear is keyed there in place (the path
# as it was) and the handle goes where it is put.
rig_id, rig = build()
args = dict(bone="Ear", head="1", layer=str(rig_id))
for f in (0, 30):
    doc.frame_current = f
    assert ops.anim.keyframe_insert() == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 30]
doc.frame_current = 18
assert ops.anim.motion_path_select(frame="6", **args) == {'FINISHED'}
p = path()
assert 6 in p["keys_picked"], p["keys_picked"]
shown = {h["frame"]: h for h in p["handles"]}
assert 6 in shown and shown[6]["in"] is not None, ("the knob's key between the ear's shows its handles", p["handles"])
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 30], "showing them keys nothing"
before = dots_at()
h6 = shown[6]["in"]
assert ops.anim.motion_path_handle(frame="6", side="IN", x=str(h6[0]), y=str(h6[1]), **args) == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 6, 30]
assert path()["on_path"] is True
travel = max(math.dist(before[0], before[f]) for f in frames)
assert worst(before, dots_at(), frames) < 0.01 * travel, ("keyed in place, the path as it was", worst(before, dots_at(), frames))
k6 = dots_at()[6]
want_in = (k6[0] + 0.05, k6[1] - 0.2)
assert ops.anim.motion_path_handle(frame="6", side="IN", x=str(want_in[0]), y=str(want_in[1]), **args) == {'FINISHED'}
got = {h["frame"]: h for h in path()["handles"]}[6]["in"]
assert math.dist(got, want_in) < 1e-3, ("the handle went where it was put", got, want_in)

# What the actions add past the last key, kept from a path drawn then, isn't added once a key past it puts those frames
# between keys: from its keys (and the kept frames) the path is as working every frame out has it.
rig_id, rig = build()
args = dict(bone="Ear", head="1", layer=str(rig_id))
assert ops.anim.motion_path_on_path(on="1", **args) == {'FINISHED'}
whole = range(0, 45)
kept = lambda: next(p for p in wm.motion_paths(kept=True) if p["label"] == "Ear head")
kept()
d = dots_at()
assert ops.anim.motion_path_move(frame="40", x=str(d[40][0]), y=str(d[40][1] + 0.2), **args) == {'FINISHED'}
assert [k["frame"] for k in rig().keyframes('bones["Ear"].position')] == [0, 6, 30, 40]
wm.motion_path_places_clear()
p = kept()
fast = {p["first"] + i: tuple(q) for i, q in enumerate(p["points"])}
assert wm.motion_path_places()["offsets"] > 0, ("the kept frames used", wm.motion_path_places())
wm.motion_path_own_from_keys(False)
full = dots_at()
wm.motion_path_own_from_keys(True)
assert worst(fast, full, whole) < 1e-4, ("between the keys now, nothing kept added", worst(fast, full, whole))

print("test_motion_path_on_path: ok")
