"""The pose library (the Asset Shelf's Poses): Save Pose keeps the selected bones' and points' pose on this frame in the
file under a name and a collection (a new collection is made from the selection); the shelf shows a collection's row
while anything in it is selected, every collection with poses while nothing is; a click applies the pose on the frame
shown, onto the bones and points it was saved from whatever is active (Auto Keying keys it); Apply Flipped, Apply to
Selected Only, Replace, Rename, Move, Duplicate, Save Flipped Copy and Delete are undo steps; the poses are saved in the
file.

Run with:  OpenAnimate --background --python tests/test_pose_library.py
"""

import os
import tempfile

import _oanim
import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    if isinstance(a, (int, float)):
        return abs(a - b) < eps
    return all(abs(x - y) < eps for x, y in zip(a, b))


def scene():
    """A bone layer with Arm_L, Arm_R and Leg, a drawing whose points Arm_L moves. Frame 10: the arm raised, a point
    pulled out; frame 20: the arm lowered. Auto Keying on."""
    global doc, layers, rig_id, art_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id
    assert ops.armature.bone_add(name="Arm_L", head_x="0.5", head_y="0", tail_x="1.5", tail_y="0", parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="Arm_R", head_x="-0.5", head_y="0", tail_x="-1.5", tail_y="0",
                                 parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="Leg", head_x="0", head_y="-1", tail_x="0", tail_y="-2", parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.layer.new() == {'FINISHED'}
    art_id = layers.active.id
    art().name = "hand"
    assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
    art().add_curve([(1.2, 0.1), (1.4, 0.3), (1.1, 0.5)])
    assert ops.layer.parent_bone_set(bone="Arm_L", deform="POINTS") == {'FINISHED'}
    art().edit_with_bones = True
    doc.auto_key = True
    doc.frame_current = 10
    rig().bone_set("Arm_L", angle=0.7)
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] + 0.3)
    art().set_point(0, (1.3, 0.0))
    doc.frame_current = 20
    rig().bone_set("Arm_L", angle=-0.4)
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] - 0.5)
    art().set_point(0, (1.6, 0.4))
    at(10)
    # (An undo step of its own, so undoing an operator leaves the scene's Python edits in.)
    layers.active = art()
    assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
    assert ops.object.modifier_remove(index="0") == {'FINISHED'}


def rig():
    return next(l for l in layers.all() if l.id == rig_id)


def art():
    return next(l for l in layers.all() if l.id == art_id)


def bone(name):
    return next(b for b in rig().bones if b["name"] == name)


def stored():
    return [tuple(p[:2]) for p in art().points]


