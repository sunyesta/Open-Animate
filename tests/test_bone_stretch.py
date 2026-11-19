"""A stretch stays with its bone: what hangs from a bone stretched along its length (a key, an IK End's stretch, an Alt
drag, Maintain Volume's thinning) rides its tip but is never stretched or skewed by it; a bone's size all over (its
width's scale, evenly) still passes down as Inherit Scale says.

Run with:  OpenAnimate --background --python tests/test_bone_stretch.py
"""

import math

import oanim

ops = oanim.ops


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def scene():
    """A bent leg: Thigh straight down, Calf (connected) off to the side, Foot (connected) level; a square drawn on each
    bone's middle, its sides along and across the bone, its points following the bone."""
    global doc, layers, rig, squares
    ops.wm.read_homefile(confirmed="1")
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = layers.active
    for name, head, tail, parent in (("Pelvis", (0, 0), (0, 0.4), ""), ("Thigh", (0, 0), (0, -1.0), "Pelvis"),
                                     ("Calf", (0, -1.0), (0.7, -1.7), "Thigh"),
                                     ("Foot", (0.7, -1.7), (1.0, -1.7), "Calf")):
        assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                     tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    for name in ("Calf", "Foot"):
        assert ops.armature.bone_relations_set(bone=name, connected="1") == {'FINISHED'}
    squares = {}
    b = bones()
    for name in ("Thigh", "Calf", "Foot"):
        h, t = b[name]["head"], b[name]["tail"]
        n = dist(h, t)
        u = ((t[0] - h[0]) / n, (t[1] - h[1]) / n)
        v = (-u[1], u[0])
        m = ((h[0] + t[0]) / 2, (h[1] + t[1]) / 2)
        pts = [(m[0] + (a * u[0] + c * v[0]) * 0.1, m[1] + (a * u[1] + c * v[1]) * 0.1)
               for a, c in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        ops.layer.new()
        layers.active.name = "sq_" + name
        layers.active.add_curve(pts, closed=True)
        ops.layer.move_to_group(group=str(rig.id))
        layers.active = find("sq_" + name)
        assert ops.layer.parent_bone_set(bone=name, deform="POINTS") == {'FINISHED'}
        squares[name] = pts
    layers.active = rig
    doc.auto_key = True


def find(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def bones():
    doc.frame_current = doc.frame_current
    return {b["name"]: b for b in rig.bones}


def length(b, name):
    return dist(b[name]["head"], b[name]["tail"])


def square(name):
    """The square as it shows: its side along the bone, its side across, its corner's angle (degrees)."""
    l = find("sq_" + name)
    p = [l.to_document(q) for q in l.evaluated()[0]]
    e = (p[1][0] - p[0][0], p[1][1] - p[0][1])
    f = (p[2][0] - p[1][0], p[2][1] - p[1][1])
    cos = (e[0] * f[0] + e[1] * f[1]) / (math.hypot(*e) * math.hypot(*f))
    return math.hypot(*e), math.hypot(*f), math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def unchanged(name, what):
    along, across, corner = square(name)
    assert abs(along - 0.2) < 1e-4 and abs(across - 0.2) < 1e-4 and abs(corner - 90) < 1e-2, \
        (what, name, along, across, corner)


def key(frame, name, **values):
    doc.frame_current = frame
    rig.bone_set(name, **values)
    doc.frame_current = frame + 1
    doc.frame_current = frame


# --- A stretch keyed on the thigh: the calf rides its tip at its own size, not skewed --------------------------------
scene()
rest = bones()
key(10, "Thigh", scale=(1.0, 2.0))
b = bones()
assert abs(length(b, "Thigh") - 2.0) < 1e-4, length(b, "Thigh")
assert dist(b["Calf"]["head"], (0, -2.0)) < 1e-4, ("the calf on the stretched tip", b["Calf"]["head"])
assert abs(length(b, "Calf") - length(rest, "Calf")) < 1e-4, ("the calf as long as it was", length(b, "Calf"))
assert abs(length(b, "Foot") - length(rest, "Foot")) < 1e-4, ("the foot too", length(b, "Foot"))
along, across, corner = square("Thigh")
assert abs(along - 0.4) < 1e-4 and abs(across - 0.2) < 1e-4, ("the thigh's own drawing stretches", along, across)
unchanged("Calf", "not stretched or skewed by the thigh")
unchanged("Foot", "nor further down")

# --- Made bigger all over: its size passes down -------------------------------------------------------------------------
key(20, "Thigh", scale=(2.0, 2.0))
b = bones()
assert abs(length(b, "Calf") - 2 * length(rest, "Calf")) < 1e-4, ("twice as big all over", length(b, "Calf"))
assert abs(square("Foot")[0] - 0.4) < 1e-4 and abs(square("Foot")[2] - 90) < 1e-2, square("Foot")

# --- An IK End stretched out of reach: each bone of the chain stretches alike along its own length; the foot as it was --
scene()
rest = bones()
assert ops.armature.ik_base_add(bone="Pelvis") == {'FINISHED'}
assert ops.armature.ik_end_add(bone="Foot") == {'FINISHED'}
doc.frame_current = 10
far = (0.5, -4.0)
assert ops.armature.ik_drag(bone="Foot", x=repr(far[0]), y=repr(far[1]), stretch="1") == {'FINISHED'}
b = bones()
assert dist(b["Calf"]["tail"], far) < 1e-3, ("it reaches", b["Calf"]["tail"])
r_thigh = length(b, "Thigh") / length(rest, "Thigh")
r_calf = length(b, "Calf") / length(rest, "Calf")
assert r_thigh > 1.5 and abs(r_thigh - r_calf) < 1e-3, ("thigh and calf stretched alike", r_thigh, r_calf)
assert abs(b["Thigh"]["scale"][0] - 1.0) < 1e-6 and abs(b["Calf"]["scale"][0] - 1.0) < 1e-6, "only along"
assert abs(length(b, "Foot") - length(rest, "Foot")) < 1e-4, ("the foot as long as it was", length(b, "Foot"))
unchanged("Foot", "the foot's drawing not widened or slanted")
along, across, corner = square("Calf")
assert abs(across - 0.2) < 1e-4 and abs(corner - 90) < 1e-2, ("the calf stretched only along", along, across, corner)

# --- An Alt drag stretching the thigh, and G with Alt on its tip: what hangs from it keeps its size --------------------
for how in ("drag", "grab"):
    scene()
    rest = bones()
    doc.frame_current = 10
    t = rest["Thigh"]["tail"]
    if how == "drag":
        assert ops.armature.bone_drag(bone="Thigh", part="TIP", x=repr(t[0]), y=repr(t[1]), to_x=repr(t[0]),
                                      to_y=repr(t[1] - 0.8), stretch="1") == {'FINISHED'}
    else:
        rig.select_bone("Thigh", part="TAIL")
        assert ops.armature.translate(move_x="0", move_y="-0.8", posing="1", stretch="1") == {'FINISHED'}
    b = bones()
    assert abs(length(b, "Thigh") - 1.8) < 1e-3, (how, length(b, "Thigh"))
    assert abs(length(b, "Foot") - length(rest, "Foot")) < 1e-4, (how, "the foot keeps its size", length(b, "Foot"))
    unchanged("Foot", how)

# --- Turning a bone under a stretched parent by its tip: it points where it is taken, its size kept -------------------
scene()
rest = bones()
key(10, "Thigh", scale=(1.0, 2.0))
b = bones()
h = b["Calf"]["head"]
goal = (h[0] - 0.5, h[1] - 0.5)
rig.select_bone("Calf", part="TAIL")
t = b["Calf"]["tail"]
assert ops.armature.translate(move_x=repr(goal[0] - t[0]), move_y=repr(goal[1] - t[1]), posing="1") == {'FINISHED'}
b = bones()
way = math.atan2(b["Calf"]["tail"][1] - h[1], b["Calf"]["tail"][0] - h[0])
assert abs(way - math.atan2(-0.5, -0.5)) < 1e-3, ("G: it points at where its tip was taken", math.degrees(way))
assert abs(length(b, "Calf") - length(rest, "Calf")) < 1e-4, ("its size kept", length(b, "Calf"))
unchanged("Calf", "turned under a stretched parent")

# --- Maintain Volume thins the stretched bone, not what hangs from it --------------------------------------------------
scene()
rest = bones()
rig.select_bone("Thigh")
assert ops.armature.constraint_add(type="MAINTAIN_VOLUME") == {'FINISHED'}
key(10, "Thigh", scale=(1.0, 2.0))
along, across, corner = square("Thigh")
assert across < 0.19, ("the thigh thinned", across)
unchanged("Calf", "the calf not thinned")

print("bone stretch: ok")
