"""A Cage Deform whose cage is a reference that shows through a Resample: what it bends is what its original would bend.
A Match Original reference shows its original's Resample, and the cage was bent by that resampled outline but read at
rest without it, each segment's control points matched against another's: with Blended the creases inside collapsed
to a speck at the leg's edge (a pants leg's details in the clay file once its front became a reference of its back).
A reference's own Resample was left out of its rest the same way.

Run with:  OpenAnimate --background --python tests/test_cage_reference_resample.py
"""

import math

import oanim

ops = oanim.ops

# A pants leg's back, its corner point 2 pulled up on frame 10.
REST = [(0.078526, -0.473149), (0.093325, -0.542029), (0.004325, -0.562576), (0.002528, -0.494025)]
POSE_2 = (0.007282, -0.527301)
CREASES = [(0.03, -0.50), (0.05, -0.52), (0.07, -0.51), (0.04, -0.545)]
METHODS = ("STANDARD", "SEAMLESS", "BLENDED")


def find(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def drawing(name, points, closed):
    ops.layer.new()
    oanim.data.layers.active.name = name
    oanim.data.layers.active.add_curve(points, closed=closed, fill=closed)
    return oanim.data.layers.active


def resample(layer):
    oanim.data.layers.active = layer
    assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
    layer.modifier_set(len(layer.modifiers) - 1, split="COUNT", pieces=4)


def creases(name, cage):
    layer = drawing(name, CREASES, False)
    assert ops.object.modifier_add(type="CAGE_DEFORM") == {'FINISHED'}
    layer.modifier_set(len(layer.modifiers) - 1, layer=cage.name, shape=cage.shapes[0][0], cage_method="ENVELOPE")
    return layer


def scene(match):
    """The back with a Resample; a reference of it as the front (Match Original, or its own Resample); creases bent by
    each. The back posed on frame 10."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    back = drawing("Back", REST, True)
    resample(back)
    assert ops.layer.make_reference() == {'FINISHED'}
    front = oanim.data.layers.active
    front.name = "Front"
    if not match:
        assert ops.layer.reference_set(match_original="0") == {'FINISHED'}
        resample(front)
    by_front, by_back = creases("ByFront", front), creases("ByBack", back)
    doc.auto_key = True
    doc.frame_current = 10
    oanim.data.layers.active = back
    back.set_point(2, POSE_2)
    doc.frame_current = 11
    doc.frame_current = 10
    return front, back, by_front, by_back


def compare(match):
    front, back, by_front, by_back = scene(match)
    assert len(front.evaluated()[0]) == len(back.evaluated()[0]) == 16, "both show the Resample's points"
    for method in METHODS:
        for layer in (by_front, by_back):
            layer.modifier_set(0, envelope_method=method)
        a, b = by_front.evaluated()[0], by_back.evaluated()[0]
        off = max(math.dist(p, q) for p, q in zip(a, b))
        assert off < 1e-4, ("bent by the reference as by its original", match, method, off)
        spread = max(math.dist(p, q) for p in a for q in a)
        assert spread > 0.03, ("the creases keep their size", match, method, spread)


# --- A Match Original reference shows its original's Resample: it bends as the original does ---------------------------
compare(True)

# --- A reference with a Resample of its own ----------------------------------------------------------------------------
compare(False)

print("cage reference resample: ok")
