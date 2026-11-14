"""Collections: named tags the whole document shares, which any bone or layer can carry (several each).
A bone layer's Collections panel (Armature tab) lists the ones it works with, with their eyes and stars:
+ puts one on the panel, - takes it off (its bones stay in it), Delete Collection takes it off
everything, and renaming renames it everywhere. The Bone and Layer tabs' Collections panels put the
active bone or layer in one or take it out (Alt: every selected bone or picked layer too), and M opens
a menu of every collection that toggles the selection in it. Files from before, where each bone layer
had its own, become the document's, the same names merged.

Run with:  OpenAnimate --background --python tests/test_collections.py
"""

import json
import pathlib
import tempfile
import zipfile

import oanim

doc = oanim.data.document
layers = oanim.data.layers
ops = oanim.ops.armature
doc.frame_current = 0


def rig_with(name, bones):
    oanim.ops.layer.new_bone()
    rig = layers.active
    rig.name = name
    for i, b in enumerate(bones):
        ops.bone_add(name=b, head_x=str(i), head_y="0", tail_x=str(i), tail_y="1", parent="")
    return rig


def drawing(name, inside=None, y=2.0):
    oanim.ops.layer.new()
    layer = layers.active
    layer.name = name
    layer.add_curve([(0.0, y), (1.0, y)])
    if inside is not None:
        oanim.ops.layer.move_to_group(group=str(inside.id))
    return layer


def bone(rig, name):
    return next(b for b in rig.bones if b["name"] == name)


def panel(rig):
    return [c["name"] for c in rig.bone_collections]


def unpick_layers(ls=None):
    for l in oanim.data.layers if ls is None else ls:
        l.select = False
        unpick_layers(l.children)


def select_bones(rig, names):
    layers.active = rig
    ops.select_none()
    for i, n in enumerate(names):
        rig.select_bone(n, extend=i > 0)


sky = drawing("sky", None, 5.0)
body = rig_with("body", ["arm", "leg"])
face = rig_with("face", ["jaw", "brow"])
mouth = drawing("mouth", face)
mouth.edit_with_bones = True
assert sky in oanim.data.layers and mouth in face.children
assert oanim.data.collections == []

# --- The Bone tab: the active bone in a collection, made when there is none; its rig's panel gets it -----------
select_bones(face, ["jaw"])
assert ops.bone_collection_link(bone="jaw", collection="Face") == {'FINISHED'}
assert bone(face, "jaw")["collections"] == ["Face"] and oanim.data.collections == ["Face"]
assert panel(face) == ["All", "Face"], "a bone's collection goes on its bone layer's panel"
assert ops.bone_collection_link(bone="jaw", collection="Face") == {'CANCELLED'}, "in it already"
# Alt: every selected bone too.
select_bones(face, ["jaw", "brow"])
assert ops.bone_collection_link(bone="jaw", collection="Brows", all="1") == {'FINISHED'}
assert bone(face, "jaw")["collections"] == ["Face", "Brows"] and bone(face, "brow")["collections"] == ["Brows"]
assert ops.bone_collection_link(bone="jaw", collection="Brows", on="0") == {'FINISHED'}
assert bone(face, "jaw")["collections"] == ["Face"] and bone(face, "brow")["collections"] == ["Brows"]
assert ops.bone_collection_link(bone="brow", collection="Nothing", on="0") == {'CANCELLED'}
assert "Nothing" not in oanim.data.collections, "taking a bone out of no collection makes none"

# --- Shared by the whole document: another rig's bone, a layer outside any rig ------------------------------------
select_bones(body, ["arm"])
assert ops.bone_collection_link(bone="arm", collection="Face") == {'FINISHED'}
assert bone(body, "arm")["collections"] == ["Face"] and oanim.data.collections == ["Face", "Brows"]
assert panel(body) == ["All", "Face"]
layers.active = sky
assert oanim.ops.layer.collection_link(collection="Background") == {'FINISHED'}
assert sky.collections == ["Background"]
assert oanim.ops.layer.collection_link(collection="Face") == {'FINISHED'}
assert sky.collections == ["Background", "Face"], "any layer can be in several"

