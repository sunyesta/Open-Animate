---
name: bug-sweep
description: Robust bug testing of an Open Animate file or feature - when the user asks to test robustly, sweep, hunt or find bugs, do random operations on the bones and points, stress-test a file (such as the eye path test file), or fix the bugs a sweep finds, or says "run milestone checks" (a sweep and the mutation checks go together, only on the user's word). Covers probing with background agents on private copies, the seeded random-operations fuzzer and its shrinker, confirming each report, and fixing confirmed bugs while the probes keep running.
---

# Bug sweep

A sweep finds bugs in a file the user cares about, confirms each one, and fixes the confirmed ones, all without
touching the user's open app. Probes run in the background on private copies while you fix what has already come in.

## 1. Set up (a few minutes)

- **Private copy of the file.** Copy the user's file into your scratchpad (`<sweep>/file.oanim`). Probes open the copy;
  nothing is ever saved over it or over the user's file. The user's open app is read-only: never script it.
- **Frozen app.** Copy the build's output folder (`build/bin/RelWithDebInfo/`) to `<sweep>/bin/`. Probes run that copy,
  so you can rebuild the real one while they work. Copy into a new, empty folder: `cp -r` into a `bin/` left from an earlier sweep nests the new build
  in `bin/RelWithDebInfo/` and leaves the old exe on top (check the exe's time before briefing probes). (Without it, a rebuild either fails with LNK1168 while a probe runs
  the app, or changes the app under the probes.)
- **Known list.** Collect what's already been found or fixed (earlier sweeps, the conversation) and known artifacts, so
  probes don't report them again.

## 2. Probe in parallel (background agents)

Launch probes as background `general-purpose` agents, all in one message, with the briefs in
`references/probe-briefs.md`: one per area (bones and rigging; motion paths and timing; timeline, layers, undo and
files) plus one running the random-operations fuzzer. Give each its own output folder. Add an area when the file
invites one (switches, media, masks). Tell the user what's running in a few lines, and that nothing is fixed yet.

The fuzzer (`scripts/fuzz.py`) throws seeded random sequences at the file's bones and points, about 45 kinds of op:
frames, auto-key, undo and redo; bone moves, turns, scales and lengths (Python and G R S, Without Children, Only
Bones), knobs inside and past their box, add/delete/duplicate/extrude/subdivide/parent/convert/clear bones; actions
entered, left and made; points moved, deleted, dissolved, subdivided, split, added, extruded; weights assigned,
removed, automatic, cleaned; Parent Bone with its deform modes; new drawings in the rig; insert/delete keys; Sculpt strokes with every brush (Dyntopo 40% of the time, at Resolution
8-400, Decimate half the time) and Simplify; curvature, width, smooth, slide, merge, mirror, symmetrize, clear handles,
unalign and handle moves; Auto-Freeze Keys on and off (on by default: `OA_FUZZ_FREEZE=0` leaves the file's setting), folding timeline rows (Key Together), Key Whole Drawing, layer move/turn/size/opacity; fix actions that follow bones (`fix_new`, `fix_follow`, `fix_set`,
`fix_mute`, `fix_enter`, `fix_key`, `fix_peek`, `fix_still`, with `check_fixes` after every op), `freeze_check` (an edit between a layer's poses must leave them as they were), and `mpath` (motion paths drawn on a frame: the shortcuts, from keys and kept copies, must match working every frame out on copies, each dot must sit where that frame's pose puts it, and drawing them changes nothing; `OA_FUZZ_MPATH_W` weights it) `mpath_edit` (moves and handle drags on a path, checked against working each frame out afresh), `ref_op` and `ref_check` (references of drawings and groups, each shown where its original is; `OA_FUZZ_X_W` weights the three, `OA_FUZZ_NO_PEEK=1` leaves `fix_peek` out, `OA_FUZZ_SAVE_FAIL=<path>` saves the document as it failed) `mod_op`, `mod_set`, `mask_op` and `switch_op` (modifier stacks: deforms added, moved, duplicated, applied and retargeted; mask cards and steps; switches; `OA_FUZZ_XX_W` weights them, `OA_FUZZ_BADSET=1` adds a refused argument to mask calls) (`freeze_check` skips files with Dynamics bones, whose later frames follow from earlier ones: `OA_FUZZ_FREEZE_DYN=1` checks anyway) (`OA_FUZZ_CANVAS=1` checks after every op that the iPad's canvas, each layer's part kept from the last, is what working it out afresh gives) (`OA_FUZZ_ONLY` limits a run to a list of op names; `OA_FUZZ_SAVE_END=<path>` saves the document at the end, to write a repro from a long log without shrinking). It checks
every op (no exception, finite numbers, a change only with an undo step, CANCELLED changes nothing, entering an action
and leaving changes nothing) and every few ops (undo then redo exact, frames in different orders give the same pose,
save/open exact, a point weighted wholly to one plain bone turns rigidly with it). A watchdog (`OA_FUZZ_HANG`, default
150 s per op) dumps the stacks and exits; the log is written before each op, so a crash or hang still leaves one. A
failure writes the op log; `scripts/shrink.py` cuts it down to the fewest ops that fail the same way (past about 100 ops that takes too long: save the state just before the failing op and write the
repro from there). Run it yourself
too while waiting: a handful of seeds costs little. When a probe adds an op to its own copy, fold it in here.

```
set OA_SWEEP_FILE=<sweep>\file.oanim & set OA_SWEEP_TMP=<sweep>\t1 & set OA_FUZZ_SEED=1 & set OA_FUZZ_OPS=300
<sweep>\bin\OpenAnimate.exe --background --python <skill>\scripts\fuzz.py
python <skill>\scripts\shrink.py <sweep>\bin\OpenAnimate.exe <sweep>\fuzz_fail_1.json
```

For the Path Timing graph and the path's timing, `scripts/fuzz_timing.py` builds its own scene (Linear, Smooth, on 2s
and 3s, a breakdown, Time Together's pair, Key Whole Drawing, a bone) and throws about 30 kinds of op at it: the
graph's points, handles, picks, G R S, V, Decimate and Sculpt; path strokes, slides, spacing; keys added, deleted,
retimed and moved; odd numbers (nan, inf, 1e30) 8% of the time. Besides the fuzzer's checks it holds every stored
curve valid (ends, x increasing, handles pointing the right way, aligned points in line) and a Custom stretch playing
its curve. `OA_FUZZ_SEED`, `OA_FUZZ_OPS`, `OA_FUZZ_OUT`, `OA_FUZZ_REPLAY`; shrink with `python
scripts/shrink_timing.py <exe> <tfuzz_fail_N.json>`. It compares undo states at the frame each step was pushed on and
reopens every 10 ops (the undo stack keeps 64 steps, past which a push looks like none).

For rigs, `scripts/rigfuzz.py` throws seeded rig ops at the file's bone layer (Convert To, the Actions panel, actions
made, renamed, deleted and moved, controller spots, constraints, Apply Pose as Rest, controller sides, turn actions,
collections, Symmetrize, fixes, dynamics): `RF_SEED`, `RF_OPS`, `RF_RIG` (the bone layer's name), with the fuzzer's
`OA_SWEEP_FILE` and `OA_SWEEP_TMP`. It found a fix keeping a stale name after the action it named was deleted.

An operator that takes several settings and refuses one (a bad enum, vars not JSON, a bone not there, a row past the end) must refuse before writing any: CANCELLED pushes no undo step, so what it wrote before stays. Read each operator the new ops reach for settings written into live data ahead of a check (mask.set, driver_set, Parent Bone with Keep Animation were), and edit a copy put back at the end.

Three invariants that caught bugs the area probes missed, worth checking after every op in any area: the frame shown
equals the same frame left and reached again (an edit that changes keys must evaluate the frame shown, and so must
whatever follows it, as Time Together's retiming); an edit that moves nothing (a click with a brush, strength 0, a
stroke off the curve) is CANCELLED with no undo step and nothing changed, not even a key's interpolation; and a
"make it so" op pressed twice (Aligned, Flat, a handle type) changes nothing the second time. Picks or selections
stored as bare indexes or frames go stale when the thing they index moves: move the key under them, then edit.

Edges and limits, which the eye file's probes reached only by reading the code: a move held at an edge (frame 1, a
knob's box) must hold the whole selection together, so count the keys after every move left past frame 1, scale and
copy; settings set with no undo step (the timeline's filters and Lock, overlays) stay through an undo of something
else; a step pushed on another frame than the last compares that frame's pose, so an edit that changes nothing there
pushes none; and every number an operator takes (a frame, a timing y, a handle) is tried at 1e6, INT_MAX and 1e30.

For keying features (Auto-Freeze Keys, Key Together, Key Whole Drawing) one more: what every channel of the layer
shows on each of its poses (frames keyed anywhere on it) is the same before and after an edit on another frame, with
Smooth keys too (they lean on their neighbours, so a key bends the stretches past it), and right after opening a file
(state rebuilt on the first edit, such as a filler not yet taken, behaves differently from mid-session).

Moves between containers (Move to Layer, Move to Bone Group, Paste): data copied raw from one drawing or layer carries
that place's bookkeeping (a channel's `synced`, what its drawing last keyed) into the other, where it reads as edits
(the target's own keys went); Paste through JSON dropped it, so it only showed for the direct move. Check the target's
own keys and poses, not only the moved part's. And everything that binds a drawing to bones: Parent Bone (Layer and
Points) wins over point weights, a bound group over what is inside it, and a switch or masking group must go whole or
not at all. For solvers (IK), build the chain under a parent flipped one way, stretched one way, and in a mirrored bone
group; a turn of a bone goes the other way or bends there. Many small float rotations of points stretch them (3e-4 over
thousands of steps): keep a light model as angles and lengths, not rotated points.

## 3. Confirm every report

A probe's report is a claim. Rerun each repro yourself (in parallel) and read the numbers before telling the user it's
a bug. Sort into: confirmed bugs; maybe-by-design (check the spec and the code, and ask the user when it's a design
call); harness mistakes (drop them). Tell the user each batch as it's confirmed: one short line per bug, worst first,
in their words (what they'd see), with the numbers that show it.

## 4. Fix while the probes keep running

Fix on the one branch, in the main folder (no worktrees or branches for fix groups): many bugs are
fixed one after another, grouped by area so each build compiles few files.

When the user wants fixes (they may say so up front), fix confirmed bugs one at a time, worst or simplest first,
while probes keep reporting:

- Read the code the repro points at; find the cause, not the symptom. A design call (two behaviours that can't both
  hold) goes to the user with a recommendation before you build it.
- Write the test first through operators (`tests/`, `add_test` in CMakeLists.txt), see it fail, fix, see it pass.
- Add a mutation entry to `PENDING` in `tools/mutation_checks.py` for each fix, and undo each fix by hand once to
  see its test fail (below). The entries run at the end (step 5), not one by one.
- Rebuild with the LNK1168 retry loop (the user's own copy may hold the exe), then run the broad related tests
  (`ctest -R` over every area the change touches), not only the new one: a fix in a shared path (how a key goes in,
  how a frame is evaluated) can change everyday behaviour. Keep such a fix to the cases the bug is about (a key put in
  a stretch shaped on the path, not every key) and the plain cases as they were.
- The frozen app in `<sweep>/bin/` is the build before the fixes: write the new test as `# --- ` sections that each
  build their own scene (shared helpers in the header), then run each section on its own against both builds (exec
  the header, then the section: `set OA_TEST=<test.py> & set OA_SEC=<n> & <exe> --background --python
  scripts/section.py` prints `SECTION n PASS`). Every section should fail on the frozen copy and pass on the new build, which proves
  the tests without touching the source.
- A test that passes with its fix undone tests nothing: undo the fix by hand once (`if (false && ...)`), rebuild and
  see the test fail before relying on it. Build its scene like the repro's (the eye file's Look At had an Eye Shape;
  without one the bug never showed).
- Points bent by a deform: bend hard (one cage corner pulled far out) and move far (0.3). A point's skin is a
  linear guess round where it was, so a mild bend lands a move that skips the settle within a test's tolerance.
- A mutation entry's test is `'tests/test_x.py'` or a bare stem (`'timing_curve'`); a bare `'test_x.py'` finds no
  test and shows as missed. `--lanes N` counts this folder as one, so with `--not-here` `--lanes 1` runs nothing ("0
  caught, 0 not"): one lane is `--lanes 2`. An entry whose undone code doesn't compile at `/W4` (a variable left
  unused) reports BUILD FAILED: undo the whole change in it. Guards the operators can't reach (op_arg_float already turns nan, inf and text into the
  fallback) need no entry.
- An entry can stop being caught because later code does the same job (Auto-Freeze's holds before the key, redone by
  `hold_reach` after it): find the path where the code is the only one doing it (a Switch key's `auto_freeze_hold`)
  and test there. A check that the shortcut is reused counts it (`wm.motion_path_places()["offsets"]`) across the
  changes a user makes on the way, a frame change included.
- A later fix can move or reword code an older entry names ("found 0 times" or "found 2 times": fix the entry to the code as it is now,
  and prove it by hand again), or make its test too loose to notice: a check that something is kept "as it was"
  compares the stored values exactly (read back after storing them), since a fit lands close enough to pass a tolerance.
- Never stop a hand prover (undo, build, test, put back) mid-run: it leaves the undone fix in the source. If one was
  stopped, diff the files it swaps and put the fix back before building. Prove by PENDING index (`scripts/prove.py 56 57`), not a list of its own.
- A hang's test: `faulthandler.dump_traceback_later(20, exit=True)` before the op, cancelled after. Its watchdog runs
  outside Python's lock, so it fires while a C++ operator loops (a `threading.Timer` never gets to run).
- Taking out a floor or clamp (a least speed, a least gap) can break code that counted on it: what was always slightly
  increasing becomes flat, and a strict `<` then reads a held frame as a turn. Run the tests on 2s and 3s too.
- Precision leftovers: measure what is left after a fix (frame by frame) and say what it comes from (sampling, a
  polyline's chords) rather than chasing it; tell the user how big it is next to the scene.
- New reports keep arriving: confirm them between fixes, add them to the list, never interrupt a fix half done.
- At the end: the spec (`docs/SPEC.md`) and the live Doc in small find-and-replace edits, then one commit on the
  branch. Never push or merge unless told.

## 5. Mutation checks and the full ctest

A sweep always ends with the milestone checks, and they never run outside a sweep or a "run milestone checks":
the user's message being answered must ask for one (a hook, `~/.claude/hooks/mutation_guard.py`, refuses the
script otherwise; it looks for "milestone check", "mutation" or "sweep"). An ask covers its own request only,
never the features after it. With the fixes in: `python tools/mutation_checks.py` (`--lanes N` within the load
limit below) and the full ctest. Nothing edits source while they run (the script swaps it). Each must be caught:
strengthen the test if not, commit, and empty `PENDING`. The hook reads only the latest message, and a background
task's notice (a probe, build or test run finishing) counts as one: once a notice has come in, the script is refused
until the user asks again. So keep every entry proven by hand as you go, and when refused say so and ask the user to
say "run milestone checks" (a wrap-up button with that label sends it).

## 6. Improve this skill

After each sweep, fold back what you learned: a new fuzzer op for a kind of edit it missed (an area probe's report
may name one), a new invariant, a harness pitfall below, a better brief. The skill lives in the repo
(`.claude/skills/bug-sweep/`), so commit its changes with the sweep's fixes.

## Load

Keep the machine's load moderate: about three heavy jobs at once (a build, a probe, a mutation lane each count), and
count every app process a probe starts, not the probe: four probes each running three copies of the app (twelve, each
bending drawings on all its threads) cut the power within half an hour. Brief each probe to run one app at a time, and
run the area probes one or two at a time, the next started as one reports (SendMessage resumes a stopped one from its
transcript). A
sweep with five mutation lanes, four fix builds and probes running for hours ended with the computer switching off,
and the power cut zeroed a source file a mutation check had open (the runner now syncs its backup first; after a
crash, check every folder for files of zero bytes and broken .pdb/.obj files before building).
A power cut mid-run leaves each fuzz lane a "crash-or-hang" log with an empty hang dump, stopped at the same minute:
not a bug, check the times against the shutdown before shrinking.
`tests/test_motion_path_places.py` and `test_motion_path_on_path_fast.py` fail on a saturated CPU (their work never spreads over threads, "threads" 1): rerun them quiet.

## Pitfalls (harness mistakes that look like bugs)

- **Key Whole Drawing settles each timeline the first time it is recorded in**, after it is turned on or a file is
  opened: an action not visited since gets its other channels keyed on its keyed frames when first entered, an edit
  or not. A "CANCELLED but changed" or "entering an action changed" naming `*_keys_actions` on a drawing keyed whole
  is this.

- **Python data edits aren't undo steps.** `bone_set`, `set_point`, `layer.keyframe_insert` join the next operator's
  step, so undoing that operator also takes them back. Call `harness.rebase()` (save and reopen) before checking an
  operator after such edits.
- **Undo keeps the playhead**, as Blender does: compare after undo at the frame the state belongs to.
- **Selection and the active layer or bone are never undo steps**: `harness.edits()` leaves them out.
- **A reference's points are locked** unless its Edit Points is on; the fuzzer skips such layers.
- **The undo history holds about 62 steps**: a long chain can't undo to its start.
- **Bones in Python have no id key**; `parent_bone` is a name; a controller with no side actions has a zero box,
  and Contain Knob clamps the knob to it (use `contain_knob=False` in probes).
- **"path dots off the pose by ~0.0003" with Own Motion** is a known artifact of the eye file.
- **Frame-order bugs hide behind reads.** Setting `doc.frame_current` evaluates at once; a probe that reads between
  frames changes what the next frame starts from. Compare a frame reached from several others (`f-1`, `f+1`, 0, keys)
  without reads between, and diff every layer's points and bones to find which one depends on the order.
- **A parent with uneven scale** turns and stretches its children by a skew, not a similarity: a check that a point
  weighted to one bone turns rigidly with it must skip such bones (`skewed_above` in fuzz.py).
- **Some operators push two undo steps** (a select-none and the edit), and `doc.time_together` set from Python isn't
  one: undo back to each saved step index, not one undo per op.
- **With auto-key off, going to another frame drops an edit not keyed.** A check that visits frames before an op
  (to record poses) then blames the op for the lost edit: skip such visits while auto-key is off.
- **Key Together's state is per timeline and partly rebuilt on opening** (the timeline it last keyed in is saved, its
  layers recorded as loaded): test edits right after opening a file, inside an action entered again, and on a
  duplicate, not only mid-session on the mainline.
- **`OA_SWEEP_TMP` must exist** before a run: a missing folder fails the first `harness.rebase()` with a bare
  AssertionError on `open_mainfile`.
- **Folding rows moves keys only on their own frames.** A check that folding (Key Together) moved nothing compares each
  channel's own key frames, not every frame keyed anywhere on the layer.
- **`mpath` changes the selection** to pick its targets: restore it after, or the next op's "changed" check blames the op.
- **A name the operators refuse** (a fix renamed to a bone's turn action, "turn 2") can still come from an old file:
  test it by editing the saved file's JSON and reopening it.
- **A promise a stretch can't keep.** "Every dot stays" can't hold for a key put where a Bounce touches its end key
  mid-stretch (the dots after it go back along the curve to the same place: no key and stretch pair shows that without
  control points) or Convert to Key behind such a bounce: what plays is Moho's (both halves the stretch's
  interpolation). Report it as a design question, not a bug to fix.
- **Inside an action the saved bones are posed on the frame shown**: an op that goes to another frame (`fix_enter` with frame=) changes them with no step. The fuzzer compares such ops on the frame they started on (`check_op`'s `frame_before`); a probe saving snapshots must do the same.
- **Names that mean something.** Where data is tied by name (a bone's own action is the action named after it), every path that makes or changes a name can break the tie: new actions, renames, new bones, conversions, Symmetrize and mirrors, and the upgrade on opening (which must not convert again on the next open). Probe them all together, and put the check in one place they all call.
- **A fix made redundant.** A mutation entry missed because other code already does the job (a prune done earlier on the way): take that change back out, so no code stands that no test needs.
- **An edit by nothing turned CANCELLED** leaves older tests that ran the real path with it (Alt S by 1) testing nothing: give them a hair off (1.00001) so their mutation entries still catch.
- **A rig loop** (a bone's IK target riding on the chain, a constraint fed by what it moves) can make a pose depend on
  history by design: report it as a question, don't fix it as a bug.
- **Handles through a deform: the wire isn't what shows.** The edit wire refits each bent segment's handle lengths
  (`evaluated_handles(shown=True)`), but the viewport draws, picks and drags each handle as bent at its own point
  (`oanim.wm.handle_ends_shown`). Measure a neighbour's handle there, and stack deforms (a group's and the layer's,
  two on the layer): each fit is bent on by the next, which is where the sweep's 0.035 slip hid. Anything that writes
  a handle back through the deform (Smooth Points, place_handle, settle) must take the fit off first, and write a
  handle only by its own change, never the shown value back, or an option that moves nothing (Radius alone) moves it.
- **An "empty step" note is a lead, not a bug.** `fuzz_timing` notes ops that push an undo step and change nothing it
  sees. Diff the whole saved file around the op before fixing: a Move Keys noted so had moved a handle key the targets
  don't list. Timing Decimate keeps its empty step on purpose (raising Ratio in Adjust Last Operation puts points back).
  Settings set as they already are (Set Action, Reference Settings) were real: they now return CANCELLED.
- **Diffs stop at about 9 places.** `edits()` used to cut the list first and drop selection lines after, so picks
  sorted first hid every real edit (both `harness.py` and `fuzz_timing.py`, fixed: `diff(..., skip=True)` leaves them
  out as it goes). Any new filter on a diff goes inside it, never on its capped result.
- **`fuzz_fail_<seed>.json` exists while a run is going.** The fuzzer writes a "crash-or-hang" placeholder before
  each op (so a crash leaves one): read it only once the run has ended, when the log's last line says "ops clean" or
  FUZZ FAIL. A placeholder read mid-run looks exactly like a crash that won't replay.
- **Smooth between two keys plays straight.** A test that needs two timings to differ (a retiming, Key Together's
  majority) uses Ease In/Out against Linear (`keyframe_set(path, frame, interp=)`), or it passes with the fix undone.
- **A long fuzz log that won't shrink**: replay its first N ops with `OA_FUZZ_SAVE_END`, then replay the rest on that
  file as `OA_SWEEP_FILE` and shrink only those (seed 14's 210 ops came down to two this way in minutes).
- **A rename on every change finds tests that read a name too early.** Fix names now follow at each undo push: a test
  that reads a fix's name, then converts or deletes what it names, must read it again after.
- **Bone keys hold the change from the setup, not where the bone is.** Position and angle keys (in actions too) hold
  `Bone::transform` and `turn`, so a bone held still is keyed (0,0) and 0 whatever its setup. A check against
  `setup_position` or `setup_angle` passes only for bones at the origin pointing right: build test bones off the
  origin and turned (the practice file's Head_X points up), and compare with the channel's own frame 0
  (`channel_setup` in animation.cc).
- **A field "missing before" can be a hair off its default.** The file leaves a point's width out at exactly 1.0; a fix playing a width can leave the stored 1.0 two rounding steps under it (0.9999999, settled, never growing) after some frames are visited, so the field appears. `SAVED_DEFAULTS` in harness.py and fuzz_timing.py compares a missing one as its default; add a key there when another such field shows up.
- **A preview of an edit not yet made must work the frame out.** The iPad's live erasing cut a copy of the drawing and drew it at once: references of the line cut (the practice character's inside of the mouth is one of its lip line) and points that follow it are made again only by the app's update (`animation_sync`), so the preview showed them as before. Compare a preview with what the edit gives once done, on a file with references and followers, not only plain layers.
- **References refuse point edits.** An operator that edits points (delete, dissolve, duplicate, peak, smooth) must
  skip a reference without Edit Points and return CANCELLED with no undo step: its edit is put back on the next
  capture, so it looks done and isn't. Check it after every point op that ran with a reference picked.
- **A paste on the setup frame pastes changes.** Keys hold changes from the setup, so pasting them onto frame 0 moves
  the setup and every later key with it: paste twice and the second press must change nothing. The same for Paste
  Pose there, and for any operator with two passes on frame 0 (Same Look's): the first pass's recording moves the setup,
  so the second must work against the setup as it was, or the change goes on twice.
- **A point that won't land may be squashed flat by the rig.** Before blaming a move, set a stored point by hand on
  that pose and read what shows: on the practice character, with Bone.001's knob in "Up and Right", the brow's Mesh
  Deform squashes Brow_Mask_R so a stored move of 0.1 shows 0.006, and no move can put its points where it's told.
- **An operator ignores a setting it doesn't read.** Dyntopo's refine= became decimate= (off by default), and the
  fuzzer kept sending refine=: its "Collapse" strokes only added points, then were checked against strokes without
  Dyntopo (seed 33's Twist "0.018 off"). When a check fails on a setting, first see that the operator reads it
  (`op_arg` / `op_has_arg` in its exec).
