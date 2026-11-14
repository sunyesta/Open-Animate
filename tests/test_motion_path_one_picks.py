"""One path shown at a time: what was picked on a path no longer shown (another chosen, another bone made active) is
let go, so no edit reaches the hidden path through it: dots (G with Edit Timing, Alt S, Even Spacing), path handles
and control points (G, V, X, Align), the Path Timing graph's points. The path chosen goes with its file. And edits
that change nothing are CANCELLED with no undo step: G R S on path keys by nothing, Alt S by 1.

Run with:  OpenAnimate --background --python tests/test_motion_path_one_picks.py
"""

import os
import tempfile

import oanim

ops, layers, wm = oanim.ops, oanim.data.layers, oanim.wm
OUT = tempfile.mkdtemp()


def doc():
    return oanim.data.document


def build():
    """Bones arm (x=0) and leg (x=3), both turning and moving on 10 and 20, both picked, leg active; saved and opened
    again so the keys are the undo base; the Motion Path tool on, frame 15."""
    assert ops.wm.read_homefile() == {'FINISHED'}
    d = doc()
    d.auto_key = True
    d.auto_freeze_keys = False
    d.motion_paths = True
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    for name, x in (("arm", 0.0), ("leg", 3.0)):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="1",
                                     parent="") == {'FINISHED'}
    for f, a in ((10, 0.5), (20, -0.3)):
        d.frame_current = f
        rig.bone_set("arm", angle=a, position=(0.2 * a, 0.1 + a))
        rig.bone_set("leg", angle=-a, position=(3.0 + a, 0.2 * a))
    rig.select_bone("arm")
    rig.select_bone("leg", extend=True)
    rid = rig.id
    path = os.path.join(OUT, "base.oanim")
    assert ops.wm.save_copy(filepath=path) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
    doc().frame_current = 15
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    return next(l for l in layers.all() if l.id == rid)


def poses(rig, name):
    d = doc()
    shown = d.frame_current
    out = []
    for f in range(25):
        d.frame_current = f
        out.append(tuple(round(v, 6) for v in rig.bone_pose(name)))
    d.frame_current = shown
    return out


def dots_picked_then_hidden(rig):
    """A dot picked on leg tip on frame 15 (Edit Timing), then arm tip shown: leg's poses on every frame."""
    assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING", proportional="0") == {'FINISHED'}
    assert ops.anim.motion_path_select(frame="15") == {'FINISHED'} and wm.motion_path_dots()
    assert ops.anim.motion_path_active_set(layer=str(rig.id), bone="arm") == {'FINISHED'}
    return poses(rig, "leg")


def keys(rig, path):
    return [(k["frame"], k["interp"], k.get("value")) for k in rig.keyframes(path)]


def steps():
    return wm.undo_history()


# --- Dots picked on leg tip, then arm tip shown: G (Edit Timing) leaves leg alone ----------------------------------------
rig = build()
leg = dots_picked_then_hidden(rig)
ops.anim.motion_path_dots_slide(x="0.3", y="0.0")
assert poses(rig, "leg") == leg, "G slid the hidden leg tip's dots"
assert not wm.motion_path_dots(), wm.motion_path_dots()

# --- Dots picked on leg tip, then arm tip shown: Alt S around the picks leaves leg alone ----------------------------------
rig = build()
leg = dots_picked_then_hidden(rig)
ops.anim.motion_path_scale_spacing(factor="0.5")
assert poses(rig, "leg") == leg, "Alt S scaled the hidden leg tip's timing"

# --- Dots picked on leg tip, then arm tip shown: Even Spacing of the picks leaves leg alone -------------------------------
rig = build()
leg = dots_picked_then_hidden(rig)
ops.anim.motion_path_even_spacing()
assert poses(rig, "leg") == leg, "Even Spacing respaced the hidden leg tip"

# --- A path handle picked on leg head, then arm head shown: G, V and X leave leg alone --------------------------------------
rig = build()
rid = str(rig.id)
assert ops.anim.motion_path_active_set(layer=rid, bone="leg", head="1") == {'FINISHED'}
assert ops.anim.motion_path_brush_set(brush="EDIT") == {'FINISHED'}
assert ops.anim.motion_path_handle_select(frame="10", out="1") == {'FINISHED'} and wm.motion_path_handle_picks()
assert ops.anim.motion_path_active_set(layer=rid, bone="arm", head="1") == {'FINISHED'}
leg, leg_keys = poses(rig, "leg"), keys(rig, 'bones["leg"].position')
assert ops.anim.motion_path_keys_transform(kind="G", x="0.3", y="0.2") == {'CANCELLED'}
assert ops.anim.motion_path_handles_type(mode="BROKEN") == {'CANCELLED'}
assert ops.anim.motion_path_handles_reset() == {'CANCELLED'}
assert poses(rig, "leg") == leg and keys(rig, 'bones["leg"].position') == leg_keys

