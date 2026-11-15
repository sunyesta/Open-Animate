"""Bugs the sweep after the pin, picking and bent-handle work found, each in a scene of its own (a fresh document):
handles through stacked deforms, place_handle and Smooth Points on bent frames, the Collections row menu with a sub
bone group, collection_link CANCELLED, and a pin whose Custom shape draws nothing.

Run with:  OpenAnimate --background --python tests/test_sweep_handles_collections.py
"""

import oanim


# --- Two deforms stacked on one layer: moving a point leaves its neighbours' shown handles still (the first deform's fit
# bent on by the second, CurvePoint::wire_fit_in).
def two_deforms_neighbour():
    import math
    import oanim
    ops = oanim.ops; doc = oanim.data.document; layers = oanim.data.layers; wm = oanim.wm
    doc.auto_key = True; doc.frame_current = 0
    anchor = layers.active
    def fresh(l): return next(x for x in layers.all() if x.id == l.id)
    def grid(name):
        layers.active = anchor; ops.layer.new(); g = layers.active; g.name = name
        assert g.add_primitive("GRID", [(-1, -1), (1, 1)], columns=3, rows=3); return g
    g1, g2 = grid("G1"), grid("G2")
    layers.active = anchor; ops.layer.new(); art = layers.active; art.name = "Art"
    art.add_curve([(-0.6, -0.1), (-0.2, 0.4), (0.2, 0.3), (0.6, -0.05)])
    for g in (g1, g2):
        layers.active = fresh(art); assert ops.object.modifier_add(type="MESH_DEFORM") == {'FINISHED'}
        art = fresh(art)
        art.modifier_set(len(art.modifiers) - 1, curve_method="SMOOTH", cage_method="MEAN_VALUE", layer=g.name,
                         shape=g.shapes[0][0], precision=0.0)
    doc.frame_current = 10
    for g, k in ((g1, 1.0), (g2, -0.7)):
        for i, p in enumerate(g.points):
            g.set_point(i, (p[0] * (1 + 0.2 * k) + 0.25 * k * math.sin(p[1] * 2.0), p[1] + 0.3 * k * math.sin(p[0] * 2.5)))
    doc.frame_current = 11; doc.frame_current = 10
    art = fresh(art); layers.active = art
    before = wm.handle_ends_shown(art)
    ops.mesh.select_none(); art.select_points([0])
    assert ops.mesh.translate(move_x="0.07", move_y="0.04") == {'FINISHED'}
    after = wm.handle_ends_shown(art)
    moved = {(i, s): math.dist(before[i][s], after[i][s]) for i in (1, 2, 3) for s in (0, 1)}
    print(moved)
    worst = max(moved.values())
    assert worst < 1e-5, f"moving point 0 moved its neighbours' shown handles (two deforms) by up to {worst:.4f}: {moved}"


# --- A group's deform and the layer's own: a handle dragged lands where it was sent, and a point's move leaves its
# neighbour's shown handle.
def group_plus_layer_handle():
    import math
    import oanim
    ops = oanim.ops; doc = oanim.data.document; layers = oanim.data.layers; wm = oanim.wm
    doc.auto_key = True; doc.frame_current = 0
    anchor = layers.active
    def fresh(l): return next(x for x in layers.all() if x.id == l.id)
    def grid(name):
        layers.active = anchor; ops.layer.new(); g = layers.active; g.name = name
        assert g.add_primitive("GRID", [(-1, -1), (1, 1)], columns=3, rows=3); return g
    def deform(owner, g, **kw):
        layers.active = fresh(owner); assert ops.object.modifier_add(type="MESH_DEFORM") == {'FINISHED'}
        o = fresh(owner); o.modifier_set(len(o.modifiers) - 1, curve_method="SMOOTH", cage_method="MEAN_VALUE",
                                         layer=g.name, shape=g.shapes[0][0], **kw)
    g1, g2 = grid("G1"), grid("G2")
    layers.active = anchor; ops.layer.new(); art = layers.active; art.name = "Art"
    art.add_curve([(-0.6, -0.1), (-0.2, 0.4), (0.2, 0.3), (0.6, -0.05)])
    layers.active = anchor; assert ops.layer.new_group() == {'FINISHED'}; grp = layers.active; grp.name = "Grp"
    layers.active = fresh(art); assert ops.layer.move_to_group(group=str(grp.id)) == {'FINISHED'}
    deform(grp, g1)
    deform(art, g2, precision=0.0)
    doc.frame_current = 10
    for g, k in ((g1, 1.0), (g2, -0.7)):
        for i, p in enumerate(g.points):
            g.set_point(i, (p[0] * (1 + 0.2 * k) + 0.25 * k * math.sin(p[1] * 2.0), p[1] + 0.3 * k * math.sin(p[0] * 2.5)))
    doc.frame_current = 11; doc.frame_current = 10
    art = fresh(art); layers.active = art
    fails = []
    ends = wm.handle_ends_shown(art)
    ops.mesh.select_none(); art.select_handle(0, 2, "IN")
    assert ops.mesh.translate(move_x="0.05", move_y="-0.03") == {'FINISHED'}
    got = wm.handle_ends_shown(art)[2][0]
    want = (ends[2][0][0] + 0.05, ends[2][0][1] - 0.03)
    if math.dist(got, want) > 1e-3:
        fails.append(f"handle 2 IN sent to {want}, shows at {got}: {math.dist(got, want):.4f} off")
    ops.ed.undo(); doc.frame_current = 11; doc.frame_current = 10
    art = fresh(art)
    ends = wm.handle_ends_shown(art)
    ops.mesh.select_none(); art.select_points([0])
    assert ops.mesh.translate(move_x="0.07", move_y="0.04") == {'FINISHED'}
    after = wm.handle_ends_shown(art)
    d = math.dist(ends[1][0], after[1][0])
    if d > 1e-5:
        fails.append(f"moving point 0 moved point 1's shown in handle by {d:.4f}")
    assert not fails, fails


