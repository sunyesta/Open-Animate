"""Layer Symmetrize keeps the animation: the other side's copy plays the source's keys mirrored (animation=MIRROR, the
default), every timeline, an action's keys going to its other side's action; KEEP_PARTNER keeps a remade partner's own
animation on its new points; NONE leaves the copy at rest as Symmetrize first did. Each section starts from a new file.

Run with:  OpenAnimate --background --python tests/test_layer_symmetrize_keys.py
"""

import math

import oanim

ops = oanim.ops


def fresh():
    assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    d = oanim.data.document
    d.auto_key = True
    d.auto_freeze_keys = False
    d.frame_current = 0
    return d


def L():
    return oanim.data.layers


def find(name):
    return next((l for l in L().all() if l.name == name), None)


def new(name, points, closed=False):
    ops.layer.new()
    l = L().active
    l.name = name
    l.add_curve(points, closed=closed)
    return l


def curve(l):
    """The drawing as shown, sampled along its Bezier segments, in document space."""
    points, curves = l.shown()
    out = []
    for cps, closed in curves:
        for a, b in list(zip(cps, cps[1:])) + ([(cps[-1], cps[0])] if closed else []):
            p0, p1, p2, p3 = points[a[0]], a[2], b[1], points[b[0]]
            for i in range(9):
                t = i / 8
                u = 1 - t
                p = tuple(u * u * u * p0[k] + 3 * u * u * t * p1[k] + 3 * u * t * t * p2[k] + t * t * t * p3[k]
                          for k in (0, 1))
                out.append(l.to_document(p))
    return out


def mirror_gap(a, b, axis=0.0):
    """How far layer b's shown drawing is from layer a's flipped across x = axis."""
    pa = [(2 * axis - x, y) for x, y in curve(a)]
    pb = curve(b)
    near = lambda p, q: min(math.dist(p, x) for x in q)
    return max(max(near(p, pb) for p in pa), max(near(p, pa) for p in pb))


def keyed(l, path):
    """Its keys, leaving out Key Together's fillers (which hold what the frame shows)."""
    return {k["frame"]: k["value"] for k in l.keyframes(path) if not k.get("filler")}


def at(d, frame):
    d.frame_current = frame + 1
    d.frame_current = frame


EAR = [(0.6, 0.0), (0.9, 0.4), (1.3, 0.1)]


def animated_ear(d):
    ear = new("Ear_L", EAR)
    d.frame_current = 10
    ear.set_point(1, (1.0, 0.7))
    ear.move_handle(0, 1, "OUT", (1.2, 0.9))
    ear.location_x = 0.4
    ear.rotation = 25.0
    at(d, 0)
    return ear


# --- The copy plays the source's points, handles and transform keys mirrored -------------------------------------
d = fresh()
ear = animated_ear(d)
L().active = ear
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
ear_r = find("Ear_R")
assert 10 in keyed(ear_r, "points[1].pos") and 10 in keyed(ear_r, "rotation"), ear_r.keyframes("points[1].pos")
for f in (0, 4, 10, 14):
    at(d, f)
    assert mirror_gap(ear, ear_r) < 2e-3, ("mirrored on every frame", f, mirror_gap(ear, ear_r))
at(d, 10)
assert abs(ear_r.rotation + 25.0) < 1e-3 and abs(ear_r.location_x + 0.4) < 1e-4, (ear_r.rotation, ear_r.location_x)

# --- A group: its own keys and its layers' inside, mirrored ---------------------------------------------------------
d = fresh()
ops.layer.new_group()
arm = L().active
arm.name = "Arm_L"
arm.location_x = 1.0
hand = new("Hand_L", [(0.0, 0.0), (0.5, 0.1), (0.4, 0.5)])
assert ops.layer.move_to_group(group=str(arm.id)) == {'FINISHED'}
hand = find("Hand_L")
d.frame_current = 12
find("Arm_L").location_y = 0.5
hand.rotation = 40.0
hand.location_x = 0.3
hand.set_point(2, (0.2, 0.8))
at(d, 0)
L().active = find("Arm_L")
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
for f in (0, 6, 12):
    at(d, f)
    assert mirror_gap(find("Hand_L"), find("Hand_R")) < 2e-3, ("the hand inside, mirrored", f)

# --- Actions around it: each one's keys go to its other side's ------------------------------------------------------
d = fresh()
ops.layer.new_bone()
rig = L().active
rig.name = "Rig"
ops.armature.bone_add(name="Head", head_x="0.0", head_y="2.0", tail_x="0.0", tail_y="2.5")
rig.bone_set("Head", strength=0.0)
eye = new("Eye_L", [(0.4, 1.0), (0.6, 1.2), (0.8, 1.0)])
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
eye = find("Eye_L")
setup = {b["name"]: b["setup_angle"] for b in rig.bones}
moves = {"Head": (0.5, 1.5), "Head 2": (0.7, 0.6), "Blink_L": (0.6, 1.05), "Blink_R": (0.6, 1.3), "Talk": (0.9, 1.2),
         "Wink_L": (0.55, 1.1)}
for name in ("Head", "Head 2", "Blink_L", "Blink_R", "Talk", "Wink_L"):
    L().active = rig
    rig.select_bone("Head")
    own = name.startswith("Head")
    assert ops.anim.action_new(name=name, action_bone="1" if name == "Head" else "0") == {'FINISHED'} and d.action == name
    d.frame_current = 10
    if own:
        rig.bone_set("Head", angle=setup["Head"] + (0.6 if name == "Head" else -0.6))
    eye.set_point(1, moves[name])
    at(d, 0)
    d.action = ""
