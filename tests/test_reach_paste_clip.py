"""Timeline and media fixes from a sweep. A mask's Reach keys count as a change: undo and Move Keys compared the cards
without them, so moving a lone Reach key was CANCELLED with the key moved and deleting one pushed no undo step. Paste
Keys on frame 0 pressed a second time changes nothing: the keys after the setup one were taken as changes from the
setup now, not the one they were copied from, so the second press moved them by the setup's change (frame 3 showed 2.5
for 1.5). A clip's In point given nan or inf stays as it was (it was stored, and saved as null).

Run with:  OpenAnimate --background --python tests/test_reach_paste_clip.py
"""

import math
import os

import oanim

ops, doc, L, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm
REACH = "masks[0].reach"
MEDIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "media")


def square(name, x0, y0, x1, y1):
    ops.layer.new()
    l = L.active
    l.name = name
    l.add_curve([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True, fill=True)
    return l


def reach_scene():
    """A layer masked by another, its Reach keyed on frame 10 alone (frame 0 its setup); that key selected."""
    global doc
    assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    doc = oanim.data.document
    art = square("art", -3.0, -3.0, 3.0, 3.0)
    square("head", -1.0, -1.0, 1.0, 1.0)
    L.active = art
    # Key Whole Drawing and Key Together off, so the Reach key is all that moves.
    assert ops.anim.key_together_set(layer=str(art.id), drawing="1", on="0") == {"FINISHED"}
    assert ops.anim.key_together_set(layer=str(art.id), on="0") == {"FINISHED"}
    assert ops.mask.add(sources="head", mode="SUBTRACT") == {'FINISHED'}
    assert ops.mask.set(index="0", end_lines="1") == {'FINISHED'}
    assert ops.anim.keyframe_toggle(layer=str(art.id), paths=REACH) == {'FINISHED'}
    doc.frame_current = 10
    assert ops.mask.set(layer=str(art.id), index="0", reach="1") == {'FINISHED'}
    for l in L.all():
        l.selected = l.id == art.id
    assert ops.anim.keys_select(frame_start="10", frame_end="10", layers=str(art.id), path=REACH) == {'FINISHED'}
    doc.frame_current = 0
    return art


# --- Move Keys on a lone Reach key: FINISHED, one undo step, and undo puts it back -------------------------------------
art = reach_scene()
steps = wm.undo_history()[1]
assert ops.anim.keys_offset(frames="5") == {'FINISHED'}, "the Reach key moved"
assert [k['frame'] for k in art.keyframes(REACH)] == [0, 15]
assert wm.undo_history()[1] == steps + 1, "one undo step"
assert ops.ed.undo() == {'FINISHED'}
assert [k['frame'] for k in L.active.keyframes(REACH)] == [0, 10], "undone"

# --- Delete Keys on a lone Reach key: one undo step, which brings it back ---------------------------------------------
art = reach_scene()
steps = wm.undo_history()[1]
assert ops.anim.keys_delete() == {'FINISHED'}
assert 10 not in [k['frame'] for k in art.keyframes(REACH)]
assert wm.undo_history()[1] == steps + 1, "one undo step"
assert ops.ed.undo() == {'FINISHED'}
assert 10 in [k['frame'] for k in L.active.keyframes(REACH)], "undone, the key and not the step before"

# --- Paste Keys on frame 0 twice: the second press changes nothing -----------------------------------------------------
assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
doc = oanim.data.document
doc.auto_freeze_keys = False
doc.auto_key = True
doc.frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
rig = L.active
assert ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0") == {'FINISHED'}
setup = next(b for b in rig.bones if b["name"] == "arm")["setup_angle"]


def pose(f):
    doc.frame_current = f + 1
    doc.frame_current = f
    b = next(b for b in rig.bones if b["name"] == "arm")
    return round(b["angle"] - setup, 4), tuple(round(v, 4) for v in b["position"])


for f, a, at in ((1, 1.0, (0.2, 0.1)), (4, 1.5, (0.5, -0.3))):
    doc.frame_current = f
    rig.bone_set("arm", angle=setup + a, position=at)
    doc.frame_current = f + 1
copied = {f: pose(f) for f in (1, 4)}
assert ops.anim.keys_select(frame_start="1", frame_end="20") == {'FINISHED'}
assert ops.anim.keys_copy() == {'FINISHED'}
doc.frame_current = 0
assert ops.anim.keys_paste() == {'FINISHED'}
first = {f: pose(f) for f in (0, 3)}
assert first == {0: copied[1], 3: copied[4]}, ("frame 0 as frame 1 was, frame 3 as frame 4 was", first, copied)
doc.frame_current = 0
assert ops.anim.keys_paste() == {'FINISHED'}
second = {f: pose(f) for f in (0, 3)}
assert second == first, ("the same paste again moved the pose", first, second)

# --- A clip's In point given nan or inf: as it was ---------------------------------------------------------------------
assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
assert ops.media.add(filepath=os.path.join(MEDIA, "counting.mp4")) == {'FINISHED'}
video = L.active
cid = video.media_clips[0]["id"]
assert ops.media.clip_set(clip=str(cid), in_point="0.25") == {'FINISHED'}
for v in ("nan", "inf", "-inf"):
    ops.media.clip_set(clip=str(cid), in_point=v)
    clip = next(c for c in L.active.media_clips if c["id"] == cid)
    assert math.isfinite(clip["in_point"]) and abs(clip["in_point"] - 0.25) < 1e-9, (v, clip["in_point"])

print("reach paste clip: ok")