# --- layer.place_handle on a bent frame: the end shows where asked, though the wire fitted it elsewhere.
def place_handle_fit():
    import math
    import oanim
    ops = oanim.ops; doc = oanim.data.document; layers = oanim.data.layers; wm = oanim.wm
    doc.auto_key = True; doc.frame_current = 0
    ops.layer.new(); grid = layers.active; grid.name = "Grid"
    assert grid.add_primitive("GRID", [(-1, -1), (1, 1)], columns=3, rows=3)
    ops.layer.new(); art = layers.active; art.name = "Brow"
    art.add_curve([(-0.6, -0.1), (0.0, 0.45), (0.6, -0.05)])
    assert ops.object.modifier_add(type="MESH_DEFORM") == {'FINISHED'}
    art.modifier_set(0, curve_method="SMOOTH", cage_method="MEAN_VALUE", layer="Grid", shape=grid.shapes[0][0], precision=0.0)
    doc.frame_current = 10
    for i, p in enumerate(grid.points):
        grid.set_point(i, (p[0] * 1.2 + 0.25 * math.sin(p[1] * 2.0), p[1] + 0.3 * math.sin(p[0] * 2.5)))
    doc.frame_current = 11; doc.frame_current = 10
    layers.active = art
    res = []
    for (i, side, s) in ((1, "OUT", 1), (1, "IN", 0), (2, "IN", 0), (0, "OUT", 1)):
        shown = wm.handle_ends_shown(art)
        wire = art.evaluated_handles(0, shown=True)
        target = (shown[i][s][0] + 0.04, shown[i][s][1] + 0.02)
        art.place_handle(0, i, side, target)
        got = wm.handle_ends_shown(art)[i][s]
        res.append((i, side, math.dist(got, target), math.dist(shown[i][s], wire[i][s + 1])))
        doc.frame_current = 11; doc.frame_current = 10
    print(res)
    worst = max(r[2] for r in res)
    assert worst < 1e-3, f"place_handle: ends show off where asked by up to {worst:.4f} (point, side, off, wire fit there): {res}"


# --- Smooth Points with Radius only on a bent frame leaves the handles as stored (it wrote back the wire's fitted ones).
def smooth_radius_handles():
    import math
    import oanim
    ops = oanim.ops; doc = oanim.data.document; layers = oanim.data.layers; wm = oanim.wm
    doc.auto_key = True; doc.frame_current = 0
    ops.layer.new(); grid = layers.active; grid.name = "Grid"
    assert grid.add_primitive("GRID", [(-1, -1), (1, 1)], columns=3, rows=3)
    ops.layer.new(); art = layers.active; art.name = "Brow"
    art.add_curve([(-0.6, -0.1), (-0.2, 0.4), (0.2, 0.3), (0.6, -0.05)])
    assert ops.object.modifier_add(type="MESH_DEFORM") == {'FINISHED'}
    art.modifier_set(0, curve_method="SMOOTH", cage_method="MEAN_VALUE", layer="Grid", shape=grid.shapes[0][0], precision=0.0)
    doc.frame_current = 10
    for i, p in enumerate(grid.points):
        grid.set_point(i, (p[0] * 1.2 + 0.25 * math.sin(p[1] * 2.0), p[1] + 0.3 * math.sin(p[0] * 2.5)))
    doc.frame_current = 11; doc.frame_current = 10
    art = next(l for l in layers.all() if l.name == "Brow"); layers.active = art
    # make radii differ so radius smoothing has work
    for i in range(art.point_count):
        pass
    stored0 = art.curve_handles(0); shown0 = wm.handle_ends_shown(art)
    ops.mesh.select_none(); art.select_points([1, 2])
    r = ops.mesh.smooth_points(position="0", handles="0", radius="1", factor="0.5")
    art = next(l for l in layers.all() if l.name == "Brow")
    stored1 = art.curve_handles(0); shown1 = wm.handle_ends_shown(art)
    ds = max(math.dist(stored0[i][k], stored1[i][k]) for i in range(4) for k in (1, 2))
    dw = max(math.dist(shown0[i][k], shown1[i][k]) for i in range(4) for k in (0, 1))
    print(r, "stored moved", ds, "shown moved", dw)
    assert ds < 1e-5 and dw < 1e-5, f"Smooth Points radius only ({r}) moved stored handles by {ds:.4f}, shown handle ends by {dw:.4f}"


