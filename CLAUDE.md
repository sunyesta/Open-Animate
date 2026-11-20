# Open Animate

A private, Windows-only 2D animation app: Moho's animation model with Blender's interface and
editing habits. C++20 core, Dear ImGui UI, embedded Python API (`oanim`, shaped like Blender's `bpy`).

The full plan is `docs/SPEC.md` (exported from the live Claude Docs spec; keep both in sync).
Reference material lives outside the repo, one folder up: `../blender-main/blender` (Blender
source, GPL; fine to read and port for this private app) and `../Moho` (Moho scripting docs and
Lua scripts). Never copy them into this repo.

## Build and test

CMake is bundled with Visual Studio Build Tools and is not on PATH:

```
CMAKE="/c/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin"
"$CMAKE/cmake.exe" --preset windows          # configure (fetches SDL3, ImGui, pybind11)
"$CMAKE/cmake.exe" --build --preset release  # build -> build/bin/RelWithDebInfo/OpenAnimate.exe
"$CMAKE/ctest.exe" --preset release          # run tests
```

Tests are Python scripts in `tests/`, run headless:
`OpenAnimate.exe --background --python tests/<file>.py` exits 1 if the script raises.
Add each new test file to `CMakeLists.txt` with `add_test`. Prefer testing through operators and
`oanim.wm.event_simulate()` so tests cover the same path as the UI.

Bug sweeps and mutation checks (a test must fail with its fix undone) go together, and run only when the
user's message being answered asks for one: "run milestone checks", a bug sweep, mutation checks. That ask
covers its own request, never later features. Meanwhile each feature adds its checks to `PENDING` in
`tools/mutation_checks.py`, proves each test by undoing its fix by hand once, and runs only its own tests.
When asked, run the sweep (the bug-sweep skill), that script and the full ctest, strengthen any test that
misses, commit and empty `PENDING`. A hook in the user's settings (`~/.claude/hooks/mutation_guard.py`)
refuses the script otherwise. If a merge is asked for with checks pending, say so and offer to run them.

The desktop and Start menu shortcuts run `tools/run_openanimate.ps1`, which starts a copy of the
build from `build/run/<build time>/`, so rebuilding works while Open Animate is open (reopen it to
get the new build). Run the build output directly only for tests.

To find what makes an edit slow, time it: `oanim.wm.profile_enable(True)`, do the edit (in a private copy, or call
`oanim.wm.profile_frame_end()` per step in a background run), then `oanim.wm.profile(frames)` lists the
`OANIM_PROFILE("name")` sections (`src/core/profile.hh`) slowest first. Off by default; add sections where needed. Deform work (cell solves, side searches, builds) is counted by `oanim.wm.deform_counts()`. A render bends its drawings side by side on the pool's threads (`layers_evaluated_drawings` in `src/anim/deform.cc`), so anything evaluation touches must be safe on several threads at once (shared caches locked or `thread_local`; workers borrow the layer index with `LayerIndexBorrow` and the pose cache with `ArmaturePoseCacheBorrow`). Motion paths work whole frames out on copies side by side too (`places_side_by_side` in `src/anim/motion_path.cc`, one at a time where bones have dynamics), so `animation_evaluate` on a copy must be as well; the profiler times only the main thread (`oanim.wm.motion_path_places` counts path places on every thread).

Python is embedded from `C:/Python314` (`OANIM_PYTHON_ROOT`), isolated from PYTHONPATH and user
site-packages. Scripts load from the source tree's `scripts/` while developing.

## One branch

All work happens on `milestone-3-animation` in the main folder, one feature at a time: no feature branches, no
second chat in a worktree of its own. Commit there; push only when told. The user's open app stays read-only.
Mutation checks' `--lanes` folders are scratch copies for running checks side by side, not branches for features:
remove them when the checks are done.

`docs/SPEC.md` sections are each one long line: update it and the live Doc in small edits.

## Layout

- `src/core` logging and reports (shown in the Info editor)
- `src/rna` property reflection: one description drives the UI, Python and later animation paths
- `src/data` saved data (`Document`); plain copyable values, undo snapshots copy them
- `src/ops` operators, built-in C++ operators, undo stack
- `src/wm` app and main loop, context, keymaps, key-event dispatch
- `src/editors` editor types drawn in dockable areas
- `src/ui` Blender theme for ImGui
- `src/python` interpreter and the low-level `_oanim` module
- `scripts/modules/oanim` the public Python API; `scripts/startup` runs at launch (keymap, Python operators)

## Conventions

- Follow Blender's patterns: every action is an operator (`category.name` idname, `poll`, `exec`,
  `OPTYPE_REGISTER`/`OPTYPE_UNDO` flags); keymaps are data; properties are described through RNA.
