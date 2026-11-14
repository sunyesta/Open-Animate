"""On Path put on quickly: the frames from the bone's first key to its last are worked out side by side, values only.

Putting a path On Path works out where the bone is on every frame between its keys. Bone dynamics anywhere in the rig
had that done one frame at a time, every frame posed in full (Look At's and Limit to Shape's drawings bent each time).
Where nothing that poses bones can change the bone's values (its actions played from bones' own values alone), the
frames go side by side with only values worked out, and come out as working everything out does. Where something could
(a knob playing where it is posed, hanging from a bone with dynamics), it is worked out in full, one frame at a time.

Run with:  OpenAnimate --background --python tests/test_motion_path_on_path_fast.py
"""

import math

import oanim
oanim.data.document.path_show_all = True  # these tests look at several paths at once

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def build(knob_on_hair=False):
    ops.wm.read_homefile()
    oanim.data.document.path_show_all = True
    doc.auto_key = True
    ops.layer.new_bone()
    rig_id = layers.active.id
    rig = lambda: next(l for l in layers.all() if l.id == rig_id)
    bone = lambda n: next(b for b in rig().bones if b["name"] == n)
    # A hair swinging with dynamics: the rig has dynamics.
    ops.armature.bone_add(name="Hair", head_x="-3.0", head_y="0.0", tail_x="-3.0", tail_y="2.0")
    ops.armature.select_none()
    ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0",
                          parent="Hair" if knob_on_hair else "")
    ops.armature.select_none()
    ops.armature.bone_add(name="Ear", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
    ops.armature.select_none()
    assert ops.anim.action_new(name="Knob Right") == {'FINISHED'}
    doc.frame_current = 24
    p = bone("Ear")["position"]
    rig().bone_set("Ear", position=(p[0] - 0.6, p[1] - 0.2))
    doc.frame_current = 25
    ops.anim.action_set(name="")
    doc.frame_current = 0
    rig().select_bone("Knob")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action="Knob Right") == {'FINISHED'}
    if knob_on_hair:
        # Played where it is posed: where the hair, swinging, takes it.
        assert ops.armature.bone_relations_set(bone="Knob", knob_independent="1") == {'FINISHED'}
    for f, knob in ((6, (2.0, 0.0)), (30, (24.0, 0.0))):
        doc.frame_current = f
        rig().bone_set("Knob", knob=knob)
        doc.frame_current += 1
        doc.frame_current -= 1
    ops.armature.select_none()
    rig().select_bone("Hair")
    for f, turn in ((0, 0.0), (8, 1.2), (14, -0.4)):
        doc.frame_current = f
        rig().bone_set("Hair", angle=math.pi / 2 + turn)
        doc.frame_current += 1
        doc.frame_current -= 1
    assert ops.armature.constraint_add(type="DYNAMICS", bone="Hair") == {'FINISHED'}
    doc.auto_key = False
    doc.motion_paths = True
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    layers.active = rig()
    ops.armature.select_none()
    rig().select_bone("Ear")
    doc.frame_current = 18
    return rig_id, rig


def on_path(knob_on_hair, shortcuts):
    """The Ear's keys once On Path (frame, value, path_offset), and the places' counts."""
    rig_id, rig = build(knob_on_hair)
    wm.motion_path_own_from_keys(shortcuts)
    wm.motion_path_places_clear()
    assert ops.anim.motion_path_on_path(on="1", bone="Ear", head="1", layer=str(rig_id)) == {'FINISHED'}
    counts = wm.motion_path_places()
    wm.motion_path_own_from_keys(True)
    keys = [(k["frame"], tuple(k["value"]), tuple(k["path_offset"])) for k in rig().keyframes('bones["Ear"].position')]
    return keys, counts


def worst(a, b):
    assert [k[0] for k in a] == [k[0] for k in b], (a, b)
    return max(max(math.dist(x[1], y[1]), math.dist(x[2], y[2])) for x, y in zip(a, b))