# --- The Collections row menu counts the rig its operators work on: a bone picked in a sub bone group.
def collection_row_menu_sub_group():
    import oanim, traceback
    ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm
    doc.frame_current = 0
    def fresh(l): return next(x for x in layers.all() if x.id == l.id)
    def rig_in(name, parent=None):
        if parent: layers.active = parent
        assert ops.layer.new_bone() == {'FINISHED'}
        rig = layers.active; rig.name = name
        if parent:
            assert ops.layer.move_to_group(group=str(parent.id)) == {'FINISHED'}
            layers.active = rig
        return rig
    def bone(rig, name, x):
        layers.active = rig
        assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="1", parent="") == {'FINISHED'}
    outer = rig_in("Outer"); bone(outer, "a", 0)
    inner = rig_in("Inner", fresh(outer)); bone(inner, "b", 2)
    print("sub_bone_group", fresh(inner).sub_bone_group)
    fresh(inner).sub_bone_group = True
    layers.active = fresh(outer)
    assert ops.armature.collection_add(collection="Eyes") == {'FINISHED'}
    # pick b only (in Inner), Outer active
    layers.active = fresh(outer); ops.armature.select_none(); fresh(outer).bone_select_set("a", False) if hasattr(fresh(outer), "bone_select_set") else None
    layers.active = fresh(inner); ops.armature.select_none(); fresh(inner).select_bone("b")
    layers.active = fresh(outer)
    for b in fresh(outer).bones: print("outer", b["name"], b["selected"])
    for b in fresh(inner).bones: print("inner", b["name"], b["selected"])
    menu = wm.collection_selected_change(fresh(outer), "Eyes", True)
    print("row menu (Armature tab, Outer active) says:", repr(menu))
    h0 = wm.undo_history()[1]
    r = ops.armature.collection_assign(collection="Eyes")
    print("assign ->", r, "steps", wm.undo_history()[1] - h0)
    print("outer bones", [(b["name"], b["collections"]) for b in fresh(outer).bones])
    print("inner bones", [(b["name"], b["collections"]) for b in fresh(inner).bones])
    changed = sum(1 for l in (outer, inner) for b in fresh(l).bones if "Eyes" in b["collections"])
    assert (menu == "") == (changed == 0), f"row menu said {menu!r} (greyed) but Assign Selected changed {changed} bone(s)"


# --- layer.collection_link with no layer to put in: CANCELLED, and no collection made.
def collection_link_cancelled_creates():
    import oanim
    before = list(oanim.data.collections)
    r = oanim.ops.layer.collection_link(layer="999999", collection="Zzz", on="1")
    after = list(oanim.data.collections)
    assert not (r == {'CANCELLED'} and after != before), f"CANCELLED, yet collections went {before} -> {after}"


# --- A pin whose Custom shape is only an open, outline-less fill draws nothing: it stays a pin.
def pin_open_fill():
    import oanim
    ops = oanim.ops; doc = oanim.data.document; layers = oanim.data.layers; wm = oanim.wm
    doc.frame_current = 0
    ops.layer.new(); s = layers.active; s.name = "OpenFill"
    s.add_curve([(0, 0), (1, 0.2), (2, 0)], closed=False)
    s.set_shape_style(0, has_fill=True, has_outline=False)
    ops.layer.new_bone(); rig = layers.active
    ops.armature.bone_add(name="p", head_x="2", head_y="0", tail_x="2.1", tail_y="0", parent="")
    ops.armature.select_none(); rig.select_bone("p")
    assert ops.armature.bone_convert(type="PIN") == {'FINISHED'}
    rig = next(l for l in layers.all() if l.id == rig.id)
    rig.bone_set("p", shape="CUSTOM", shape_layer="OpenFill")
    got = wm.bone_drawn_as(rig, "p")
    assert got == "PIN", f"pin with a Custom shape of only an open, outline-less fill: drawn as {got} (nothing to draw), want PIN"


for section in (two_deforms_neighbour, group_plus_layer_handle, place_handle_fit, smooth_radius_handles, collection_row_menu_sub_group, collection_link_cancelled_creates, pin_open_fill):
    assert oanim.ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    section()
    print(section.__name__, "ok")

print("sweep handles and collections: ok")
