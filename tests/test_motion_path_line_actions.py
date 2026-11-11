"""The line between a path's dots where actions move the bone as much as its own keys: a knob's action carries an ear
across while the ear's own keys move it a little, its handle dragged far out (as on the eye rig, an ear's key's handle
pulled down to the key before). The keys' curve then bends sharply between two dots, and drawn to the dots' step (the
action's) that bend made a loop; the line keeps to the dots there.

Run with:  OpenAnimate --background --python tests/test_motion_path_line_actions.py
"""

import math

import oanim
import _oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

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


def settle():
    doc.frame_current += 1
    doc.frame_current -= 1


# The knob's right side carries the ear across (as a head turn does).
assert ops.anim.action_new(name="Knob Right") == {'FINISHED'}
doc.frame_current = 24
p = bone("Ear")["position"]
rig().bone_set("Ear", position=(p[0] - 0.6, p[1]))
doc.frame_current = 25
ops.anim.action_set(name="")
doc.frame_current = 0
rig().select_bone("Knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="Knob Right") == {'FINISHED'}
# On the mainline the knob goes right over 6-30, and the ear has keys of its own on 6 and 30, a little up on 30.
for f, ear in ((6, (0.002, 0.0)), (30, (-0.01, 0.0015))):
    doc.frame_current = f
    s = bone("Ear")["setup_position"]
    rig().bone_set("Ear", position=(s[0] + ear[0], s[1] + ear[1]))
    settle()
# (The knob keyed after, so what its action adds goes on top of the ear's keys.)
for f, knob in ((6, (0.0, 0.0)), (30, (24.0, 0.0))):
    doc.frame_current = f
    rig().bone_set("Knob", knob=knob)
    settle()
doc.auto_key = False

doc.motion_paths = True
doc.path_all = True
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert doc.path_own_motion
layers.active = rig()
rig().select_bone("Ear")
args = dict(bone="Ear", head="1", layer=str(rig_id))
# Follow Action: the ear's keys what is added to the action (an edit would put it On Path, its keys the path as seen).
assert ops.anim.motion_path_on_path(on="0", **args) == {'FINISHED'}
assert ops.anim.motion_path_select(frame="30", **args) == {'FINISHED'}
doc.frame_current = 18


def path():
    return next(p for p in wm.motion_paths(kept=False) if p["label"] == "Ear head")


dots = path()["points"]
first = path()["first"]
assert first <= 6 and len(dots) > 30 - first, (first, len(dots))
k0, k24 = dots[6 - first], dots[30 - first]
assert math.dist(k0, k24) > 0.3, ("the action carries the ear across", k0, k24)
# The out handle of 6 out the way it goes, the in handle of 30 pulled down and back toward 6, far past where its own keys
# reach: their curve hooks.
assert ops.anim.motion_path_handle(frame="6", side="OUT", x=str(k0[0] - 0.05), y=str(k0[1] + 0.12), **args) == {'FINISHED'}
assert ops.anim.motion_path_handle(frame="30", side="IN", x=str(k24[0] + 0.05), y=str(k24[1] - 0.25), **args) == {'FINISHED'}
keys = rig().keyframes('bones["Ear"].position')
assert keys[1]["path_handles"] != "AUTO", keys

dots = path()["points"]
first = path()["first"]
r = _oanim.overlay_colors(rig_id, (0.3, 0.2, 0.15), (0.3, 0.2, 0.15), 0.0, 0.002, False)
pieces = next(p for p in r["paths"] if p["label"] == "Ear head")["pieces"]
assert pieces


def stray(e):
    """How far a point of the line is off the dots' own line (the nearest step between two dots)."""
    best = 1e9
    for a, b in zip(dots, dots[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        dd = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((e[0] - a[0]) * dx + (e[1] - a[1]) * dy) / dd)) if dd > 1e-14 else 0.0
        best = min(best, math.hypot(e[0] - a[0] - dx * t, e[1] - a[1] - dy * t))
    return best


step = min(math.dist(a, b) for a, b in zip(dots, dots[1:]) if math.dist(a, b) > 1e-6)
worst = max(stray(e) for k in pieces for e in (k["a"], k["b"]))
assert worst < 0.2 * step, (f"the line strays {worst:.5f} off the dots (a step between them is {step:.5f} at least): "
                            "the ear's keys' curve, bent between two dots, looped drawn to the action's step")

print("test_motion_path_line_actions: ok")
