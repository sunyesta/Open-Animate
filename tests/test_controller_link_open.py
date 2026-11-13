"""A 2 Axis Controller side takes ordinary actions only: a bone's own action (an action bone action) plays as that bone
turns, so a knob drives one through an ordinary action keying the bone's turn. Older files linked a side to a bone's
own action (one set of keys, the knob's): opened, each such side gets an ordinary action of its own keying that bone's
turn as its action did, and every frame plays as before.

tests/data/controller_dial_link.oanim was saved by the build with the link: joy's Right is turn_r's own action (a quarter
turn by frame 90), Left turn_l's (back a quarter by 60), the knob keyed on the mainline across both. The .json beside it
holds what frames 0-44 showed then.

Run with:  OpenAnimate --background --python tests/test_controller_link_open.py
"""

import json
import math
import os

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

assert ops.wm.open_mainfile(filepath=os.path.join(DATA, "controller_dial_link.oanim")) == {'FINISHED'}
want = json.load(open(os.path.join(DATA, "controller_dial_link.json")))
rig = next(l for l in layers.all() if l.type == 'BONE')
names = lambda: [a["name"] for a in rig.actions]
face = next(l for l in layers.all() if l.type == 'VECTOR')
bone = lambda n: next(b for b in rig.bones if b["name"] == n)

# --- The sides now play ordinary actions of their own; the bones keep theirs ---------------------------------------------
sides = bone("joy")["controller_actions"]
assert sides["RIGHT"] == "joy Right" and sides["LEFT"] == "joy Left", sides
for name in ("turn_r", "turn_l", "joy Right", "joy Left"):
    assert name in names(), (name, names())
assert "controller" not in bone("turn_r") and "held" not in bone("turn_r"), bone("turn_r")

# --- Every frame as the link played it ----------------------------------------------------------------------------------
worst = 0.0
for f in range(45):
    doc.frame_current = f
    w = want[str(f)]
    got = {"point": face.shown()[0][0],
           "turn_r": bone("turn_r")["angle"] - bone("turn_r")["setup_angle"],
           "turn_l": bone("turn_l")["angle"] - bone("turn_l")["setup_angle"],
           "knob": bone("joy")["knob"]}
    for k in ("turn_r", "turn_l"):
        worst = max(worst, abs(got[k] - w[k]))
        assert abs(got[k] - w[k]) < 1e-4, (f, k, got[k], w[k])
    for k in ("point", "knob"):
        for a, b in zip(got[k], w[k]):
            worst = max(worst, abs(a - b))
            assert abs(a - b) < 1e-4, (f, k, got[k], w[k])
print("worst difference", worst)

# --- Saved and opened again, nothing more changes ------------------------------------------------------------------------
tmp = os.path.join(os.environ.get("TEMP", "."), "oanim_controller_link_open.oanim")
assert ops.wm.save_as_mainfile(filepath=tmp) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=tmp) == {'FINISHED'}
rig = next(l for l in layers.all() if l.type == 'BONE')
face = next(l for l in layers.all() if l.type == 'VECTOR')
assert bone("joy")["controller_actions"]["RIGHT"] == "joy Right"
names = lambda: [a["name"] for a in rig.actions]
assert sorted(a for a in names() if a.startswith("joy")) == ["joy Left", "joy Right"], names()
doc.frame_current = 25
assert abs(face.shown()[0][0][0] - want["25"]["point"][0]) < 1e-4
os.remove(tmp)

# --- A side refuses a bone's own action, and the Bone tab's list doesn't offer it ------------------------------------------
doc.frame_current = 0
layers.active = rig
rig.select_bone("joy")
assert ops.armature.controller_side(side="UP", action="turn_r") == {'CANCELLED'}
assert bone("joy")["controller_actions"]["UP"] == ""
# An ordinary action goes in.
assert ops.anim.action_new(name="wave") == {'FINISHED'}
assert ops.anim.action_set(name="") == {'FINISHED'}
rig.select_bone("joy")
assert ops.armature.controller_side(side="UP", action="wave") == {'FINISHED'}
assert bone("joy")["controller_actions"]["UP"] == "wave"

print("Controller link open tests passed")
