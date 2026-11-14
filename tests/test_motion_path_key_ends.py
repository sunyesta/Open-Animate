"""Deleting keys lets go of the path handles left facing nothing.

A bone moves through keys on 0, 10 and 20; frame 0's and 10's handles are dragged. Deleting 20 leaves 10 last: its out
handle, which shapes nothing now, goes back in line with its in one (the path into 10 as it was). Deleting 10 leaves
frame 0's key alone: its handles go back to Auto, so a key made later leaves 0 as a fresh one would, not along the old
handle. The timeline's Delete Keys does the same.

Run with:  OpenAnimate --background --python tests/test_motion_path_key_ends.py
"""

import math

import oanim
oanim.data.document.path_show_all = True  # these tests look at several paths at once

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def build():
    ops.wm.read_homefile()
    oanim.data.document.path_show_all = True
    doc.auto_key = True
    ops.layer.new_bone()
    rig_id = layers.active.id
    ops.armature.bone_add(name="Arm", head_x="0.0", head_y="0.0", tail_x="1.0", tail_y="0.0")
    rig = lambda: next(l for l in layers.all() if l.id == rig_id)
    for f, at in ((10, (2.0, 1.0)), (20, (4.0, 0.0))):
        doc.frame_current = f
        rig().bone_set("Arm", position=at)
        doc.frame_current += 1
        doc.frame_current -= 1
    doc.auto_key = False
    doc.motion_paths = True
    doc.path_all = True
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    layers.active = rig()
    rig().select_bone("Arm")
    doc.frame_current = 5
    return rig_id, rig


def keys(rig):
    return {k["frame"]: k for k in rig().keyframes('bones["Arm"].position')}


def path():
    return next(p for p in wm.motion_paths(kept=False) if p["label"] == "Arm head")


def dots_at():
    p = path()
    return {p["first"] + i: tuple(d) for i, d in enumerate(p["points"])}


rig_id, rig = build()
args = dict(bone="Arm", head="1", layer=str(rig_id))
assert sorted(keys(rig)) == [0, 10, 20], keys(rig)
fresh = dots_at()

# Frame 0's out handle and 10's handles dragged.
k0, k10 = fresh[0], fresh[10]
assert ops.anim.motion_path_handle(frame="0", side="OUT", x=str(k0[0]), y=str(k0[1] - 1.0), **args) == {'FINISHED'}
assert ops.anim.motion_path_handle(frame="10", side="IN", x=str(k10[0] - 0.4), y=str(k10[1] + 0.5), broken="1",
                                   **args) == {'FINISHED'}
assert ops.anim.motion_path_handle(frame="10", side="OUT", x=str(k10[0] + 0.1), y=str(k10[1] + 0.8), broken="1",
                                   **args) == {'FINISHED'}
assert keys(rig)[10]["path_handles"] == "BROKEN", keys(rig)[10]["path_handles"]
shaped = dots_at()

# 20 deleted: 10 is last, its out handle back in line with its in one; the path into 10 as it was.
assert ops.anim.motion_path_key_delete(frame="20", **args) == {'FINISHED'}
k = keys(rig)[10]
assert k["path_handles"] == "ALIGNED", k["path_handles"]
assert math.dist(k["path_out"], (-k["path_in"][0], -k["path_in"][1])) < 1e-5, ("in line", k["path_in"], k["path_out"])
d = dots_at()
assert max(math.dist(d[f], shaped[f]) for f in range(0, 11)) < 1e-4, "the path into 10 moved"

# 10 deleted: frame 0's key alone, its handles back to Auto.
assert ops.anim.motion_path_key_delete(frame="10", **args) == {'FINISHED'}
k = keys(rig)
assert sorted(k) == [0], k
assert k[0]["path_handles"] == "AUTO" and k[0]["path_out"] == (0.0, 0.0), k[0]

# Keyed again on 20: it leaves 0 as a fresh key would, not down along the old handle.
doc.auto_key = True
doc.frame_current = 20
rig().bone_set("Arm", position=(4.0, 0.0))
doc.frame_current = 19
doc.frame_current = 20
doc.auto_key = False
assert sorted(keys(rig)) == [0, 20], keys(rig)
d = dots_at()
assert all(d[f][1] > -1e-4 for f in range(0, 21)), ("the old handle still bends it down", [d[f] for f in range(0, 6)])

# The timeline's Delete Keys: 20 selected and deleted leaves 10 last, its out handle in line again.
rig_id, rig = build()
args = dict(bone="Arm", head="1", layer=str(rig_id))
k10 = dots_at()[10]
assert ops.anim.motion_path_handle(frame="10", side="OUT", x=str(k10[0] + 0.1), y=str(k10[1] + 0.8), broken="1",
                                   **args) == {'FINISHED'}
assert ops.anim.motion_path_handle(frame="10", side="IN", x=str(k10[0] - 0.4), y=str(k10[1] + 0.5), broken="1",
                                   **args) == {'FINISHED'}
assert ops.anim.keys_select(deselect="0", extend="0", frame_start="20", frame_end="20", kinds="304", layers=str(rig_id),
                            path='bones["Arm"].position', pinned="0", selected_only="0") == {'FINISHED'}
assert ops.anim.keys_delete() == {'FINISHED'}
k = keys(rig)
assert sorted(k) == [0, 10], k
assert k[10]["path_handles"] == "ALIGNED", k[10]["path_handles"]
assert math.dist(k[10]["path_out"], (-k[10]["path_in"][0], -k[10]["path_in"][1])) < 1e-5, k[10]

print("test_motion_path_key_ends: ok")