- Blender's file style: `.hh`/`.cc`, `snake_case` functions, `CamelCase` types, two-space indent,
  `/* */` comments that explain why. Compile clean at `/W4`.
- Moho decides data-model behaviour (layers, channels, actions, action bones, interpolation, frame 0
  as the setup pose); Blender decides interaction (tools, keymaps, editors, UI).
- Panel spacing comes from rules, not numbers picked at each widget (Blender's; `src/editors/ui.hh`): `ui_row_label`
  right-aligns labels, `ui_group_gap` between groups of rows, `ui_checkbox` (Blender-sized, its name after the box, no
  label in the label column) with `ui_checks_row`, fields that belong together joined `UI_JOIN_GAP` apart with only the
  outer corners round (`ui_join_next`, `ui_join_in_row`, `ui_button`), typed text in dark fields (`ui_input_text`). A panel's box keeps everything in it 8 pixels off both sides (its
  content region narrowed in `box_open`). Text is Blender's: Inter (`data/fonts`, copied next to the exe) at an 11 pixel
  em, rows kept 21 tall (`UI_FONT_SIZE`, `UI_FRAME_HEIGHT` in `src/ui/theme.hh`), with its shadow (ImGui's text drawing
  patched in `cmake/Dependencies.cmake`, `GOAnimTextShadowAlpha`).
- Icons are SVGs in `scripts/icons` on a 16 grid (white draws, black cuts out), drawn by `ui_icon` (`src/ui/icons.*`,
  NanoSVG) into a texture at the size shown and tinted; Properties' tabs run down its left side in Blender's colours
  (`properties_tab_strip` in `src/editors/properties.cc`: grey document, blue for every layer, green for its kind); the
  Layers editor's icons the same way (`layer_icon_color` in `src/editors/layers_editor.cc`: white groups, bone layers and
  camera, green drawn layers, red pixel layers such as media, blue references) with Blender's eye, camera and lock.
- Use ImGui wherever it can do the job; write custom widgets on top of it only where Blender's look
  or behaviour differs.
- ImGui gotcha: in a docked window `SetCursorPos()` is measured from above the tab bar and gets
  clipped; position overlays with `GetCursorScreenPos()` / `SetCursorScreenPos()`.

## Status

