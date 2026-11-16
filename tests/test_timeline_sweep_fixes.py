"""Bugs a sweep of the timeline, layers and undo found, each section its own scene: Paste Keys on the setup frame
twice, Select All Keys with the timeline's filters on, edits a reference refuses, and Paste Pose as Same Place on the
frame it was copied on.

Run with:  OpenAnimate --background --python tests/test_timeline_sweep_fixes.py
"""

import json
import os
import tempfile
import zipfile

import oanim

ops, wm, L = oanim.ops, oanim.wm, oanim.data.layers


def close(a, b, eps=1e-5):
    if isinstance(a, (int, float)):
        return abs(a - b) < eps
    return all(close(x, y, eps) for x, y in zip(a, b))


def saved_layers():
    path = os.path.join(tempfile.mkdtemp(prefix="oanim_timeline_sweep_"), "snap.oanim")
    ops.wm.save_copy(filepath=path)
    with zipfile.ZipFile(path) as z:
        return json.dumps(json.loads(z.read("document.json"))["document"]["layers"], sort_keys=True)


def step():
    return wm.undo_history()[1]


# --- Paste Keys on the setup frame makes the copied pose the setup: a second paste there changes nothing ----------------
ops.wm.read_homefile(confirmed="1")
doc = oanim.data.document
doc.auto_key = True
doc.frame_current = 0
ops.layer.new()
lay = L.active
lay.key_together = False
lay.add_curve([(0.0, 0.0), (0.4, 0.3), (0.8, 0.0)])
h0 = lay.curve_handles(0)[1]
ops.layer.new_bone()
rig = L.active
ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0")
doc.frame_current = 6
lay.set_point(1, (0.5, 0.5))
lay.move_handle(0, 1, "OUT", (h0[2][0], h0[2][1] + 0.15))
rig.bone_set("arm", angle=0.5, position=(0.2, 0.1))
doc.frame_current = 7
doc.frame_current = 6
shown6 = (lay.points[1][:2], lay.curve_handles(0)[1], rig.bones[0]["angle"], rig.bones[0]["position"])
for l in L.all():
    l.selected = True
ops.anim.keys_deselect_all()
assert ops.anim.keys_select(frame_start="6", frame_end="6") == {"FINISHED"}
assert ops.anim.keys_copy() == {"FINISHED"}
doc.frame_current = 0
seen = []
for i in range(2):
    assert ops.anim.keys_paste() == {"FINISHED"}
    seen.append((lay.points[1][:2], lay.curve_handles(0)[1], rig.bones[0]["angle"], rig.bones[0]["position"]))
assert close(seen[0][0], (0.5, 0.5)) and close(seen[0][2], 0.5), ("the copied pose is the setup", seen[0])
assert close(seen[1][0], seen[0][0]), ("the point again", seen)
assert close(seen[1][1][1:], seen[0][1][1:]), ("the handles again", seen)
assert close(seen[1][2], seen[0][2]) and close(seen[1][3], seen[0][3]), ("the bone again", seen)
assert close(seen[0][1][1:], shown6[1][1:], 1e-4) and close(seen[0][3], shown6[3], 1e-4), (seen[0], shown6)
# Frame 6 still shows its pose.
doc.frame_current = 6
assert close(lay.points[1][:2], shown6[0]) and close(rig.bones[0]["angle"], shown6[2]), "the other frames keep theirs"

# --- Select All Keys picks only the keys of rows shown: the filters' hidden rows' keys stay unpicked, and X keeps them --
ops.wm.read_homefile(confirmed="1")
doc = oanim.data.document
doc.frame_current = 0
doc.auto_key = False
ops.layer.new_bone()
rig = L.active
ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0")
for frame in (10, 20):
    doc.frame_current = frame
    rig.location_x = frame / 100.0
    rig.keyframe_insert("position")
    rig.bone_set("arm", angle=frame / 100.0)
    rig.keyframe_insert('bones["arm"].angle')
doc.frame_current = 0
ops.armature.select_none()
doc.timeline_only_selected = False
assert ops.anim.timeline_filter(kinds="BONES") == {"FINISHED"}
assert "Position" not in [r["label"] for r in wm.timeline_row_details()]
ops.anim.keys_select_all()
assert not [k["frame"] for k in rig.keyframes("position") if k["selected"] and k["frame"]], "hidden keys picked"
assert all(k["selected"] for k in rig.keyframes('bones["arm"].angle') if k["frame"]), "the shown ones are"
ops.anim.keys_delete()
assert sorted(k["frame"] for k in rig.keyframes("position")) == [0, 10, 20]
assert not [k for k in rig.keyframes('bones["arm"].angle') if k["frame"]], "the shown ones went"
# With the filters off, every row again.
assert ops.anim.timeline_filter(kinds="ALL") == {"FINISHED"}
ops.anim.keys_select_all()
assert all(k["selected"] for k in rig.keyframes("position") if k["frame"])

# --- A reference refuses edits to its points: CANCELLED and no undo step -----------------------------------------------
bad = []
for name in ("duplicate_move", "delete_edges", "peak", "delete_points", "dissolve_points"):
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.frame_current = 0
    ops.layer.new()
    src = L.active
    src.add_curve([(0.0, 0.0), (0.3, 0.1), (0.6, 0.0), (0.9, 0.2)])
    ops.layer.make_reference()
    ref = L.active
    assert ref.id != src.id and ref.reference_source is not None
    ops.mesh.select_none()
    ref.select_points([0, 1, 2])
    n, was = ref.point_count, step()
    r = getattr(ops.mesh, name)()
    if ref.point_count != n or r != {"CANCELLED"} or step() != was:
        bad.append((name, r, step() != was, ref.point_count))
assert not bad, bad
# Their own drawing's as before.
ops.wm.read_homefile(confirmed="1")
ops.layer.new()
own = L.active
own.add_curve([(0.0, 0.0), (0.3, 0.1), (0.6, 0.0), (0.9, 0.2)])
own.select_points([1])
assert ops.mesh.dissolve_points() == {"FINISHED"} and own.point_count == 3
own.select_points([1])
assert ops.mesh.peak() == {"FINISHED"}
assert ops.mesh.delete_points() == {"FINISHED"} and own.point_count == 2

# --- Paste Pose as Same Place on the frame it was copied on changes nothing -----------------------------------------------
ops.wm.read_homefile(confirmed="1")
doc = oanim.data.document
doc.auto_key = True
doc.auto_freeze_keys = False
doc.frame_current = 0
ops.layer.new_bone()
rig = L.active
ops.armature.bone_add(name="arm", head_x="0.13", head_y="-0.07", tail_x="1.1", tail_y="0.31")
ops.layer.new()
art = L.active
ops.layer.move_to_group(group=str(rig.id))
art.add_curve([(0.21, 0.13), (0.47, 0.33), (0.71, 0.11), (0.93, 0.57)])
assert ops.layer.parent_bone_set(bone="arm", deform="POINTS") == {"FINISHED"}
doc.frame_current = 6
rig.bone_set("arm", angle=rig.bones[0]["angle"] + 0.731, position=(0.37, 0.19))
doc.frame_current = 7
doc.frame_current = 6
L.active = rig
ops.armature.select_all()
art.selected = True
ops.mesh.select_all()
assert ops.pose.copy() == {"FINISHED"}
for mode in ("KEYS", "LOOK", "PLACE"):
    before, was = saved_layers(), step()
    assert ops.pose.paste(paste_as=mode) == {"FINISHED"}
    assert saved_layers() == before and step() == was, (mode, "changed what it pasted onto", step() != was)

print("timeline sweep fixes: ok")
