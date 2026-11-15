r"""Rigging fuzzer (from a bug sweep's rigging probe): seeded random rig ops on the sweep file's "Character" bone layer:
Convert To, the Actions panel (frame, mute, loop), actions made, renamed, deleted and moved, controller spots (add,
remove, rename, go, move, corners, order), constraints added and removed, Apply Pose as Rest, controller mirror and
new side actions, turn actions, collections, Symmetrize, bone edits, fixes, frames, entering actions, knobs from
Python and dynamics bakes. Each op is checked as harness.run does (with a fresh undo base and selection left out),
and every 6 ops frame order and save/open.

  set OA_SWEEP_FILE=<sweep>\file.oanim & set OA_SWEEP_TMP=<sweep>\r1 & set RF_SEED=1 & set RF_OPS=60
  <sweep>\bin\OpenAnimate.exe --background --python <skill>\scripts\rigfuzz.py

A failure writes rigfuzz_fail_<seed>.json (the op log) to OA_SWEEP_TMP. The rig is the sweep file's "Character"; set
RF_RIG for another file.
"""
import sys,os,math,random,json,traceback; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import *
import harness
RIG=os.environ.get("RF_RIG","Character")
def LN(n): return [l for l in L.all() if l.name==n][0]
import harness as _h
def run2(name, fn, base=True):
    """run() with a fresh undo base and selection left out of undo/redo comparisons."""
    if base:
        a, f = doc.action, doc.frame_current
        rebase()
        doc.action = a; doc.frame_current = f
    s0, h0, f0, a0 = snap(), active_step(), doc.frame_current, doc.action
    try:
        r = fn()
    except Exception as e:
        bug(name, f"raised {e}"); return None
    s1, h1, f1, a1 = snap(), active_step(), doc.frame_current, doc.action
    bn = bad_numbers(s1)
    if bn: bug(name, f"non-finite {bn[:4]}")
    ch = edits(s0, s1)
    pushed = h1 != h0
    if ch and not pushed: bug(name, f"changed with no undo step r={r} {ch[:3]}")
    if r == {'CANCELLED'} and ch: bug(name, f"CANCELLED but changed {ch[:3]}")
    if pushed:
        for _ in range(h1 - h0): ops.ed.undo()
        doc.frame_current = f0
        d = edits(s0, snap())
        if d: bug(name, f"undo doesn't restore: {d[:4]}")
        for _ in range(h1 - h0): ops.ed.redo()
        doc.frame_current = f1
        d = edits(s1, snap())
        if d: bug(name, f"redo doesn't restore: {d[:4]}")
    print(f"  ok {name} -> {r} changed={bool(ch)} pushed={pushed}", flush=True)
    return r

A=ops.armature; N=ops.anim
SEED=int(os.environ.get("RF_SEED","1")); COUNT=int(os.environ.get("RF_OPS","60"))
rng=random.Random(SEED)
LOG=[]
load()
def rig(): return LN(RIG)
def names(): return [b["name"] for b in rig().bones]
def B(n): return next((b for b in rig().bones if b["name"]==n), None)
def ctls(): return [b["name"] for b in rig().bones if b["type"]=="CONTROLLER_2D"]
def acts(kind=None): return [a["name"] for a in rig().actions if kind is None or a["kind"]==kind]
def pick(ns):
    L.active=rig(); A.select_none()
    for i,n in enumerate(ns): rig().select_bone(n, extend=i>0)
def setup():
    doc.action=""; doc.frame_current=0