# The knob plays from its own values: side by side, values only, as working everything out has it.
fast, counts = on_path(False, True)
full, full_counts = on_path(False, False)
assert [k[0] for k in fast] == [0, 6, 30], fast
assert counts["frames"] == 31 and counts["threads"] >= 2, ("side by side", counts)
assert full_counts["threads"] <= 1, ("in full, one at a time with dynamics", full_counts)
assert worst(fast, full) < 1e-5, ("the same keys", fast, full)
assert max(math.dist(k[2], (0.0, 0.0)) for k in fast) > 0.1, ("the action adds something", fast)

# A knob played where it is posed, hanging from the swinging hair: in full, one frame at a time, so the same.
fast, counts = on_path(True, True)
full, _ = on_path(True, False)
assert counts["threads"] <= 1, ("dynamics can move the knob: one at a time", counts)
assert worst(fast, full) < 1e-5, ("the same keys", fast, full)


def drawn(knob_on_hair, shortcuts):
    """The Ear's head path as drawn once On Path, Own Motion (worked out afresh), and the places' counts."""
    rig_id, rig = build(knob_on_hair)
    assert ops.anim.motion_path_on_path(on="1", bone="Ear", head="1", layer=str(rig_id)) == {'FINISHED'}
    doc.frame_current = 18
    wm.motion_path_own_from_keys(shortcuts)
    wm.motion_path_places_clear()
    path = next(p for p in wm.motion_paths() if p["head"])
    counts = wm.motion_path_places()
    wm.motion_path_own_from_keys(True)
    return path["points"], counts


def furthest(a, b):
    assert len(a) == len(b), (len(a), len(b))
    return max(math.dist(x, y) for x, y in zip(a, b))


# Its path drawn the same way: side by side, values only, as working everything out has it.
fast, counts = drawn(False, True)
full, full_counts = drawn(False, False)
assert counts["threads"] >= 2, ("the path side by side", counts)
assert full_counts["threads"] <= 1, ("in full, one at a time with dynamics", full_counts)
assert furthest(fast, full) < 1e-5, ("the same path", furthest(fast, full))
assert max(math.dist(p, fast[0]) for p in fast) > 0.1, ("the path moves", fast)

# Hanging from the swinging hair: in full, one frame at a time.
fast, counts = drawn(True, True)
full, _ = drawn(True, False)
assert counts["threads"] <= 1, ("dynamics can move the knob: one at a time", counts)
assert furthest(fast, full) < 1e-5, ("the same path", furthest(fast, full))

