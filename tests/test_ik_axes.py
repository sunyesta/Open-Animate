"""IK worked out in the axes the chain's base turns in. Under a parent flipped one way (scale -1 across), a turn of a
bone goes the other way in the layer, so stepping toward the goal stepped away from it: a leg's tip reaches its goal
under a flipped hip, by its IK and by Auto IK dragging the tip, and a leg in a bone group flipped (a mirrored copy)
hung from an outer bone. Under a parent stretched one way the chain is a rigid one stretched, reaching every goal the
stretch takes in reach. Arc IK dragged with Limit Angle on the joints counts each joint's bend as the limit leaves it,
reaching a goal inside the limits. A chain of three bones reaches goals in reach (24 steps on the bones fell short).

Run with:  OpenAnimate --background --python tests/test_ik_axes.py
"""

import math
import random

import oanim

ops = oanim.ops
doc, layers = oanim.data.document, oanim.data.layers


def new_rig():
    doc.auto_freeze_keys = False
    doc.auto_key = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    return layers.active


def find(layer):
    return next(l for l in layers.all() if l.id == layer.id)


def add(rig, name, head, tail, parent=""):
    assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                 tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
    ops.armature.select_none()


def constrain(rig, bone, type, **kw):
    rig.select_bone(bone)
    assert ops.armature.constraint_add(type=type, bone=bone) == {'FINISHED'}
    n = len(rig.bone_constraints(bone)) - 1
    if kw:
        rig.bone_constraint_set(bone, n, **kw)
    ops.armature.select_none()


def bones(rig):
    doc.frame_current = doc.frame_current
    return {b["name"]: b for b in rig.bones}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def leg(rig, parent="Hip"):
    """A thigh and a calf, the knee bent a little, the calf's IK aimed at Goal."""
    add(rig, "Thigh", (0, 0), (0.1, -1.0), parent)
    add(rig, "Calf", (0.1, -1.0), (0.0, -2.0), "Thigh")
    add(rig, "Goal", (0.0, -2.0), (0.2, -2.0))
    constrain(rig, "Calf", "IK", target="Goal")


# --- a flipped hip: the IK and Auto IK
rig = new_rig()
add(rig, "Hip", (0, 0), (0.5, 0))
leg(rig)
rig.bone_set("Hip", ik_ignore=True)
doc.auto_key = True
doc.frame_current = 1
rig.bone_set("Hip", scale=(-1.0, 1.0))
for goal in ((0.6, -1.4), (-0.7, -1.2), (0.3, -1.8), (-0.2, -0.9)):
    rig.bone_set("Goal", position=goal)
    b = bones(rig)
    miss = dist(b["Calf"]["tail"], b["Goal"]["head"])
    assert miss < 1e-4, ("under a flipped hip the calf reaches its goal", goal, miss)
# Auto IK: the calf's tip dragged, its IK off.
rig.bone_constraint_set("Calf", 0, enabled=False)
for goal in ((0.6, -1.4), (-0.5, -1.5)):
    t = bones(rig)["Calf"]["tail"]
    rig.select_bone("Calf", part="TAIL")
    assert rig.move_bone_ends((goal[0] - t[0], goal[1] - t[1]))
    ops.armature.select_none()
    miss = dist(bones(rig)["Calf"]["tail"], goal)
    assert miss < 1e-4, ("Auto IK under a flipped hip reaches", goal, miss)

# --- a flipped bone group hung from an outer bone
outer = new_rig()
add(outer, "Hip", (0, 0), (0.5, 0))
assert ops.layer.new_bone() == {'FINISHED'}
inner = layers.active
assert ops.layer.move_to_group(group=str(outer.id)) == {'FINISHED'}
inner = find(inner)
layers.active = inner
inner.scale_x = -1.0
inner = find(inner)
leg(inner, "")
inner = find(inner)
inner.select_bone("Thigh")
assert ops.armature.bone_parent_set(bone="Thigh", parent="Hip", parent_layer=str(outer.id)) == {'FINISHED'}
ops.armature.select_none()
doc.auto_key = True
doc.frame_current = 1
inner = find(inner)
for goal in ((0.6, -1.4), (-0.6, -1.4), (0.2, -1.1)):
    inner.bone_set("Goal", position=goal)
    b = bones(inner)
    miss = dist(b["Calf"]["tail"], b["Goal"]["head"])
    assert miss < 1e-4, ("in a flipped bone group the calf reaches its goal", goal, miss)