def any_frame(): return rng.choice([0,0,1,5,12,24,37,50])
def draw():
    k=rng.choice(["convert","play","play","act_new","act_rename","act_delete","act_move","spot","spot","constraint","constraint_rm",
                  "apply_rest","ctl_mirror","ctl_new","turn_new","turn_mirror","coll","sym","bone_edit","fix","frame","enter","knob_py","dyn"])
    ns=names(); cs=ctls()
    if k=="convert":
        n=rng.choice(ns); t=rng.choice(["REGULAR","PIN","CONTROLLER_2D"]); return (k, dict(bone=n,type=t))
    if k=="play":
        a=rng.choice(acts()); what=rng.choice(["frame","mute","loop"])
        v={"frame":str(rng.choice([0,3,10.5,30,90,200,-5])),"mute":rng.choice(["0","1"]),"loop":rng.choice(["AUTO","ON","OFF"])}[what]
        return (k, dict(name=a, what=what, v=v, f=rng.choice([1,12,24,40])))
    if k=="act_new": return (k, dict(name=rng.choice(["P1","P2","Head_X","P1 2"])))
    if k=="act_rename": return (k, dict(name=rng.choice(acts()), to=rng.choice(["R1","R2 Right","Ear_L","HeadTurn"])))
    if k=="act_delete": return (k, dict(name=rng.choice(acts())))
    if k=="act_move": return (k, dict(name=rng.choice(acts()), d=rng.choice(["UP","DOWN"])))
    if k=="spot":
        if not cs: return None
        c=rng.choice(cs); sp=[s[0] for s in B(c)["controller_spots"]]
        sub=rng.choice(["add","remove","rename","go","goh","move","corners","order"])
        return (k, dict(bone=c, sub=sub, name=rng.choice(sp) if sp else "Spot 1", f=any_frame()))
    if k=="constraint":
        n=rng.choice(ns); t=rng.choice(["LIMIT_ANGLE","COPY_ANGLE","TRACK_TO","IK","MAINTAIN_VOLUME","DYNAMICS","STRETCH_TO"])
        return (k, dict(bone=n, type=t, target=rng.choice(ns)))
    if k=="constraint_rm":
        withc=[n for n in ns if rig().bone_constraints(n)]
        if not withc: return None
        n=rng.choice(withc); m=len(rig().bone_constraints(n))
        return (k, dict(bone=n, index=rng.randrange(m), sub=rng.choice(["rm","move"])))
    if k=="apply_rest": return (k, dict(f=rng.choice([5,12,24]), act=rng.choice(["","","HeadTurn","Head_Turn_L"]), sel=rng.choice([None]+ns)))
    if k=="ctl_mirror":
        if not cs: return None
        return (k, dict(bone=rng.choice(cs), side=rng.choice(["LEFT","RIGHT","UP","DOWN"])))
    if k=="ctl_new":
        if not cs: return None
        return (k, dict(bone=rng.choice(cs), side=rng.choice(["LEFT","RIGHT","UP","DOWN"])))
    if k=="turn_new": return (k, dict(bone=rng.choice(ns), d=rng.choice(["CCW","CW"])))
    if k=="turn_mirror": return (k, dict(bone=rng.choice(ns), d=rng.choice(["CCW","CW"])))
    if k=="coll": return (k, dict(sub=rng.choice(["add","assign","unassign","hide","show"]), bone=rng.choice(ns)))
    if k=="sym": return (k, dict(ab=rng.choice(["0","1"])))
    if k=="bone_edit": return (k, dict(sub=rng.choice(["dup","extrude","subdiv","delete","parent","clear"]), bones=rng.sample(ns, min(2,len(ns)))))
    if k=="fix":
        sub=rng.choice(["new","fade","follow"]); fx=[f["name"] for f in rig().bone_fixes]
        return (k, dict(sub=sub, bones=rng.sample(ns, rng.choice([1,2])), fix=rng.choice(fx) if fx else ""))
    if k=="frame": return (k, dict(f=any_frame()))
    if k=="enter": return (k, dict(a=rng.choice([""]+acts()), f=any_frame()))
    if k=="knob_py":
        if not cs: return None
        return (k, dict(bone=rng.choice(cs), knob=(rng.uniform(-200,200), rng.uniform(-80,80)), f=rng.choice([3,12,30])))
    if k=="dyn": return (k, dict())