# Renaming from one panel renames it everywhere.
layers.active = face
assert ops.collection_set(collection="Face", name="Head") == {'FINISHED'}
assert bone(body, "arm")["collections"] == ["Head"] and sky.collections == ["Background", "Head"]
assert panel(body) == ["All", "Head"] and "Face" not in oanim.data.collections
assert ops.collection_set(collection="Head", name="Brows") == {'FINISHED'}
assert bone(face, "jaw")["collections"] == ["Brows.001"], "a name another collection has gets a number"
assert ops.collection_set(collection="Brows.001", name="Head") == {'FINISHED'}

# --- The panel: + puts a collection on it (or a new one), - takes it off; eyes are the panel's own -----------------
layers.active = body
assert ops.collection_add(collection="Background") == {'FINISHED'}
assert panel(body) == ["All", "Background", "Head"] and body.bone_collections[1]["active"], "after the active one"

assert ops.collection_add(collection="Background") == {'CANCELLED'}, "on the panel already"
assert ops.collection_add() == {'FINISHED'} and "Collection" in panel(body), "a new one"
assert ops.collection_remove(collection="Collection") == {'FINISHED'}
assert "Collection" not in panel(body) and "Collection" in oanim.data.collections, "off the panel, not deleted"
assert ops.collection_remove(collection="Background") == {'FINISHED'}
assert sky.collections == ["Background", "Head"], "its layers stay in it"
# Each rig's eye is its own.
assert ops.collection_set(collection="All", visible="0") == {'FINISHED'}
assert ops.collection_set(collection="Head", visible="0") == {'FINISHED'}
assert not body.bone_collections[1]["shown"]
assert next(c for c in face.bone_collections if c["name"] == "Head")["shown"], "the face rig's Head still shows"

# --- The M menu: toggles the selection in a collection ---------------------------------------------------------------
assert ops.collection_set(collection="All", visible="1") == {'FINISHED'}
assert ops.collection_set(collection="Head", visible="1") == {'FINISHED'}
select_bones(face, ["jaw", "brow"])
assert oanim.wm.event_simulate("M", area="Viewport"), "M opens the menu over bones"
assert ops.collection_toggle(collection="Head") == {'FINISHED'}
assert bone(face, "jaw")["collections"] == ["Head"] and "Head" in bone(face, "brow")["collections"]
assert ops.collection_toggle(collection="Head") == {'FINISHED'}, "all of them in it: picked again, it takes them out"
assert "Head" not in bone(face, "jaw")["collections"] and "Head" not in bone(face, "brow")["collections"]
assert ops.collection_toggle(new="1", name="Eyes") == {'FINISHED'}
assert bone(face, "jaw")["collections"] == ["Eyes"] and "Eyes" in panel(face)
# Bones and the drawings edited with them whose points are selected.
ops.select_none()
mouth.select_points([0])
assert ops.collection_toggle(collection="Eyes") == {'FINISHED'}
assert mouth.collections == ["Eyes"] and bone(face, "brow")["collections"] == ["Brows", "Eyes"]
oanim.ops.mesh.select_none()
# The Layers editor's: the picked layers.
unpick_layers()
layers.active = sky
mouth.select = True
assert oanim.wm.event_simulate("M", area="Layers")
assert ops.collection_toggle(collection="Brows", area="LAYERS") == {'FINISHED'}
assert sky.collections == ["Background", "Head", "Brows"] and mouth.collections == ["Eyes", "Brows"]
unpick_layers()
layers.active = sky
assert ops.collection_toggle(collection="Brows", area="LAYERS") == {'FINISHED'}
assert sky.collections == ["Background", "Head"], "only the active one picked now: it leaves"
assert not oanim.wm.event_simulate("M", area="Viewport"), "M in the viewport is for bones"

# Alt on a layer's chips: every picked layer.
mouth.select = True
assert oanim.ops.layer.collection_link(layer=str(sky.id), collection="Sky", all="1") == {'FINISHED'}
assert sky.collections[-1] == "Sky" and mouth.collections[-1] == "Sky"
assert "Sky" in panel(face), "a drawing edited with the bones: its rig's panel gets it"
mouth.select = False

# --- Delete Collection: off every bone, layer and panel; undo brings it back --------------------------------------------
layers.active = face
assert ops.collection_delete(collection="Head") == {'FINISHED'}
assert "Head" not in oanim.data.collections and panel(body) == ["All"], "no row left on any panel"
assert bone(body, "arm")["collections"] == [] and sky.collections == ["Background", "Sky"]
assert oanim.ops.ed.undo() == {'FINISHED'}
assert "Head" in oanim.data.collections and bone(body, "arm")["collections"] == ["Head"]
assert sky.collections == ["Background", "Head", "Sky"]

