"""A 2 Axis Controller's spots stay inside its range: a spot left outside the box (a side's action made shorter, or the
side's action taken off) is deleted with that edit's undo step, and on opening a file; undo brings it back. Adding a
spot, or moving one to the knob, outside the box is refused.

Run with:  OpenAnimate --background --python tests/test_controller_spots_range.py
"""

import json
import pathlib
import tempfile
import zipfile

import oanim

ops = oanim.ops


def scene():
    """A knob "joy" playing Right: turn_r (keys to frame 40) and Up: look_up (to frame 20), each moving the face's
    first point. Spots: Far (30, 10), Near (5, 0), High (0, 15)."""
    global doc, layers, rig, face
    ops.wm.read_homefile(confirmed="1")
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_key = True
    ops.layer.new_bone()
    rig = layers.active
    ops.armature.bone_add(name="joy", head_x="-3.0", head_y="3.0", tail_x="-2.5", tail_y="3.0")
    rig.bone_set("joy", strength=0.0)
    ops.layer.new()
    face = layers.active
    face.add_curve([(0.0, 0.0), (1.0, 0.0)])
    ops.layer.move_to_group(group=str(rig.id))
    layers.active = rig
    for name, frames, moved in (("turn_r", 40, (2.0, 0.0)), ("look_up", 20, (0.0, 2.0))):
        assert ops.anim.action_new(name=name) == {'FINISHED'}
        doc.frame_current = frames
        face.set_point(0, moved)
        doc.frame_current = frames + 1
        doc.action = ""
        doc.frame_current = 0
    rig.select_bone("joy")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    for side, action in (("RIGHT", "turn_r"), ("UP", "look_up")):
        assert ops.armature.controller_side(side=side, action=action) == {'FINISHED'}
    for name, x, y in (("Far", 30, 10), ("Near", 5, 0), ("High", 0, 15)):
        assert ops.armature.controller_spot_add(name=name, x=str(x), y=str(y)) == {'FINISHED'}, name


def spots():
    b = next(b for b in rig.bones if b["name"] == "joy")
    return [n for n, _ in b["controller_spots"]]


def box():
    return next(b for b in rig.bones if b["name"] == "joy")["controller_box"]


def last_step():
    names, index = oanim.wm.undo_history()
    return names[index]


# --- A side's action made shorter: the spots past its new end go with that edit -----------------------------------------
scene()
assert spots() == ["Far", "Near", "High"]
assert ops.anim.action_set(name="turn_r") == {'FINISHED'}
face.keyframe_insert("points[0].pos", 20)
face.keyframe_delete("points[0].pos", 40)
assert [k["frame"] for k in face.keyframes("points[0].pos")] == [0, 20], face.keyframes("points[0].pos")
assert ops.anim.action_set(name="") == {'FINISHED'}
assert abs(box()[1][0] - 20.0) < 1e-3, ("Right now reaches frame 20", box())
assert spots() == ["Near", "High"], ("Far (30) is past the end", spots())
# Undo brings it back with the frames.
while spots() != ["Far", "Near", "High"] and oanim.wm.undo_history()[1] > 0:
    ops.ed.undo()
assert spots() == ["Far", "Near", "High"], spots()
assert abs(box()[1][0] - 40.0) < 1e-3, box()

# --- A side's action taken off: its spots go ----------------------------------------------------------------------------
scene()
assert ops.armature.controller_side(side="UP", action="") == {'FINISHED'}
assert spots() == ["Near"], ("Far and High were up the Up side", spots())
ops.ed.undo()
assert spots() == ["Far", "Near", "High"], spots()

# --- Edits elsewhere leave spots inside alone ----------------------------------------------------------------------------
scene()
doc.frame_current = 10
face.set_point(1, (1.0, 0.5))
doc.frame_current = 11
doc.frame_current = 0
assert ops.anim.keyframe_insert() in ({'FINISHED'}, {'CANCELLED'})
assert spots() == ["Far", "Near", "High"], spots()

# --- Adding or moving a spot outside the box is refused ------------------------------------------------------------------
scene()
assert ops.armature.controller_spot_add(name="Out", x="50", y="0") == {'CANCELLED'}
assert ops.armature.controller_spot_add(name="Below", x="0", y="-3") == {'CANCELLED'}, "no Down side"
assert spots() == ["Far", "Near", "High"]
assert ops.armature.controller_spot_add(name="Edge", x="40", y="20") == {'FINISHED'}, "the corner is inside"

# --- Opening a file with a spot outside the box deletes it ---------------------------------------------------------------
scene()
folder = pathlib.Path(tempfile.mkdtemp())
path = folder / "spots.oanim"
assert ops.wm.save_as_mainfile(filepath=str(path)) == {'FINISHED'}
with zipfile.ZipFile(path) as z:
    files = {n: z.read(n) for n in z.namelist()}
text = files["document.json"].decode("utf-8")
data = json.loads(text)


def push_out(o):
    if isinstance(o, dict):
        if o.get("name") == "Near" and "at" in o:
            o["at"] = [90.0, 0.0]
        for v in o.values():
            push_out(v)
    elif isinstance(o, list):
        for v in o:
            push_out(v)


push_out(data)
files["document.json"] = json.dumps(data).encode("utf-8")
broken = folder / "spots_out.oanim"
with zipfile.ZipFile(broken, "w", zipfile.ZIP_DEFLATED) as z:
    for n, b in files.items():
        z.writestr(n, b)
assert ops.wm.open_mainfile(filepath=str(broken)) == {'FINISHED'}
doc, layers = oanim.data.document, oanim.data.layers
rig = next(l for l in layers.all() if l.type == "BONE")
assert spots() == ["Far", "High"], ("Near, pushed to 90 in the file, went on opening", spots())

print("test_controller_spots_range: OK")