def apply(k, a):
    r=rig()
    if k=="convert": setup(); pick([a["bone"]]); return A.bone_convert(type=a["type"])
    if k=="play":
        doc.action=""; doc.frame_current=a["f"]
        return N.action_play_set(layer=str(r.id), name=a["name"], **{a["what"]:a["v"]})
    if k=="act_new": setup(); L.active=r; x=N.action_new(name=a["name"]); return x
    if k=="act_rename": setup(); L.active=r; return N.action_rename(name=a["name"], to=a["to"])
    if k=="act_delete": setup(); L.active=r; return N.action_delete(name=a["name"])
    if k=="act_move": L.active=r; return N.action_move(name=a["name"], direction=a["d"])
    if k=="spot":
        doc.action=""; doc.frame_current=a["f"]; pick([a["bone"]]); s=a["sub"]; n=a["name"]
        if s=="add": return A.controller_spot_add()
        if s=="remove": return A.controller_spot_remove(name=n)
        if s=="rename": return A.controller_spot_rename(name=n, to="Renamed")
        if s=="go": return A.controller_spot_go(name=n)
        if s=="goh": return A.controller_spot_go(name=n, hold="1")
        if s=="move": return A.controller_spot_move(name=n)
        if s=="corners": return A.controller_spots_corners()
        if s=="order": return A.controller_spot_order(name=n, direction="UP")
    if k=="constraint":
        setup(); pick([a["bone"]]); x=A.constraint_add(bone=a["bone"], type=a["type"])
        if False and x=={'FINISHED'} and a["type"] in ("COPY_ANGLE","TRACK_TO","IK","STRETCH_TO"):
            i=len(r.bone_constraints(a["bone"]))-1
            try: r.bone_constraint_set(a["bone"], i, target=a["target"])
            except Exception as e: print("   target refused", e)
        return x
    if k=="constraint_rm":
        setup(); pick([a["bone"]])
        if a["sub"]=="rm": return A.constraint_remove(bone=a["bone"], index=str(a["index"]))
        return A.constraint_move(bone=a["bone"], index=str(a["index"]), direction="1")
    if k=="apply_rest":
        doc.action=a["act"]; doc.frame_current=a["f"]
        if a["sel"]: pick([a["sel"]]); x=A.apply_selected_as_rest()
        else: L.active=r; x=A.apply_pose_as_rest()
        return x
    if k=="ctl_mirror": setup(); pick([a["bone"]]); x=A.controller_mirror(side=a["side"]); return x
    if k=="ctl_new": setup(); pick([a["bone"]]); x=A.controller_action_new(side=a["side"]); return x
    if k=="turn_new": setup(); pick([a["bone"]]); return A.bone_turn_action_new(direction=a["d"])
    if k=="turn_mirror": setup(); pick([a["bone"]]); return A.bone_turn_mirror(direction=a["d"])
    if k=="coll":
        setup(); pick([a["bone"]]); s=a["sub"]
        if s=="add": return A.collection_add(name="FC")
        if s=="assign": return A.collection_assign(collection="FC")
        if s=="unassign": return A.collection_unassign(collection="FC")
        return A.collection_set(collection="FC", visible="0" if s=="hide" else "1")
    if k=="sym": setup(); L.active=r; return A.symmetrize(action_bone_actions=a["ab"])
    if k=="bone_edit":
        setup(); pick(a["bones"] if a["sub"]=="parent" else a["bones"][:1]); s=a["sub"]
        return {"dup":A.duplicate_move,"extrude":A.extrude,"subdiv":A.subdivide,"delete":A.bone_delete,"parent":A.parent_set,"clear":lambda: A.parent_clear(type="CLEAR")}[s]()
    if k=="fix":
        if a["sub"]=="new": doc.action=""; doc.frame_current=12; pick(a["bones"]); return A.bone_fix_new()
        if not a["fix"]: return {'CANCELLED'}
        if a["sub"]=="fade": return A.bone_fix_set(name=a["fix"], fade=rng.choice(["LINEAR","SMOOTH"]))
        return A.bone_fix_follow(name=a["fix"], bones=a["bones"][0], follow="1")
    if k=="dyn": setup(); return A.dynamics_bake()
PY={"frame","enter","knob_py"}
fails=0
for i in range(COUNT):
    try:
        d=draw()
    except Exception as e:
        print("draw fail", e); traceback.print_exc(); continue
    if not d: continue
    k,a=d; LOG.append(d)
    print(f"[{i}] {k} {a}", flush=True)
    if k=="frame": doc.frame_current=a["f"]; continue
    if k=="enter":
        try: doc.action=a["a"]; doc.frame_current=a["f"]
        except Exception as e: print("  enter refused", e)
        continue
    if k=="knob_py":
        doc.action=""; doc.frame_current=a["f"]
        try: rig().bone_set(a["bone"], knob=a["knob"])
        except Exception as e: print("  knob refused", e)
        doc.frame_current=a["f"]+1; doc.frame_current=a["f"]
        continue
    n0=len(harness.FOUND)
    class _D:
        def __getattr__(self, n): return lambda *x, **y: None
    A, N = _D(), _D()
    try: apply(k,a)
    except Exception: pass
    A, N = ops.armature, ops.anim
    run2(f"[{i}] {k} {a}", lambda: apply(k,a))
    if i%6==5:
        order_check(f"[{i}] order after {k}")
        roundtrip(f"[{i}] roundtrip after {k}")
    if len(harness.FOUND)>n0:
        json.dump(LOG, open(os.path.join(TMP, f"rigfuzz_fail_{SEED}.json"),"w"))
        break
summary()