# --- Copied layers paste with their collections, found again by name -------------------------------------------------
unpick_layers()
layers.active = sky
assert oanim.ops.layer.copy() == {'FINISHED'}
assert ops.collection_delete(collection="Background") == {'FINISHED'}
assert oanim.ops.layer.paste() == {'FINISHED'}
pasted = layers.active
assert pasted.collections == ["Head", "Sky", "Background"] or sorted(pasted.collections) == sorted(
    ["Background", "Head", "Sky"]), pasted.collections
assert "Background" in oanim.data.collections, "a collection the document no longer has is made again"
assert oanim.data.collections.count("Head") == 1, "one of the same name is reused"
unpick_layers()
layers.active = pasted
assert oanim.ops.layer.delete() == {'FINISHED'}
assert any(l.name == "sky" for l in oanim.data.layers)

# --- Saved and opened ----------------------------------------------------------------------------------------------------
folder = pathlib.Path(tempfile.mkdtemp(prefix="oanim_tags_"))
path = str(folder / "tags.oanim")
assert oanim.ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
want = {
    "names": list(oanim.data.collections),
    "arm": bone(body, "arm")["collections"],
    "jaw": bone(face, "jaw")["collections"],
    "sky": list(sky.collections),
    "mouth": list(mouth.collections),
    "face": panel(face),
    "body": panel(body),
}
assert oanim.ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}


def found():
    body = next(l for l in oanim.data.layers if l.name == "body")
    face = next(l for l in oanim.data.layers if l.name == "face")
    sky = next(l for l in oanim.data.layers if l.name == "sky")
    mouth = next(l for l in face.children if l.name == "mouth")
    return body, face, sky, mouth


body, face, sky, mouth = found()
assert {
    "names": list(oanim.data.collections),
    "arm": bone(body, "arm")["collections"],
    "jaw": bone(face, "jaw")["collections"],
    "sky": list(sky.collections),
    "mouth": list(mouth.collections),
    "face": panel(face),
    "body": panel(body),
} == want

# --- Files from before: each bone layer's own collections, by name, become the document's -------------------------------
with zipfile.ZipFile(path) as z:
    data = json.loads(z.read("document.json"))
names = {c["id"]: c["name"] for c in data["document"].pop("collections")}
data["document"].pop("next_collection_id", None)


def old_rig(rig_json):
    """Its panel as each bone layer had it: its own ids (counted from 1), named."""
    own = {}
    for i, c in enumerate(rig_json.get("bone_collections", [])):
        own[c["id"]] = 10 + i  # ids of its own, unlike the document's
        c["name"] = names[c["id"]]
        c["id"] = own[c["id"]]
    rig_json["active_collection"] = own.get(rig_json.get("active_collection", 0), 0)
    for b in rig_json.get("bones", []):
        b["collections"] = [own[i] for i in b.get("collections", []) if i in own]

    def inside(children):
        for l in children:
            if "collections" in l:
                l["collections"] = [own[i] for i in l["collections"] if i in own]
            if l.get("type") != rig_json.get("type"):
                inside(l.get("children", []))

    inside(rig_json.get("children", []))


for l in data["document"]["layers"]:
    if "bone_collections" in l:
        old_rig(l)
    elif "collections" in l:
        l.pop("collections")  # outside any bone layer there were none
old = str(folder / "old.oanim")
with zipfile.ZipFile(old, "w") as z:
    z.writestr("document.json", json.dumps(data))
assert oanim.ops.wm.open_mainfile(filepath=old, confirmed="1") == {'FINISHED'}
body, face, sky, mouth = found()
assert sorted(oanim.data.collections) == sorted(set(want["face"][1:] + want["body"][1:])), oanim.data.collections
assert panel(face) == want["face"] and panel(body) == want["body"], "each panel as it was"
assert bone(body, "arm")["collections"] == want["arm"] and bone(face, "jaw")["collections"] == want["jaw"]
assert mouth.collections == [c for c in want["mouth"] if c in want["face"]], "a drawing's, in its bone layer's"
shared = [c for c in want["face"][1:] if c in want["body"][1:]]
assert shared and all(oanim.data.collections.count(c) == 1 for c in shared), "the same name: one collection"
assert sky.collections == []

print("Collection tests passed")