L().active = eye
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
assert "Wink_L" in oanim.wm.banner_report()[3], ("said so", oanim.wm.banner_report())
eye_r = find("Eye_R")


def in_action(name, layer):
    d.action = name
    at(d, 10)
    return curve(layer)


for to, frm in (("Head 2", "Head"), ("Head", "Head 2"), ("Blink_R", "Blink_L"), ("Blink_L", "Blink_R"),
                ("Talk", "Talk")):
    d.action = to
    assert 10 in keyed(eye_r, "points[1].pos"), ("keys in", to)
    d.action = frm
    at(d, 10)
    left = [(-x, y) for x, y in curve(eye)]
    d.action = to
    at(d, 10)
    right = curve(eye_r)
    gap = max(min(math.dist(p, q) for q in right) for p in left)
    assert gap < 2e-3, (to, "plays", frm, "mirrored", gap)
d.action = "Wink_L"
assert 10 not in keyed(eye_r, "points[1].pos"), "no Wink_R: its keys are left out"
d.action = ""

# --- A bone layer inside a mirrored group: its bones' keys and its own actions go across with it -----------------
d = fresh()
ops.layer.new_group()
grp = L().active
grp.name = "Leg_L"
ops.layer.new_bone()
leg = L().active
leg.name = "LegRig"
ops.armature.bone_add(name="knee_L", head_x="0.5", head_y="0.0", tail_x="1.0", tail_y="0.0")
assert ops.layer.move_to_group(group=str(grp.id)) == {'FINISHED'}
new("Shin", [(0.5, 0.0), (0.8, -0.1), (1.0, 0.0)])
assert ops.layer.move_to_group(group=str(find("LegRig").id)) == {'FINISHED'}
leg = find("LegRig")
L().active = leg
leg.select_bone("knee_L")
setup = {b["name"]: b["setup_angle"] for b in leg.bones}
d.frame_current = 5
leg.bone_set("knee_L", angle=setup["knee_L"] + 0.3)
at(d, 0)
assert ops.anim.action_new(name="knee_L", action_bone="1") == {'FINISHED'}
d.frame_current = 10
leg.bone_set("knee_L", angle=setup["knee_L"] + 0.6)
at(d, 0)
d.action = ""
L().active = find("Leg_L")
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
rig_r = next(l for l in find("Leg_R").children if l.type == 'BONE')
assert [b["name"] for b in rig_r.bones] == ["knee_R"], rig_r.bones
assert [a["name"] for a in rig_r.actions] == ["knee_R"], rig_r.actions
turn = keyed(rig_r, 'bones["knee_R"].angle')
assert abs(turn[5] + 0.3) < 1e-4, ("the mainline's turn, the other way", turn)
d.action = "knee_R"
turn = keyed(rig_r, 'bones["knee_R"].angle')
assert abs(turn[10] + 0.6) < 1e-4, ("its own action's, the other way", turn)
d.action = ""

# --- Keep Partner's: the shape from the source, the animation the partner's own -----------------------------------
d = fresh()
ear = animated_ear(d)
L().active = ear
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
ear_r = find("Ear_R")
d.frame_current = 20
p = ear_r.points[0]
ear_r.set_point(0, (p[0] - 0.2, p[1] + 0.3))
at(d, 0)
own = keyed(ear_r, "points[0].pos")
ear.set_point(2, (1.4, -0.1))   # the setup drawing fixed on one side
L().active = ear
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE", animation="KEEP_PARTNER") == {'FINISHED'}
ear_r = find("Ear_R")
assert mirror_gap(ear, ear_r) < 2e-3, "the new shape"
kept = keyed(ear_r, "points[0].pos")
assert sorted(kept) == sorted(own) and all(math.dist(kept[f], own[f]) < 1e-5 for f in own), ("its own keys", own, kept)
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
ear_r = find("Ear_R")
assert 20 not in keyed(ear_r, "points[0].pos") and 10 in keyed(ear_r, "points[1].pos"), "Mirror: the source's"

# --- None: the copy rests, as Symmetrize first did -----------------------------------------------------------------
d = fresh()
ear = animated_ear(d)
L().active = ear
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE", animation="NONE") == {'FINISHED'}
ear_r = find("Ear_R")
assert 10 not in keyed(ear_r, "points[1].pos") and 10 not in keyed(ear_r, "rotation"), ear_r.keyframes("rotation")
at(d, 10)
assert abs(ear_r.rotation) < 1e-6 and mirror_gap(ear, ear_r) > 0.05, "it rests"

# --- A switch remade keeps picking its own children ----------------------------------------------------------------
d = fresh()
ops.layer.new_switch()
sw = L().active
sw.name = "Hand_L"
for name, pts in (("Open_L", [(0.5, 0.0), (0.9, 0.3), (1.2, 0.0)]), ("Fist_L", [(0.6, 0.0), (0.8, 0.2), (1.0, 0.0)])):
    new(name, pts)
    assert ops.layer.move_to_group(group=str(sw.id)) == {'FINISHED'}
d.frame_current = 10
assert ops.layer.switch_set(layer="Hand_L", child="Fist_L") == {'FINISHED'}
at(d, 0)
for _ in range(2):   # made, then remade in place (its children taking their old ids)
    L().active = find("Hand_L")
    assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
    at(d, 10)
    hand_r = find("Hand_R")
    assert hand_r.switch_active == "Fist_R", (hand_r.switch_active, [c.name for c in hand_r.children])
    at(d, 0)

print("Layer symmetrize keys tests passed")