def at(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def select_bones(*names):
    layers.active = rig()
    ops.armature.select_none()
    for i, n in enumerate(names):
        rig().select_bone(n, extend=i > 0)


def select_points(picked):
    layers.active = art()
    ops.mesh.select_none()
    art().select_points(picked)


def select_nothing():
    layers.active = rig()
    ops.armature.select_none()
    layers.active = art()
    ops.mesh.select_none()


def poses():
    return _oanim.poses()


def pose(name):
    return next(p for p in poses() if p["name"] == name)


def rows(search=""):
    return [(name, [next(p["name"] for p in poses() if p["id"] == i) for i in ids])
            for name, ids in _oanim.pose_shelf_rows(search)]


def said():
    r = wm.banner_report()
    return r[2] + " " + r[3]


def last_step():
    names, index = wm.undo_history()
    return names[index]


def undo_op(name):
    """Undoes back past the last step named `name` (selecting is a step of its own)."""
    for _ in range(10):
        step = last_step()
        ops.ed.undo()
        if step.startswith(name):
            return
    raise AssertionError("no step " + name)


# --- Save Pose: a name, a collection; a new collection is made from the selection ---------------------------------------
scene()
select_nothing()
assert ops.poselib.pose_new(name="Wave", new_collection="Arms") == {'CANCELLED'}, "nothing selected"
select_bones("Arm_L")
assert ops.poselib.pose_new(name="  ", new_collection="Arms") == {'CANCELLED'} and "Enter a name" in said(), said()
assert ops.poselib.pose_new(name="Wave", new_collection=" ") == {'CANCELLED'} and "Name the new collection" in said()
assert ops.poselib.pose_new(name="Wave", collection="Nowhere") == {'CANCELLED'}, "no such collection"
assert poses() == []
arm10 = bone("Arm_L")["angle"]
assert ops.poselib.pose_new(name="Wave_L", new_collection="Arms") == {'FINISHED'}
assert last_step() == "Save Pose", last_step()
p = pose("Wave_L")
assert p["collection"] == "Arms" and p["bones"] == ["Arm_L"] and p["points"] == 0, p
assert bone("Arm_L")["collections"] == ["Arms"], "the selection is put in the new collection"
assert "Arms" in [c["name"] for c in rig().bone_collections], "on the bone layer's panel"
assert bone("Leg")["collections"] == []
# Into an existing collection: the selection isn't put in it.
select_bones("Leg")
assert ops.poselib.pose_new(name="Kick", collection="Arms") == {'FINISHED'}
assert pose("Kick")["collection"] == "Arms" and bone("Leg")["collections"] == []
# The same name in the same collection gets a number.
select_bones("Arm_L")
assert ops.poselib.pose_new(name="Wave_L", collection="Arms") == {'FINISHED'}
assert [p["name"] for p in poses()] == ["Wave_L", "Kick", "Wave_L.001"]
undo_op("Save Pose")
undo_op("Save Pose")
assert [p["name"] for p in poses()] == ["Wave_L"]
undo_op("Save Pose")
assert poses() == [] and bone("Arm_L")["collections"] == [], "undone, the collection's assignment too"
ops.ed.redo()
assert [p["name"] for p in poses()] == ["Wave_L"] and bone("Arm_L")["collections"] == ["Arms"]

# --- The shelf's rows: the selection's collections, or every collection with poses -------------------------------------
select_nothing()
assert rows() == [("Arms", ["Wave_L"])], rows()
select_bones("Leg")
assert rows() == [], "Leg is in no collection"
assert ops.armature.collection_add(name="Legs") == {'FINISHED'}
assert ops.armature.collection_assign(collection="Legs") == {'FINISHED'}
assert rows() == [("Legs", [])], "the selection's collection shows with nothing in it yet, to save into"
select_bones("Arm_L", "Leg")
assert rows() == [("Arms", ["Wave_L"]), ("Legs", [])], rows()
select_nothing()
assert rows() == [("Arms", ["Wave_L"])], "with nothing selected only collections with poses"
assert rows("WAV") == [("Arms", ["Wave_L"])] and rows("zzz") == [], "search, any case"
# A drawing's points select its collections too.
select_points([0])
assert ops.poselib.pose_new(name="Fist", new_collection="Hands") == {'FINISHED'}
assert art().collections == ["Hands"] and pose("Fist")["points"] == 1 and pose("Fist")["layers"] == ["hand"]
select_points([1])
assert rows() == [("Hands", ["Fist"])], rows()

# --- Apply: back on the bones and points it was saved from, whatever is active; keyed -----------------------------------
at(20)
select_nothing()
layers.active = art()
assert not close(bone("Arm_L")["angle"], arm10)
assert ops.poselib.apply(pose=str(pose("Wave_L")["id"])) == {'FINISHED'}
assert last_step() == "Apply Pose Wave_L", last_step()
assert close(bone("Arm_L")["angle"], arm10), (bone("Arm_L")["angle"], arm10)
at(20)
assert close(bone("Arm_L")["angle"], arm10), "Auto Keying keyed it"
ops.ed.undo()
at(20)
assert close(bone("Arm_L")["angle"], -0.4), "undone"
was = stored()
assert ops.poselib.apply(pose=str(pose("Fist")["id"])) == {'FINISHED'}
assert close(stored()[0], (1.3, 0.0)) and close(stored()[1], was[1]), (stored(), was)
ops.ed.undo()
at(0)
assert ops.poselib.apply(pose=str(pose("Wave_L")["id"])) == {'CANCELLED'}, "not on the setup frame"
assert "setup frame" in said(), said()
assert ops.poselib.apply(pose="12345") == {'CANCELLED'}

# --- Apply Flipped: as Paste Pose Flipped puts it ----------------------------------------------------------------------
at(10)
select_bones("Arm_L")
assert ops.pose.copy() == {'FINISHED'}
at(20)
assert ops.pose.paste_flipped() == {'FINISHED'}
flipped_r, flipped_l = bone("Arm_R")["angle"], bone("Arm_L")["angle"]
ops.ed.undo()
at(20)
select_nothing()
assert ops.poselib.apply(pose=str(pose("Wave_L")["id"]), flipped="1") == {'FINISHED'}
assert close(bone("Arm_R")["angle"], flipped_r) and close(bone("Arm_L")["angle"], flipped_l), \
    (bone("Arm_R")["angle"], flipped_r)
assert not close(flipped_r, bone("Arm_R")["setup_angle"])
ops.ed.undo()

# --- Apply to Selected Only ----------------------------------------------------------------------------------------------
at(10)
leg10 = bone("Leg")["angle"]
select_bones("Arm_L", "Leg")
assert ops.poselib.pose_new(name="Both", collection="Arms") == {'FINISHED'}
at(20)
leg20 = bone("Leg")["angle"]
select_bones("Leg")
assert ops.poselib.apply(pose=str(pose("Both")["id"]), selected_only="1") == {'FINISHED'}
assert close(bone("Leg")["angle"], leg10) and close(bone("Arm_L")["angle"], -0.4), "only Leg"
ops.ed.undo()
at(20)
select_nothing()
assert ops.poselib.apply(pose=str(pose("Both")["id"]), selected_only="1") == {'FINISHED'}, "none selected: all"
assert close(bone("Leg")["angle"], leg10) and close(bone("Arm_L")["angle"], arm10)
ops.ed.undo()

# --- Replace, Rename, Move, Duplicate, Save Flipped Copy, Delete ----------------------------------------------------------
at(20)
both = str(pose("Both")["id"])
select_bones("Leg")
assert ops.poselib.replace(pose=both) == {'FINISHED'}
assert pose("Both")["bones"] == ["Leg"] and pose("Both")["collection"] == "Arms"
ops.ed.undo()
assert pose("Both")["bones"] == ["Arm_L", "Leg"]
assert ops.poselib.rename(pose=both, name=" ") == {'CANCELLED'}
assert ops.poselib.rename(pose=both, name="Wave_L") == {'FINISHED'} and pose("Wave_L.001")["id"] == int(both), \
    "a name taken in its collection gets a number"
assert ops.poselib.rename(pose=both, name="Both") == {'FINISHED'}
assert ops.poselib.move(pose=both, collection="Legs") == {'FINISHED'} and pose("Both")["collection"] == "Legs"
assert ops.poselib.move(pose=both, collection="Legs") == {'CANCELLED'}, "already there"
assert ops.poselib.move(pose=both, collection="") == {'FINISHED'} and pose("Both")["collection"] == ""
select_nothing()
assert ("Unsorted", ["Both"]) in rows(), rows()
assert ops.poselib.move(pose=both, collection="Arms") == {'FINISHED'}
assert ops.poselib.duplicate(pose=both) == {'FINISHED'}
names = [p["name"] for p in poses()]
assert names[names.index("Both") + 1] == "Both.001", names
assert ops.poselib.delete(pose=str(pose("Both.001")["id"])) == {'FINISHED'} and "Both.001" not in [p["name"] for p in poses()]
ops.ed.undo()
assert "Both.001" in [p["name"] for p in poses()], "undone"
wave = str(pose("Wave_L")["id"])
assert ops.poselib.flip_copy(pose=wave) == {'FINISHED'}
r = pose("Wave_R")
assert r["bones"] == ["Arm_R"] and r["collection"] == "Arms", r
assert bone("Arm_R")["collections"] == ["Arms"], "its bones put in its collection, so it shows while they're selected"
select_bones("Arm_R")
assert [name for name, _ in rows()] == ["Arms"] and "Wave_R" in dict(rows())["Arms"], rows()
at(20)
assert ops.poselib.apply(pose=str(r["id"])) == {'FINISHED'}
assert close(bone("Arm_R")["angle"], flipped_r), (bone("Arm_R")["angle"], flipped_r)
assert close(bone("Arm_L")["angle"], -0.4), "the flipped copy holds Arm_R alone"
ops.ed.undo()
assert ops.poselib.flip_copy(pose=both) == {'FINISHED'}
assert pose("Both Flipped")["bones"] == ["Arm_R", "Leg"], "no other side in its name: Flipped after it"

# --- Saved in the file --------------------------------------------------------------------------------------------------
kept = poses()
path = os.path.join(tempfile.mkdtemp(prefix="oanim_poselib_"), "poses.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
doc, layers = oanim.data.document, oanim.data.layers
assert poses() == kept, (poses(), kept)
at(20)
select_nothing()
assert ops.poselib.apply(pose=str(pose("Wave_L")["id"])) == {'FINISHED'}
assert close(bone("Arm_L")["angle"], arm10)
# A new pose after opening gets an id of its own.
select_bones("Leg")
assert ops.poselib.pose_new(name="Late", collection="Legs") == {'FINISHED'}
assert len({p["id"] for p in poses()}) == len(poses())

print("pose library OK")
