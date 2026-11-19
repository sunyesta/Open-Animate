"""The Select tool drags bones as it drags points (Blender's tweak): pressing on a bone, one of its ends or its body, and
dragging moves it as G does, ending as the mouse comes up, one undo step (Move Bones). An unpicked bone is picked alone
first; a picked one brings the whole selection. Alt stretches as with G: a tip goes exactly to the mouse, a connected
bone moves whole. A press on empty space still draws a box, and a point over a bone's body still takes the press.
(A press on a bone only ever box-selected: bones moved only by G.)

Run with:  OpenAnimate --background --python tests/test_bone_drag.py
"""

import math

import oanim

ops, wm = oanim.ops, oanim.wm
zoom = 100.0


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def scene():
    global doc, layers, rig
    ops.wm.read_homefile(confirmed="1")
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = layers.active
    for name, head, tail, parent in (("Upper", (0, 0), (1, 0), ""), ("Fore", (1, 0), (2, 0), "Upper"),
                                     ("Hand", (2, 0), (2.4, 0), "Fore"), ("Other", (0, 2), (1, 2), "")):
        assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                     tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    for name in ("Fore", "Hand"):
        assert ops.armature.bone_relations_set(bone=name, connected="1") == {'FINISHED'}
    doc.auto_key = True
    doc.frame_current = 10
    rig.select_bone("Hand")


def bones():
    doc.frame_current = doc.frame_current
    return {b["name"]: b for b in rig.bones}


def picked():
    return sorted(b["name"] for b in rig.bones if b["selected"])


def same(a, b, tol=1e-6):
    return all(dist(a[n][k], b[n][k]) < tol for n in a for k in ("head", "tail"))


# --- A bone's body dragged: picked alone, moved as G moves it, one undo step -------------------------------------------
scene()
b0 = bones()
assert wm.bone_drag((1.5, 0.0), [(1.5, 0.2), (1.5, 0.5)], zoom=zoom), "the press takes the bone"
assert picked() == ["Fore"], ("picked alone", picked())
dragged = bones()
assert not same(dragged, b0), "the bone moved"
assert dist(dragged["Upper"]["head"], b0["Upper"]["head"]) < 1e-6, "its parent's head stays"
ops.ed.undo()
assert same(bones(), b0), "one undo step takes it back"
rig.select_bone("Fore")
assert ops.armature.translate(move_x="0", move_y="0.5", posing="1") == {'FINISHED'}
assert same(bones(), dragged), "the same as G by the mouse's move"

# --- Let go with Esc or a right-click: nothing changed -----------------------------------------------------------------
scene()
b0 = bones()
assert wm.bone_drag((1.5, 0.0), [(1.5, 0.5)], zoom=zoom, confirm=False)
assert same(bones(), b0), "cancelled, the pose is as it was"

# --- Posing, a tip dragged: the bone turns to follow the mouse; Alt takes the tip exactly there, the bone stretching ----
# (posing picks bones whole, so the tip was out of reach of Alt's stretch). The bone is picked whole after.
scene()
b0 = bones()
assert wm.bone_drag((2.4, 0.0), [(2.5, 0.2), (2.6, 0.4)], alt=True, zoom=zoom)
b = bones()
assert dist(b["Hand"]["tail"], (2.6, 0.4)) < 1e-4, ("Alt: the tip goes exactly there", b["Hand"]["tail"])
assert b["Hand"]["scale"][1] > 1.05, ("the bone stretching", b["Hand"]["scale"])
assert dist(b["Hand"]["head"], b0["Hand"]["head"]) < 1e-6, "its base stays"
assert picked() == ["Hand"] and b["Hand"]["select_head"] and b["Hand"]["select_tail"], "picked whole again"
ops.ed.undo()
assert same(bones(), b0), "one undo step takes it back"
scene()
assert wm.bone_drag((1.0, 2.0), [(1.0, 2.5), (1.0, 3.0)], zoom=zoom)
b = bones()
assert dist(b["Other"]["head"], (0.0, 2.0)) < 1e-6, "turning about its base"
assert dist(b["Other"]["tail"], (math.sqrt(0.5), 2.0 + math.sqrt(0.5))) < 1e-4, ("toward the mouse", b["Other"]["tail"])
assert picked() == ["Other"], picked()
# Its tip pressed as one of several bones picked: they all move, as from the body.
scene()
rig.select_bone("Upper")
rig.select_bone("Other", extend=True)
assert wm.bone_drag((1.0, 2.0), [(1.0, 2.5)], zoom=zoom)
b = bones()
assert dist(b["Other"]["head"], (0.0, 2.5)) < 1e-4 and dist(b["Upper"]["head"], (0.0, 0.5)) < 1e-4, "the selection moves"

# --- Alt on a connected bone's body: it moves whole, its parent turning and stretching to reach it ----------------------
scene()
b0 = bones()
assert wm.bone_drag((1.5, 0.0), [(1.6, 0.1), (1.7, 0.3)], alt=True, zoom=zoom)
b = bones()
want = (b0["Fore"]["head"][0] + 0.2, b0["Fore"]["head"][1] + 0.3)
assert dist(b["Fore"]["head"], want) < 1e-4, ("Alt on a connected bone: it moves whole", b["Fore"]["head"], want)
assert dist(b["Upper"]["tail"], want) < 1e-4, ("its parent reaching it", b["Upper"]["tail"])
assert abs(b["Upper"]["scale"][1] - 1.0) > 0.02, "the parent stretching"

# --- A picked bone dragged brings the whole selection ------------------------------------------------------------------
scene()
rig.select_bone("Upper")
rig.select_bone("Other", extend=True)
b0 = bones()
assert wm.bone_drag((0.5, 2.0), [(0.5, 2.5)], zoom=zoom)
assert picked() == ["Other", "Upper"], ("both stay picked", picked())
b = bones()
assert dist(b["Other"]["head"], (0.0, 2.5)) < 1e-4, ("the bone pressed moves", b["Other"]["head"])
assert dist(b["Upper"]["head"], (0.0, 0.5)) < 1e-4, ("the other picked bone moves with it", b["Upper"]["head"])

# --- Empty space: no bone taken (a box) ----------------------------------------------------------------------------------
scene()
b0 = bones()
assert not wm.bone_drag((1.5, -1.5), [(2.0, -2.0)], zoom=zoom), "a press on empty space takes no bone"
assert same(bones(), b0) and picked() == ["Hand"], picked()

# --- A point of a drawing edited with the bones, over a bone's body, takes the press -------------------------------------
scene()
ops.layer.new()
layers.active.name = "Sleeve"
layers.active.add_curve([(0.5, 0.0), (0.5, -0.6), (0.9, -0.6)], closed=False)
ops.layer.move_to_group(group=str(rig.id))
sleeve = next(l for l in layers.all() if l.name == "Sleeve")
sleeve.edit_with_bones = True
layers.active = rig
rig.select_bone("Hand")
assert not wm.bone_drag((0.5, 0.0), [(0.5, 0.5)], zoom=zoom), "the point over the body wins"
assert wm.bone_drag((0.2, 0.0), [(0.2, 0.3)], zoom=zoom), "the body away from the point is the bone's"
assert picked() == ["Upper"], picked()

print("bone drag: ok")