# --- a hip stretched one way
rig = new_rig()
add(rig, "Hip", (0, 0), (0.5, 0))
leg(rig)
rig.bone_set("Hip", ik_ignore=True)
doc.auto_key = True
doc.frame_current = 1
rig.bone_set("Hip", scale=(2.0, 1.0))  # 2 across the hip: the layer's y doubled below it
b = bones(rig)
here = lambda p: (p[0], p[1] / 2)
l1 = dist(here(b["Thigh"]["head"]), here(b["Calf"]["head"]))
l2 = dist(here(b["Calf"]["head"]), here(b["Calf"]["tail"]))
worst = 0.0
for i in range(40):
    a = -math.pi / 2 + 1.0 * math.sin(i * 0.37)
    r = (l1 + l2) * (0.4 + 0.5 * ((i * 0.618) % 1.0))
    goal = (r * math.cos(a), 2 * r * math.sin(a))
    rig.bone_set("Goal", position=goal)
    b = bones(rig)
    worst = max(worst, dist(b["Calf"]["tail"], b["Goal"]["head"]))
assert worst < 1e-3, ("under a stretched hip the calf reaches goals in reach", worst)

# --- Arc IK dragged with Limit Angle on the joints
for n in (2, 3):
    rig = new_rig()
    add(rig, "Base", (-0.5, 0), (0, 0))
    prev = "Base"
    for k in range(n):
        add(rig, "B%d" % k, (k, 0.05 * k * k), (k + 1.0, 0.05 * (k + 1.0) ** 2), prev)
        prev = "B%d" % k
    rig.bone_set("Base", ik_ignore=True)
    rig.bone_set("B%d" % (n - 1), arc_ik=True)
    for k in range(1, n):
        constrain(rig, "B%d" % k, "LIMIT_ANGLE", min_angle=-0.2, max_angle=0.8)
    rest = bones(rig)
    # Every joint turned 0.4 (inside the limits), the base -0.5.
    x = y = 0.0
    for k in range(n):
        h, t = rest["B%d" % k]["head"], rest["B%d" % k]["tail"]
        a = math.atan2(t[1] - h[1], t[0] - h[0]) - 0.5 + 0.4 * k
        x, y = x + dist(h, t) * math.cos(a), y + dist(h, t) * math.sin(a)
    doc.auto_key = True
    doc.frame_current = 1
    end = "B%d" % (n - 1)
    t = bones(rig)[end]["tail"]
    rig.select_bone(end, part="TAIL")
    assert rig.move_bone_ends((x - t[0], y - t[1]))
    ops.armature.select_none()
    miss = dist(bones(rig)[end]["tail"], (x, y))
    assert miss < 3e-3, ("Arc IK with limits reaches a goal inside them", n, miss)

# --- a chain of three bones reaches goals in reach
rig = new_rig()
add(rig, "Base", (-0.5, 0), (0, 0))
prev = "Base"
for k in range(3):
    add(rig, "B%d" % k, (k, 0.05 * k * k), (k + 1.0, 0.05 * (k + 1.0) ** 2), prev)
    prev = "B%d" % k
add(rig, "Goal", (3, 0.5), (3.2, 0.5))
rig.bone_set("Base", ik_ignore=True)
constrain(rig, "B2", "IK", target="Goal")
doc.auto_key = True
doc.frame_current = 1
pts = [(k, 0.05 * k * k) for k in range(4)]
seg = [(math.atan2(pts[k + 1][1] - pts[k][1], pts[k + 1][0] - pts[k][0]), dist(pts[k], pts[k + 1])) for k in range(3)]
random.seed(3)
worst = 0.0
for trial in range(20):
    turns = [random.uniform(-0.8, 0.8) for _ in range(2)]
    acc, x, y = random.uniform(-1, 1), 0.0, 0.0
    for k in range(3):
        acc += turns[k - 1] if k else 0.0
        x += seg[k][1] * math.cos(seg[k][0] + acc)
        y += seg[k][1] * math.sin(seg[k][0] + acc)
    rig.bone_set("Goal", position=(x, y))
    b = bones(rig)
    worst = max(worst, dist(b["B2"]["tail"], b["Goal"]["head"]))
assert worst < 1e-4, ("a three-bone chain reaches goals in reach", worst)
print("test_ik_axes passed")