def build_self():
    """A bone whose turn plays an action moving the bone itself (as a head turn's bone), dynamics elsewhere."""
    ops.wm.read_homefile()
    oanim.data.document.path_show_all = True
    doc.auto_key = True
    ops.layer.new_bone()
    rig_id = layers.active.id
    rig = lambda: next(l for l in layers.all() if l.id == rig_id)
    ops.armature.bone_add(name="Hair", head_x="-3.0", head_y="0.0", tail_x="-3.0", tail_y="2.0")
    ops.armature.select_none()
    ops.armature.bone_add(name="Turn", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
    ops.armature.select_none()
    rig().select_bone("Turn")
    assert ops.armature.bone_turn_action_new(direction="CCW") == {'FINISHED'} and doc.action == "Turn"
    p = next(b for b in rig().bones if b["name"] == "Turn")["position"]
    rig().bone_set("Turn", position=(p[0] + 0.8, p[1] - 0.5))
    doc.frame_current = 11
    ops.anim.action_set(name="", layer=str(rig_id))
    for f, turn in ((0, 0.0), (6, 0.4), (20, 1.4), (30, 0.2)):
        doc.frame_current = f
        rig().bone_set("Turn", angle=turn)
        doc.frame_current += 1
        doc.frame_current -= 1
    ops.armature.select_none()
    rig().select_bone("Hair")
    for f, turn in ((0, 0.0), (8, 1.2), (14, -0.4)):
        doc.frame_current = f
        rig().bone_set("Hair", angle=math.pi / 2 + turn)
        doc.frame_current += 1
        doc.frame_current -= 1
    assert ops.armature.constraint_add(type="DYNAMICS", bone="Hair") == {'FINISHED'}
    doc.auto_key = False
    doc.motion_paths = True
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    layers.active = rig()
    ops.armature.select_none()
    rig().select_bone("Turn")
    doc.frame_current = 18
    return rig_id, rig


def on_path_self(shortcuts):
    """The Turn bone's position keys once On Path, its path as drawn then, and the places' counts of each."""
    rig_id, rig = build_self()
    wm.motion_path_own_from_keys(shortcuts)
    wm.motion_path_places_clear()
    assert ops.anim.motion_path_on_path(on="1", bone="Turn", head="1", layer=str(rig_id)) == {'FINISHED'}
    counts = wm.motion_path_places()
    keys = [(k["frame"], tuple(k["value"]), tuple(k["path_offset"])) for k in rig().keyframes('bones["Turn"].position')]
    wm.motion_path_places_clear()
    path = next(p for p in wm.motion_paths() if p["head"])["points"]
    path_counts = wm.motion_path_places()
    wm.motion_path_own_from_keys(True)
    return keys, counts, path, path_counts


# Its action played from its own turn: its own values have nothing posing bones in them, so side by side, values only,
# as working everything out has it.
fast, counts, fast_path, path_counts = on_path_self(True)
full, full_counts, full_path, _ = on_path_self(False)
assert counts["threads"] >= 2 and path_counts["threads"] >= 2, ("side by side", counts, path_counts)
assert full_counts["threads"] <= 1, ("in full, one at a time with dynamics", full_counts)
assert worst(fast, full) < 1e-5, ("the same keys", fast, full)
assert max(math.dist(k[2], (0.0, 0.0)) for k in fast) > 0.1, ("its action moves it", fast)
assert furthest(fast_path, full_path) < 1e-5, ("the same path", furthest(fast_path, full_path))

# Keys picked with no keys of its own yet: their handles are what On Path would give, worked out on a copy. Keys made
# on the copy are no change to the document, else what is kept until keys change (the paths, the handles) was worked
# out again on every redraw, freezing the app with every bone picked.
build(False)
ops.anim.keys_select_all()
wm.motion_path_places_clear()
first = next(p for p in wm.motion_paths(True) if p["head"])
made = wm.motion_path_places()["frames"]
assert first["handles"], ("the knob's keys' handles show", first)
wm.motion_path_places_clear()
again = next(p for p in wm.motion_paths(True) if p["head"])
# (The handles' copies are worked out each time; the path's frames, kept, are not.)
assert wm.motion_path_places()["frames"] < made, ("kept: the path not worked out again", made, wm.motion_path_places())
assert again["handles"] == first["handles"], (again["handles"], first["handles"])

# A frame change doesn't change the keys On Path would give it: kept, only placed again, as working them out afresh.
assert ops.screen.frame_offset_forward() == {'FINISHED'} and doc.frame_current == 19
wm.motion_path_places_clear()
stepped = next(p for p in wm.motion_paths(True) if p["head"])
assert wm.motion_path_places()["frames"] == 0, ("the keys On Path gives kept", wm.motion_path_places())
fresh = next(p for p in wm.motion_paths() if p["head"])
assert stepped["handles"] == fresh["handles"], (stepped["handles"], fresh["handles"])

# An edit (the knob's key moved further) changes them: worked out again, never the kept ones.
rig = next(l for l in layers.all() if l.bones and any(b["name"] == "Knob" for b in l.bones))
doc.auto_key = True
ops.armature.select_none()
rig.select_bone("Knob")
doc.frame_current = 6
rig.bone_set("Knob", knob=(16.0, 0.0))
doc.frame_current = 18
doc.auto_key = False
ops.armature.select_none()
rig.select_bone("Ear")
ops.anim.keys_select_all()
edited = next(p for p in wm.motion_paths(True) if p["head"])
fresh = next(p for p in wm.motion_paths() if p["head"])
assert edited["handles"] == fresh["handles"], (edited["handles"], fresh["handles"])
assert edited["handles"] != stepped["handles"], ("the edit changes them", edited["handles"])

print("test_motion_path_on_path_fast: ok")
