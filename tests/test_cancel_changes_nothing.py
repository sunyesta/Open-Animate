"""An operator that refuses one of its settings changes nothing: Cancelled leaves no undo step, so anything it had
already written in stayed with no way back. Change Mask wrote the settings before a refused one; Convert Masking Areas
converted the rows before one that isn't there; Clip to Below set Exclude Strokes on a layer it then found not clipped;
Change Driver wrote the expression before refusing its variables; and Parent Bone with Keep Animation looked through
every action (dropping an action's frame 0 key) before finding the bone isn't there.

Run with:  OpenAnimate --background --python tests/test_cancel_changes_nothing.py
"""

import json
import os
import tempfile
import zipfile

import oanim

ops, L = oanim.ops, oanim.data.layers
TMP = tempfile.mkdtemp(prefix="oanim_cancel_")


def saved():
    """The document as saved, without the frame shown."""
    path = os.path.join(TMP, "now.oanim")
    assert ops.wm.save_copy(filepath=path) == {'FINISHED'}
    with zipfile.ZipFile(path) as z:
        d = json.loads(z.read("document.json"))["document"]
    d.pop("frame_current", None)
    return json.dumps(d, sort_keys=True)


def steps():
    return oanim.wm.undo_history()[1]


def refused(call, what):
    before, h = saved(), steps()
    assert call() == {'CANCELLED'}, what
    assert steps() == h, (what, "no undo step")
    assert saved() == before, (what, "changed the document")


def masked():
    """Two squares, the second masked by the first; an operator after the Python edits so they are in the base."""
    ops.wm.read_homefile(confirmed="1")
    ops.layer.new()
    a = L.active
    a.add_curve([(0, 0), (1, 0), (1, 1), (0, 1)], closed=True, fill=True)
    ops.layer.new()
    b = L.active
    b.add_curve([(0.5, 0.5), (2, 0.5), (2, 2), (0.5, 2)], closed=True, fill=True)
    assert ops.mask.add(layer=str(b.id), sources=str(a.id), mode="ADD") == {'FINISHED'}
    return b


# --- Change Mask: a setting taken before one refused ------------------------------------------------------------------
b = masked()
refused(lambda: ops.mask.set(layer=str(b.id), index="0", invert="1", grow="7", mode="BOGUS"), "Change Mask")

# --- Convert Masking Areas: a row before one the card hasn't -----------------------------------------------------------
b = masked()
refused(lambda: ops.mask.areas_set(layer=str(b.id), index="0", rows="0|1280", verb="REMOVE"), "Convert Masking Areas")

# --- Clip to Below off with Exclude Strokes, on a layer not clipped ----------------------------------------------------
masked()
ops.layer.new()
refused(lambda: ops.mask.clip_to_below(set="0", exclude_strokes="1"), "Clip to Below")

# --- Change Driver: an expression before variables refused -------------------------------------------------------------
ops.wm.read_homefile(confirmed="1")
ops.layer.new()
lay = L.active
lay.add_curve([(0, 0), (1, 0), (1, 1), (0, 1)], closed=True, fill=True)
assert ops.anim.driver_add(layer=str(lay.id), path="opacity", expression="0.5") == {'FINISHED'}
refused(lambda: ops.anim.driver_set(layer=str(lay.id), path="opacity", expression="0.25", vars="not json"),
        "Change Driver")

# --- Parent Bone with Keep Animation, a bone of another rig: the actions it would look through stay as they are --------
ops.wm.read_homefile(confirmed="1")
doc = oanim.data.document
doc.auto_freeze_keys = False
doc.frame_current = 0
ops.layer.new_bone()
rig = L.active
rig.name = "Rig"
assert ops.armature.bone_add(name="Arm", head_x="0", head_y="0", tail_x="1", tail_y="0") == {'FINISHED'}
ops.layer.new()
L.active.name = "Drawing"
L.active.add_curve([(0.1, 0.1), (0.9, 0.1)])
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
L.active = rig
assert ops.anim.action_new(name="Wave") == {'FINISHED'}
doc.auto_key = True
doc.frame_current = 5
rig.bone_set("Arm", angle=0.4)
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0
ops.layer.new_bone()
L.active.name = "Other"
assert ops.armature.bone_add(name="Elsewhere", head_x="3", head_y="0", tail_x="4", tail_y="0") == {'FINISHED'}
# An action's key on frame 0, as older files have (entering the action lets it go).
path = os.path.join(TMP, "frame0.oanim")
assert ops.wm.save_mainfile(filepath=path) == {'FINISHED'}
with zipfile.ZipFile(path) as z:
    files = {n: z.read(n) for n in z.namelist()}
data = json.loads(files["document.json"])
stack = list(data["document"]["layers"])
while stack:
    l = stack.pop()
    stack += l.get("children", [])
    if l.get("name") == "Rig":
        keys = l["bones"][0]["angle_keys_actions"]["Wave"]
        keys.insert(0, dict(keys[0], frame=0, value=0.0))
files["document.json"] = json.dumps(data).encode()
with zipfile.ZipFile(path, "w") as z:
    for n, b in files.items():
        z.writestr(n, b)
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
doc = oanim.data.document
doc.frame_current = 0
assert '"frame": 0' in json.dumps(json.loads(saved()))  # (the key is there to lose)
L.active = next(l for l in L.all() if l.name == "Drawing")
refused(lambda: ops.layer.parent_bone_set(bone="Elsewhere", keep_animation="1"), "Parent Bone, Keep Animation")

print("cancel changes nothing: ok")