# --- A control point added on leg head (and so picked), then arm head shown: G, Align and X leave it -------------------------
rig = build()
rid = str(rig.id)
assert ops.anim.motion_path_active_set(layer=rid, bone="leg", head="1") == {'FINISHED'}
assert ops.anim.motion_path_brush_set(brush="EDIT") == {'FINISHED'}
assert ops.anim.motion_path_control_add(frame="15") == {'FINISHED'}
assert ops.anim.motion_path_active_set(layer=rid, bone="arm", head="1") == {'FINISHED'}
leg = poses(rig, "leg")
for call in (lambda: ops.anim.motion_path_keys_transform(kind="G", x="0.3", y="0.2"),
             lambda: ops.anim.motion_path_controls_align(aligned="0"),
             lambda: ops.anim.motion_path_handles_reset()):
    assert call() == {'CANCELLED'}
assert poses(rig, "leg") == leg, "the hidden control point moved"

# --- The Path Timing graph's points picked on leg tip, then arm tip shown: G R S in the graph leave leg alone -------------
rig = build()
rid = str(rig.id)
assert wm.motion_path_active() == "leg tip"
assert ops.anim.timing_graph_set(mode="EDIT") == {'FINISHED'}
assert ops.anim.timing_select(action="ALL", frame="15") == {'FINISHED'} and wm.timing_picks()["picks"]
assert ops.anim.motion_path_active_set(layer=rid, bone="arm") == {'FINISHED'}
leg = poses(rig, "leg")
ops.anim.timing_transform(mode="SCALE", factor="0.5", axis="Y")
assert poses(rig, "leg") == leg, "the graph scaled the hidden leg tip's timing"

# --- The graph's points picked on leg tip, then arm tip shown: X in the graph leaves leg's curve -------------------------
rig = build()
rid = str(rig.id)
assert ops.anim.timing_graph_set(mode="EDIT") == {'FINISHED'}
assert ops.anim.timing_point_add(layer=rid, bone="leg", frame="15", x="0.5", y="0.8") == {'FINISHED'}
assert wm.timing_picks()["picks"], "the point put in is picked"
assert ops.anim.motion_path_active_set(layer=rid, bone="arm") == {'FINISHED'}
leg = poses(rig, "leg")
assert ops.anim.timing_point_delete() == {'CANCELLED'}
assert poses(rig, "leg") == leg, "X deleted points of the hidden leg tip's timing"

# --- The path chosen goes with its file: another file whose layer and bones have the same ids shows its own -------------
rig = build()
assert ops.anim.motion_path_active_set(layer=str(rig.id), bone="arm", head="1") == {'FINISHED'}
assert wm.motion_path_active() == "arm head"
assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
doc().motion_paths = True
assert ops.layer.new_bone() == {'FINISHED'}
other = layers.active
for name, x in (("cat", 0.0), ("dog", 3.0)):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="1", parent="") == {'FINISHED'}
other.select_bone("cat")
other.select_bone("dog", extend=True)
path = os.path.join(OUT, "other.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
assert wm.motion_path_active() == "dog tip", wm.motion_path_active()

# --- G R S on path keys that change nothing: CANCELLED, no undo step, no auto handles stored ------------------------------
rig = build()
rid = str(rig.id)
assert ops.anim.motion_path_active_set(layer=rid, bone="leg", head="1") == {'FINISHED'}
assert ops.anim.motion_path_brush_set(brush="EDIT", proportional="0") == {'FINISHED'}
assert ops.anim.motion_path_select(frame="10") == {'FINISHED'}
assert ops.anim.motion_path_select(frame="20", extend="1") == {'FINISHED'}
leg_keys, history = rig.keyframes('bones["leg"].position'), steps()
for kind, args in (("S", {"factor": "1"}), ("R", {"angle": "0"}), ("G", {"x": "0", "y": "0"})):
    assert ops.anim.motion_path_keys_transform(kind=kind, **args) == {'CANCELLED'}, (kind, args)
assert rig.keyframes('bones["leg"].position') == leg_keys, "auto handles stored by a transform by nothing"
assert steps() == history

# --- Alt S by 1: CANCELLED, the Smooth stretch left Smooth (no Custom curve stored) ---------------------------------------
rig = build()
rid = str(rig.id)
assert ops.anim.motion_path_active_set(layer=rid, bone="leg", head="1") == {'FINISHED'}
leg_keys, history = keys(rig, 'bones["leg"].position'), steps()
for frame in ("15", "12"):
    assert ops.anim.motion_path_scale_spacing(frame=frame, factor="1") == {'CANCELLED'}, frame
assert keys(rig, 'bones["leg"].position') == leg_keys, keys(rig, 'bones["leg"].position')
assert steps() == history

print("One path picks tests passed")