Milestone 1 (Foundation) done. Milestone 2 (Drawing) in progress. Done: vector layers (Moho curve
model), GL renderer with masking groups, group and reference layers, Layers editor, Properties tabs,
select/draw/pen/split/fill tools, G R S E, .oanim save and open (`src/io/oanim_file.cc`, zip + JSON
with a format version), File menu, unsaved-changes prompt, autosave, File > Recover, Save
Incremental, pen pressure, stamp brushes (`src/assets`: the asset library set in Preferences, brush
shapes in `brushes.cc` with the one-time upgrade of Moho-format libraries, brushes as presets in
`brush_presets.cc`; dabs in `src/gpu/brush_stroke.cc`; the Brush Settings window in
`src/editors/brush_editor.cc`). The Annotate tool: notes and drawing guides over the drawing, never rendered
(`src/data/annotations.*`, operators in `src/ops/annotation_ops.cc`, the tool in `src/editors/viewport.cc`). The draw tools (the spec's "Draw tools" note): every pen sample through Windows Ink or WinTab in
`src/wm/pen_input.*` and `src/wm/pen_wintab.*`, the Stroke Pen's engine in `src/data/ink_stroke.*`, the shelf and presets in
`src/editors/draw_shelf.cc`, `src/assets/draw_presets.*` and `src/ops/draw_ops.cc`, the Fill Pen and Fill Eraser in
`src/data/fill_paint.*`, the Stroke Eraser and Vector Trimmer in `src/data/line_cut.*`; the header (`draw_header` and the shared right strip `draw_shared_buttons` in `src/editors/viewport.cc`, the brush popover `brush_tool_popover` in `brush_editor.cc`); a brushed line painted with its stamps as it is drawn (`draw_live_line` in `src/ops/draw_ops.cc`, rendered by `draw_live_brushed` in `viewport.cc`; test hook `_oanim.draw_live_dabs`); Hold to Shape in `src/data/quick_shape.*` (`draw.quick_shape`, handles by `quick_edit_frame` in `viewport.cc`). Point opacity from pressure (`MeshPoint::opacity`, not animated; `InkSettings::opacity_pressure` and `min_opacity`, kept through `ink_fit`; drawn by `tessellate_stroke`'s `opacity` through `shape_outline` and `line_runs`, and per dab in `brush_stroke.cc`; test hook `_oanim.layer_shape_stroke`). Overlay colours (`src/editors/overlay_contrast.*`: wires, points and
motion path lines take a lighter or darker colour only where hard to see, from the canvas read back after each redraw into
`g_canvas_now` in `viewport.cc`; half-picked wires fade from orange via `OverlayLine::color_b`; light red handles, stronger red where picked, no outlines, shaded only where hard to see; colours in
Preferences; test hook `oanim.wm.overlay_colors`). Draw on iPad (Window > Draw on iPad...: a LAN server and WebSocket in `src/wm/ipad_server.*`, the QR window, canvas and strokes through the Stroke Pen's engine in `src/wm/ipad_link.*`, the messages in `scripts/modules/oanim/ipad.py`, the page in `scripts/ipad`; shelf pictures shared through `src/editors/draw_tile.hh`; test `tests/test_ipad.py`). Gradient layers (a vector layer with `Layer::gradient` on, `is_gradient()`: its one open curve's points are its colour stops, filling the camera frame; the field, colour table and picture in `src/data/gradient.*`, worked out as shown by `gradient_shown` in `src/anim/gradient_shown.*`; operators `layer.new_gradient` and `gradient.*` in `src/ops/gradient_ops.cc`, whose `gradients_keep`/`gradients_restore` around every operator in `operator.cc` and `gradients_check` at each undo push in `undo.cc` keep points and stops matched; drawn by `draw_gradient` in `src/gpu/scene_renderer.cc`, its overlay and tick and squash drags by `draw_gradient_overlay` and `gradient_press` in `viewport.cc`; the Gradient tab in `src/editors/gradient_panel.cc`; test hooks `layer.gradient_sample`, `gradient_places`, `gradient_handle_drag`, `gradient_image`). The shape tree, part built (the spec's "Shape tree": a closed shape under another as its sub shape, `Shape::parent`, with an Operation, keyable Smoothing and an eye; worked out at the end of `layer_evaluated_drawing` by `drawing_shape_tree_apply` in `src/anim/shape_tree.*` (Clipper2 on tagged samples, edges rebuilt from the original Beziers); operators `mesh.shape_parent_set`, `shape_move`, `shape_op_set`, `shape_smoothing_set`, `shape_show_set` and `shape_apply` in `src/ops/shape_tree_ops.cc`; trees kept whole and together by `drawing_shape_tree_mend` after every operator; copies re-parented by `drawing_shapes_copied`; the Shapes list as a tree and `sub_shape_panel` in `src/editors/properties.cc`; selection modes Shape and Shape Group, `shapes_under` in `src/editors/viewport.cc`; test hooks `layer.shape_tree`, `layer.evaluated_shape`; a shape as a set of connected points: the active point `VectorDrawing::active_point` (set by `select_click`, drawn white in `overlay_geometry`, `drawing_active_point`), joins by `drawing_shapes_join` (Merge, Merge by Distance, F through `join_shapes_after` in `src/ops/vector_ops.cc`, only shapes on the points just joined), splits by `drawing_shapes_split` after the deletes, lines closed filled by `drawing_fill_closed_lines`, older files merged on open (format 13); the Fill Pen and Fill Eraser work the stroke into the shape it starts on as a sub shape applied, `shape_work_in` in `src/data/fill_paint.cc`; test hooks `layer.active_point`, `layer.active_shape`, `wm.select_click(shift=)`). Still to do in milestone 2: Knife tool
(Ctrl K), the style library.

Milestone 3 (Animation) in progress on `milestone-3-animation`. Done: animated channels
(`src/anim/channel.*`, Moho interpolation modes, hold, interval) on layer transform, opacity,
points, radius, curvature and stored handles; edits become keys through `src/anim/animation.*`
(recorded before every undo push, frame change and save; frame 0 is the setup frame; auto-key on
`Document`); I / Alt I, keyframe jumps, key diamonds in the timeline. Media layers
(`LayerType::Media`: images, sequences, video and sound as clips): decoding in `src/media/media.*`
(WIC and Media Foundation, a worker thread per video), playback sound in `src/media/audio.*` (SDL
audio stream; Sync to Audio, scrubbing), clips and packing in `src/data/media_layer.*`, operators in
`src/ops/media_ops.cc`, the timeline's clip bars in `src/editors/timeline_media.*`; test media in
`tests/data/media`. Switch layers stage 1 (`LayerType::Switch`, `src/anim/switch.*`: keys hold the
child's id, hand keys win over action bone actions until a Rig key, switched-out children via
`Layer::shown()`) and stage 2 (picking: Layers editor dots, [ ], Switch menus, timeline bars,
editing a hidden child via `Layer::edit_out`, Replace Keys With, Wrap in Switch) and stage 3 (sub bone
groups and bone swaps, `src/anim/bone_family.*`: families of bone layers drawn and clicked together,
Match Pose from Previous Drawing) and stage 4 (the Asset Shelf editor, `src/editors/asset_shelf.cc`, with
thumbnails in `src/editors/switch_thumbnails.*`, hover previews via `switch_preview_set`, Duplicate and
Duplicate with Keys) and stage 5 (2-Way Linked drivers, `Driver::two_way` in `src/anim/drivers.cc`: one
channel of keys, edits to the driven side written back; Link All Channels); later items are in the spec's
Switch layers section. Motion paths stage 1 (`src/anim/motion_path.*`: targets, range by keys, paths worked out on copies like onion skins; drawn by `draw_motion_paths` in `src/editors/viewport.cc`; settings in the onion popover; operators in `src/ops/motion_path_ops.cc`; one path shown at a time, `motion_path_active` there, all with `Document::path_show_all`; Alt Space is `screen.animation_play_path_range`) and stage 2 (`Tool::MotionPath`: `motion_path_tool_input` and `motion_path_header` in `src/editors/viewport.cc`; placing, breakdowns and Smooth Arc in `motion_path.cc`); stage 3 (path handles on position keys: `Key::path_handles`, `key_path_handles` and the Bezier stretch in `src/anim/channel.cc`; `motion_path_handles` in `motion_path.cc`; drawn and dragged in `draw_motion_paths`; control points' handles, worked as a vector point's: `Key::path_control_handles`, `stretch_points` in `channel.cc`, `motion_path_control_handle_set` and `motion_path_controls_align` in `motion_path.cc`); stages 4-6 (path brushes: `src/anim/path_brush.hh`, the shelf in `src/editors/motion_path_shelf.cc`, strokes by `motion_path_brush_input` in `viewport.cc` and `anim.motion_path_stroke`; Grab and Smooth in `motion_path.cc`; speed brushes paint `Interp::Custom`, its timing a decimated curve in `Key::timing` (`src/anim/timing_curve.*`: `timing_fit` keeps as few points as hold every frame, `timing_sculpt` for the graph's Grab and Smooth) evaluated by `timing_progress`; Edit Path (brush `EDIT`) selects keys, G R S on keys (`motion_path_keys_transform`), V handle types; Edit Timing (`EDIT_TIMING`) selects dots (`wm.path_dots`; a box from empty space, `anim.motion_path_select_box`) and slides them with proportional editing (`motion_path_slide` in `motion_path.cc`; G the dots picked, `motion_path_dots_slide` and the `g_path_dots` modal in `viewport.cc`); which takes a press is `motion_path_press_taken` in `viewport.cc`; Alt S scales the timing (`motion_path_scale_spacing`); its input, modals and menus are `motion_path_tool_input`, `motion_path_edit_modals` and `motion_path_menus` in `viewport.cc`); timing (dots coloured by time
through their stretch, `PathDotColors` and `motion_path_dot_colors` in `motion_path.cc`; the timeline's timing chart and the
Path Timing editor (`path_timing_draw`) in `src/editors/timeline_path.*`, stretches from `motion_path_stretches`; overshoot is a timing curve
going past 1 or under 0; Shift swaps in a brush, `path_brush_shifted` in `src/anim/path_brush.hh`;
the chart has always-on proportional editing and Shift click's `motion_path_timing_blend`; the graph edits the curve in Edit
and Sculpt modes (`path_timing_graph` in `timeline_path.cc`, operators `anim.timing_*` in `motion_path_ops.cc`, curve get/set
`motion_path_timing_curve` and `motion_path_timing_curve_set`); one selected stretch, teal, shared by the key header, the rows, the chart and the graph: `motion_path_picked_stretches` in `motion_path.cc`, `motion_path_picks` in `motion_path_ops.cc`, `key_focus` and `focus_rows` in `timeline.cc`; Alt click in a row is `anim.timeline_stretch_pick`). On Path (a bone head's path an action moves, edited as it shows:
`Channel::on_path` and `follow_action`, `Key::path_offset`; left out in `apply_action_bone_actions_playing`; put on by
`motion_path_edit_prepare` before path edits and `anim.motion_path_on_path`, refitted by `keys_fit_path` in `channel.cc`). Key Whole Drawing (`Layer::key_whole_drawing`, on for new vector layers:
`drawing_key_whole` in `animation.cc` keys every shape channel on every keyed frame and takes a deleted key's frame from them
all; drawing targets, `MotionPathTarget::drawing`, in the timing chart via `motion_path_timing_targets` and
`with_path_channels` in `motion_path.cc`). Key Together on groups (`Layer::key_together`: `key_together_sync` and `key_together_release` in `animation.cc`, sharing `keys_together_sync` with Key Whole Drawing; filler keys are `Key::filler`, let go when it is turned off unless edited; its stretch picked with the Motion Path tool, on its row or any path inside, is the group's: `motion_path_timing_owner` and `motion_path_key_layers` in `motion_path.cc`, `KeyFilter::channels`; its timeline row, and a whole drawing's Drawing row, chained shut: `ChannelRow::chain`, `row_chain_release` in `timeline.cc`, `anim.key_together_set`; folding any other row is a view, its frames hollow where the picked bones or points have no keys of their own, `ChannelRow::picked_frames`). Breakdown keys (`Key::type`, `KeyType` in `src/anim/channel.hh`: a span across breakdowns timed as one in `Channel::evaluate`; timing tools see the span as one stretch through `SpanFlat` in `motion_path.cc`, which moves the breakdowns to their poses' frames; dragged ones clamped in `layers_move_selected_keys`; the Key Type menu is `key_type_header` in `timeline.cc`; Alt click and Alt Shift make them via `motion_path_key_type_set`). Time Together (`Document::time_together`, the timeline's chain toggle: `keys_move_selected`, `time_together_linked`, `time_together_timing_follow` for operators flagged `OPTYPE_TIMING`, `keys_span_frames_add` for + and -, `keys_offset_clamp` for sliding a stretch and `keys_match_timing` in `src/anim/animation.cc`). The timeline's rows as a layer tree (`channel_rows_built` and the filtering `channel_rows` in `src/editors/timeline.cc`: Summary, Pinned, layers in Layers-editor order, Camera and Simulation; Only Selected, Lock and the filters on `Document::timeline_*`, `anim.timeline_lock` and `anim.timeline_filter`; key clicks and drags by `timeline_key_click` and `g_key_press`, typed numbers through `src/editors/num_input.hh`; filler keys hollow by `key_summary_draw`; the scroll bar, `timeline_scrollbar_drag`; test hooks `oanim.wm.timeline_row_details`, `timeline_key_press`). Next: key buttons in Properties, dope sheet, frame-by-frame layers
and onion skins, PNG sequence export, playback range.

Rigging and modifiers (milestones 4 and 5, started early): bone layers (`LayerType::Bone`,
`src/data/bones.*` for the skeleton and _L/_R names), weights (a new point averages its neighbours, one connected to nothing has none,
Weight Select / Weight Paint tools) and Parent to Bone (Attached To Body, Head or Tail with its Turn: `Layer::parent_bone_attach`, `parent_bone_turn`, worked out by `bone_follow_skin` in `src/data/bones.cc`; Head or Tail with Deform Curve bends from that end, never stretched: `bone_curve_line_skin`'s `from` in `src/anim/bone_curve.cc`); a group's Deform, Points or Curve, bends every drawing inside (`layer_bone_binder` in `src/data/bones.cc`, read by `deformer_init` in `src/anim/deform.cc`; the group left in place and pictures carried whole by `whole_binder` in `src/data/document_layers.cc`); collections (`Document::collections`, tags on any bone or layer;
a bone layer's panel of them is `Layer::bone_collections`, eyes and stars; helpers in `src/data/bones.*`, operators
`armature.collection_*` in `src/ops/rig_ops.cc`, the chips in the Bone and Layer tabs by `collection_chips` in
`src/editors/properties.cc`, the M menu and search list in `src/editors/editors.cc`; older files' per-rig ones merged by
name in `src/io/oanim_file.cc`); the modifier stack (`src/anim/deform.*`: Mirror, and the Armature modifier every
layer inside a bone layer gets, kept by `document_sync_armature_modifiers`, and on groups the deforms, `group_deforms` in `deform.cc`, which bend every drawing inside); rig operators in
`src/ops/rig_ops.cc` (setup frame only for rig changes); Blender-style bone editing (head/tail joints, E, Shift A,
Shift D, Ctrl P / Alt P; `armature_move_selected_joints` for G R S on frame 0); the Select tool drags a posed bone as the IK mockup does (`armature_bone_drag` in `src/data/bones.cc`, the press read by `bone_press_drag_pick` in `src/editors/viewport.cc`, an Alt press handed over from the layer pick by `layer_click_drag_bone`; `armature.bone_drag`, test hook `oanim.wm.bone_drag`); Weight Paint tool. Actions (bone layer
timelines swapped into the channels) and action bone actions (`apply_action_bone_actions` in
`src/anim/animation.cc`; offsets live in `Channel::from_action_bones`, mirrored by `src/anim/action_mirror.*`). Bone constraints (`BoneConstraint` stack solved in `armature_pose`) and dynamics (`src/anim/dynamics.*`, simulated and cached). Bone types: Regular, Pin (one point, nothing connects to it) and 2 Axis
Controller (`src/anim/controller.*`, Convert To; the knob plays ordinary actions only, a bone's own action never in a side, older files' linked sides made ordinary on open by `controller_links_undo` in `src/anim/animation.cc`; its spots in the Bone tab, `controller_spots_panel` in `src/editors/properties.cc`; Show Box, `Bone::controller_box_show`, decided by `controller_box_shown` in `src/editors/viewport.cc`, previews and thumbnails from posed copies in `src/anim/controller_preview.*` and `src/editors/controller_thumbnails.*`). Bendy bones (`src/anim/bone_curve.*`: each regular bone with `Bone::bendy` on (the Bone tab's Bendy Bones panel, its header checkbox from `ui_panel_begin_check`; `armature.bendy_set`; off for new bones, worked out for older files on open, format 10) a cubic curve from keyed channels on `Bone`, `curve_*` and their `_keys`, a joint's two handles kept on the child; a free end mirrors the other; handles drawn and dragged by `draw_bone_curves` and `curve_handle_input` in `src/editors/viewport.cc`, Sharp Corner and Flatten Both to Bone in the bone menu, operators `armature.curve_*` in `src/ops/rig_ops.cc`; Deform: Curve, `Layer::parent_bone_curve` and `parent_bone_chain_end`, bends a drawing along a bone's or a chain's curve in `point_skin` in `src/anim/deform.cc`; next stages: pose dots). IK Ends and IK Bases (bone constraints; pins in `BoneConstraint::pin`/`pin_keys`, `IK_PIN_SCENE` or a bone's id, solved in `bones_full_pose` in `src/data/bones.cc`, chains by `armature_ik_chain`, reached by `armature_ik_reach`, held through edits by `armature_ik_hold`; bent paths `bend_keys`, an `on_key_only` channel; the dots, rings, paths and their input `draw_ik_points`, `draw_ik_path`, `ik_point_input`, `ik_path_input` in `src/editors/viewport.cc`; operators `armature.ik_*` in `src/ops/rig_ops.cc`; Alt stretches in `armature_grab_selected`; children keep their distance from a stretched parent's nearer end, `Bone::keep_end_distance`; Limit Angle arcs `draw_limit_arcs` and `limit_arc_input` in `viewport.cc`, `armature.limit_angle_end_set`; a drawing's right-click on a bone, `##drawing_bone_menu`, extends its chain by `layer_curve_chain_extend` in `src/anim/bone_curve.cc`, `layer.parent_bone_set extend_to=`). Fix actions, which follow bones (`BoneFix` in `src/data/layer.hh`: an ordinary action
whose keys on its bones are a line of poses; played by `bone_fix_play` in `src/anim/animation.cc` among the action bone
actions (`action_bone_action_turns` orders them), faded by `BoneFix::fade`, made by `armature.bone_fix_new`; the Bone tab's
`bone_fixes_panel` in `src/editors/properties.cc`; lines in the Spots panel's knob box (not the viewport's) from `bone_fix_knob_lines`, drawn by
`bone_fix_lines_draw` in `src/editors/viewport.cc`; mirrored by Symmetrize through `document_bone_fix_mirror`). Affected By (every animatable field's or timeline row's right-click submenu, its count left of the arrow (`ui_affected_available`, `ui_affected_count`; at 0 one line, `ui_affected_empty_text`), and its tooltip line, of what moves it besides its own keys: `layer_channel_sources` in `src/anim/animation.cc`, rows by `ui_affected_rows` and the submenu `ui_affected_menu` in `src/editors/driver_ui.cc`, `armature.bone_go`; fields are green or yellow from the shown timeline's keys only, no pink). Layer Symmetrize keeps the animation (`src/anim/symmetrize_keys.*`: Mirror Source's, Keep Partner's or None; actions around the copy mapped to their other side's by `symmetrize_action_names`, the copy's own renamed by `symmetrize_actions_apply`; `layer_actions_rename` in `animation.cc`).
The Actions panel in the Armature
tab (`actions_panel` in `src/editors/properties.cc`; `ActionPlay` in `src/data/layer.hh`: each action's Frame, mute and loop,
played by `action_own_frames` and set by `action_frame_set`). Copy Pose and Paste Pose (`src/ops/pose_clipboard.cc`: Ctrl C / Ctrl V over the viewport off frame 0, the selected
bones and points, by name and id; frame 0 keeps Copy Shapes, and Ctrl V pastes the shapes copied with a pose where its
points aren't). Ctrl Shift V is Paste Pose Flipped (_L / _R bones and drawings, points onto their mirror images). Not yet: local armature viewport.

Preferences live in `%LOCALAPPDATA%\OpenAnimate\preferences.json`; background runs (tests) never read
or write them.

Operators take string arguments (`OpArgs`, read with `op_arg()`), as in
`oanim.ops.wm.open_mainfile(filepath="walk.oanim")`. Changes without an undo step call
`UndoStack::mark_changed()` so the unsaved mark and autosave see them.
