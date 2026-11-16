"""Mutation checks, batched until a milestone: each proves a test fails without the fix it guards.

Each feature adds an entry to PENDING for every fix it makes: the file, a piece of its code (found exactly once), what
to put there instead to undo the fix, a name, and the test that should then fail. They are run together when the user
says "run milestone checks":

    python tools/mutation_checks.py              # every pending check
    python tools/mutation_checks.py 3 7          # only those
    python tools/mutation_checks.py --lanes 6    # six at once (this folder and five lane folders)
    python tools/mutation_checks.py --lanes 6 --prepare   # only make and build the lane folders
    python tools/mutation_checks.py --lanes 6 --not-here  # the five lane folders only: this one stays free to edit
    python tools/mutation_checks.py --remove-lanes

Lanes: a check edits the source and rebuilds, so checks run side by side only in folders of their own. --lanes N uses
this folder and N-1 lane worktrees beside it (<this folder's name>-mut1, ...), made on first use (a configure and full
build, about ten minutes, reusing this build's fetched sources) and kept for the next run; each run brings them to this
folder's commit plus its uncommitted changes. A lane takes the next check on the file it last changed when there is
one, so each rebuild compiles one file. --remove-lanes deletes them.

Run it from the worktree's root, with nothing else building or editing the source there: it changes one file at a
time, rebuilds (for C++), runs the test and puts the file back. A check the test still passes is "NOT CAUGHT": the
test is strengthened until it fails. Once every check is caught and committed, PENDING is emptied.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading

CMAKE = (r"C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/Common7/IDE/CommonExtensions/Microsoft/"
         r"CMake/CMake/bin/cmake.exe")
EXE = os.path.join("build", "bin", "RelWithDebInfo", "OpenAnimate.exe")

# (file, old, new, name, test)
PENDING = [
    ('src/anim/animation.cc', '          return bone ? &bone_poses_of(poses, *bone) : &poses.all;',
     '          return &poses.all;',
     'Auto-Freeze doesn\'t hold a bone at a knob\'s key whose actions hold it still', 'tests/test_auto_freeze_knob.py'),
    ('src/anim/animation.cc', '    const bool moves = knob == &bone ||',
     '    const bool moves = false ||',
     'Auto-Freeze holds a knob at its own keys', 'tests/test_auto_freeze_knob.py'),
    ('src/anim/animation.cc', '                       [&](const auto &k) { return k.frame > 0 && distance(k.value, setup) > 1e-5f; });',
     '                       [&](const auto &k) { return k.frame > 0 && distance(k.value, setup) >= 0.0f; });',
     'A bone an action holds still isn\'t moved by it for Auto-Freeze', 'tests/test_auto_freeze_knob.py'),
    ('src/ops/vector_ops.cc', '            std::all_of(rigs.begin(), rigs.end(),',
     '            std::all_of(rigs.end() - 1, rigs.end(),',
     'A collection hidden on the bone layer worked in hides a sub bone group\'s drawings in it', 'tests/test_sub_group_collections.py'),
    ('src/data/bones.cc', '  return std::all_of(panels.begin(), panels.end(),',
     '  return std::all_of(panels.end() - 1, panels.end(),',
     'A collection hidden on the bone layer worked in hides a sub bone group\'s bones in it', 'tests/test_sub_group_collections.py'),
    ('src/data/bones.cc', '  return !held;', '  return false;',
     'A bone or drawing in no collection shows with All hidden', 'tests/test_sub_group_collections.py'),
    ('src/anim/animation.cc', '      if (knob.controller_size_auto && !sides_keyed) {', '      if (knob.controller_size_auto) {',
     'Picking another action never moves a controller edge the knob was keyed to', 'tests/test_controller_box_from_keys.py'),
    ('src/anim/animation.cc', '        if (!knob.controller_actions[side].empty() && own_timing[side].empty() && !across.empty()) {',
     '        if (false) {',
     'A controller side not keyed yet is as long as the opposite side is keyed', 'tests/test_controller_box_from_keys.py'),
    ('src/anim/animation.cc', '        if (most <= 1e-6f) {', '        if (false) {',
     'A controller side keyed only at rest counts as not keyed', 'tests/test_controller_box_from_keys.py'),
    ('src/anim/animation.cc', '        if (custom && key.interp == Interp::Custom) {', '        if (false) {',
     "The timeline's Paste Interpolation carries a Custom curve", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/anim/motion_path.cc', '    b.timing = s.interp == Interp::Custom ? curve : TimingCurve{};',
     '    b.timing = TimingCurve{};',
     "The Path Timing graph's Paste Interpolation gives the copied curve", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/anim/motion_path.cc',
     '  for (size_t i = first; i < ch.keys.size() && (i == first || ch.keys[i].frame <= end); i++) {',
     '  for (size_t i = first; i < ch.keys.size() && i == first; i++) {',
     "The graph's Paste Interpolation pastes a span across breakdowns whole", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/anim/motion_path.cc', '    s.interval = b.interval;', '    s.interval = settings.interval;',
     "The graph's Paste Interpolation keeps each key's hold and interval", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/ops/anim_ops.cc',
     '    const bool edits = edited->contains(flat->id) || flat->id == doc.active_layer || family.contains(flat->id);',
     '    const bool edits = edited->contains(flat->id) || flat->id == doc.active_layer;',
     "Only Selected shows a bone picked in a sub bone group of the bone layer worked in",
     'tests/test_timeline_sub_group_bones.py'),
    ('src/ops/operator.cc', '      stretch_sync.finish(C);', '      (void)stretch_sync;',
     "A timing edit to the active picked stretch goes to the other picked stretches", 'tests/test_stretch_sync.py'),
    ('src/ops/motion_path_ops.cc', '        !(now == o.settings && now_curve == o.curve))', '        false)',
     "A picked stretch a timing edit changed itself keeps what it did", 'tests/test_stretch_sync.py'),
    ('src/ops/motion_path_ops.cc', '      if (on_active) {', '      if (on_active && false) {',
     "Shift Alt click on the active picked stretch unpicks it", 'tests/test_stretch_sync.py'),
    ('src/editors/timeline.cc', '        f.teals.push_back({{p.target}, p.start, p.end, p == shown});',
     '        f.teals.push_back({{p.target}, p.start, p.end, false});',
     "Each picked stretch is teal, the active one lighter", 'tests/test_stretch_sync.py'),
    ('src/ops/anim_ops.cc', '          if (targets.empty() && !doc.path_show_all) {', '          if (false) {',
     "Alt click in a row whose path is hidden shows it and picks there", 'tests/test_stretch_pick_hidden_path.py'),
    ('src/ops/anim_ops.cc', '                wm.path_also_shown = before;', '                (void)before;',
     "Shift Alt click on another path's row keeps the paths shown and their picks", 'tests/test_stretch_pick_hidden_path.py'),
    ('src/ops/motion_path_ops.cc', '  if (picks.stretches.size() < 2) {', '  if (picks.spans < 2) {',
     "One span picked on several paths: a timing edit reaches them all", 'tests/test_stretch_pick_hidden_path.py'),
    ('src/editors/timeline.cc', '      f.teals.push_back({others, f.start, f.end, false});', '      f.teals.push_back({others, f.start, f.end, true});',
     "One span picked on several paths: the path picked last the lighter teal", 'tests/test_stretch_pick_hidden_path.py'),
    ('src/anim/motion_path.cc', '  if (plays || (action_bone && !values) || !doc.action.empty()) {',
     '  if (bone_is_controller(b) || (action_bone && !values) || !doc.action.empty()) {',
     "A controller whose sides have no actions keeps what actions add to it", 'tests/test_motion_path_pupil_offsets.py'),
    ('src/anim/motion_path.cc', '            !action_played_apart(owner, by, bone, depth + 1, values))', '            true)',
     "A knob moved by actions apart from the bone counts as moved by its keys", 'tests/test_motion_path_pupil_offsets.py'),
    ('src/anim/motion_path.cc', '    if (o.id != kept.bone && apart_from(o)) {', '    if (o.id != kept.bone && apart_from(o) && false) {',
     "Kept action offsets stay good while other bones' keys they don't follow change", 'tests/test_motion_path_pupil_offsets.py'),
    ('src/anim/motion_path.cc', '      p.points[i] += p.own_dx * d.x + p.own_dy * d.y;', '      p.points[i] += d;',
     "A slid dot moves through the path's own slopes (a turned, scaled path)", 'tests/test_motion_path_timing_slide.py'),
    ('src/anim/motion_path.cc', '  if (!(inputs == now)) {', '  if (false) {',
     "Something besides the paths' position keys changing isn't slid", 'tests/test_motion_path_timing_slide.py'),
    ('src/anim/motion_path.cc', '    for (size_t k = 0; k < frames && !(bone_is_controller(kb) && kb.controller_contain_knob); k++) {',
     '    for (size_t k = 0; k < frames; k++) {',
     "A knob kept in its box is never slid", 'tests/test_motion_path_timing_slide.py'),
    ('src/anim/motion_path.cc', '    path_shape_fill(doc, p);\n    path_speed_fill(p);\n  }\n  return true;', '    path_speed_fill(p);\n  }\n  return true;',
     "A slide draws the line between the dots again", 'tests/test_motion_path_timing_slide.py'),
    ('src/anim/motion_path.cc', '    const float2 ex = bone_position_from_transform(kb, float2{1.0f, 0.0f}) - zero;\n    const float2 ey = bone_position_from_transform(kb, float2{0.0f, 1.0f}) - zero;', '    const float2 ex = float2{1.0f, 0.0f};\n    const float2 ey = float2{0.0f, 1.0f};\n    (void)zero;',
     "A bone's slopes are per step of its keys' value, turned by its setup angle", 'tests/test_motion_path_timing_slide.py'),
    ('src/ops/motion_path_ops.cc', '  std::erase_if(wm.path_dots, [&](const auto &d) { return !path_timed_in(doc, shown, d.first); });', '  std::erase_if(wm.path_dots, [&](const auto &d) { return !path_shown_in(shown, d.first); });',
     'A dot picked on a Drawing or Key Together row stays while a path sharing its timing shows', 'tests/test_motion_path_picks_traced.py'),
    ('src/ops/motion_path_ops.cc', '      C.wm->path_also_shown.clear();\n      path_picks_prune(C, all);', '      C.wm->path_also_shown.clear();',
     'Picks on a path no longer traced are let go with Show All on or one path left', 'tests/test_motion_path_picks_traced.py'),
    ('src/ops/motion_path_ops.cc', '  std::erase_if(out, [&](const MotionPathTarget &t) { return !path_timed_in(doc, shown, t); });', '  std::erase_if(out, [&](const MotionPathTarget &t) { return !path_shown_in(shown, t); });',
     "The timing targets keep a whole drawing's or folded group's timing while one of its paths shows", 'tests/test_motion_path_picks_traced.py'),
    ('src/anim/keep_poses.cc', '        key_path_shape_map(k, f);', '',
     "Keep Poses and Apply Pose as Rest take a key's path control points and handles along", 'tests/test_rest_keeps_animation.py'),
    ('src/anim/keep_poses.cc', '  adding.insert(fixes.begin(), fixes.end());', '',
     "Keep Poses leaves a fix's keys on a bone it moves as they are", 'tests/test_rest_keeps_animation.py'),
    ('src/ops/rig_ops.cc', '                if (action_adds(*armature, action) || bone_fix_find(*armature, action)) {', '                if (action_adds(*armature, action)) {',
     'Apply Pose as Rest puts no hold key in a fix', 'tests/test_rest_keeps_animation.py'),
    ('src/ops/rig_ops.cc', '              else if (moved.count(b.parent) && !action_bones.count(b.id) && !bone_is_controller(b)) {', '              else if (moved.count(b.parent) && !action_bones.count(b.id)) {',
     'Apply Pose as Rest keeps a controller on its parent', 'tests/test_rest_keeps_animation.py'),
    ('src/ops/rig_ops.cc', '                b.controller_box_angle += std::atan2(change.b, change.a);', '',
     "A controller's box turns with its parent's applied rest, so the knob shows where it did", 'tests/test_rest_keeps_animation.py'),
    ('src/anim/animation.cc', '    position_keys_scale(*bone, 1.0f / bone->controller_frame_size, true);', '    for (Key<float2> &k : bone->position_keys.keys) {\n      k.value = k.value / bone->controller_frame_size;\n    }',
     'Converting to a controller makes the moves in every action frames', 'tests/test_rest_keeps_animation.py'),
    ('src/anim/animation.cc', '  position_keys_scale(*bone, bone->controller_frame_size, !(own_right || own_left));', '  if (!(own_right || own_left)) {\n    for (Key<float2> &k : bone->position_keys.keys) {\n      k.value = k.value * bone->controller_frame_size;\n    }\n  }',
     "Converting to Regular makes the knob's frames moves in every ordinary action", 'tests/test_rest_keeps_animation.py'),
    ('src/ops/pose_clipboard.cc', '      const float2 pos = ignore && invertible(skin) ?', '      const float2 pos = false && invertible(skin) ?',
     "Paste Pose's Ignore Bones puts each point where it showed when copied", 'tests/test_pose_clipboard.py'),
    ('src/ops/pose_clipboard.cc', '        p.pos = to_shown.inverted().apply(to_shown.apply(p.pos) + shift);', '        (void)shift;',
     "Paste Pose's Keep Place keeps the pasted points' centre", 'tests/test_pose_clipboard.py'),
    ('src/ops/pose_clipboard.cc', '      std::erase_if(onto, [](const auto &o) { return !o.first->selected; });', '',
     "Paste Pose's On Selected Only leaves bones not selected", 'tests/test_pose_clipboard.py'),
    ('src/ops/pose_clipboard.cc', '      b->turn = b->turn + (turn - b->turn) * factor;', '      b->turn = turn;',
     "Paste Pose's Factor blends a bone's angle", 'tests/test_pose_clipboard.py'),
    ('src/ops/pose_clipboard.cc', '      return pose.is_object() && pose_has_target(C, pose, flipped);', '      return pose.is_object();',
     "Ctrl V pastes the shapes copied with a pose where its points aren't", 'tests/test_pose_clipboard.py'),
    ('src/ops/pose_clipboard.cc', '      if (shapes_copy_to_clipboard(C) > 0) {', '      if (false) {',
     'Copy Pose carries the shapes for Ctrl V elsewhere', 'tests/test_pose_clipboard.py'),
    ('src/ops/pose_clipboard.cc', '      Bone *b = flipped ? bone_named(*rig, bone_mirror_name(name)) : nullptr;', '      Bone *b = nullptr;',
     "Paste Pose Flipped puts an _L bone's pose on its _R partner", 'tests/test_pose_paste_flipped.py'),
    ('src/ops/pose_clipboard.cc', '          copied_transform = (to->setup.inverted() * flip * from->setup).apply_vector(copied_transform);', '          (void)flip;',
     "A flipped bone's Transform is reflected through both bones' setups", 'tests/test_pose_paste_flipped.py'),
    ('src/ops/pose_clipboard.cc', '        copied_turn = -copied_turn;', '',
     'A flipped bone turns the other way', 'tests/test_pose_paste_flipped.py'),
    ('src/ops/pose_clipboard.cc', '      const float2 key = t.to.apply_vector(copied2(pj, "key", "key_add", look));', '      const float2 key = copied2(pj, "key", "key_add", look);',
     "A flipped point's change is reflected", 'tests/test_pose_paste_flipped.py'),
    ('src/ops/pose_clipboard.cc', '  if (const std::string other = bone_mirror_name(source->name); other != source->name) {', '  if (const std::string other = source->name; other != source->name) {',
     "An _L drawing's pose flips onto its _R partner", 'tests/test_pose_paste_flipped.py'),
    ('src/ops/pose_clipboard.cc', '          return neighbour == reach_in ? 1 : neighbour == reach_out ? 0 : -1;', '          return neighbour == reach_in ? 0 : neighbour == reach_out ? 1 : -1;',
     "A flipped handle goes on the image's handle reaching for the image of what it reached for", 'tests/test_pose_paste_flipped.py'),
    ('src/ops/rig_ops.cc', '                   bone_symmetrize_settings(*C.document, armature, source, *bone_find(armature, to));',
     '                   (void)source;',
     "Symmetrize leaves the other side's settings as they were", 'tests/test_symmetrize_settings.py'),
    ('src/ops/rig_ops.cc', '  dst.controller_knob_parent = src.controller_knob_parent ? bone_mirror_id(armature, src.controller_knob_parent) : 0;',
     '  dst.controller_knob_parent = src.controller_knob_parent;',
     "Symmetrize keeps the first side's Knob Parent", 'tests/test_symmetrize_settings.py'),
    ('src/ops/rig_ops.cc', '      c.min_angle = -hi;',
     '      c.min_angle = lo;',
     "Symmetrize copies Limit Angle's limits without turning them the other way", 'tests/test_symmetrize_settings.py'),
    ('src/ops/rig_ops.cc', '    if (i < own.size() && own[i].type == c.type) {',
     '    if (false && i < own.size() && own[i].type == c.type) {',
     "Symmetrize takes an existing bone's constraint keys away", 'follow_point_stress'),
    ('src/ops/rig_ops.cc', '                       copy.constraints.clear();',
     '',
     "Symmetrize gives a new bone the first side's Follow Point keys", 'follow_point_stress'),
    ('src/ops/vector_ops.cc', '    if (l != active && l->selected && inside_bones(l)) {',
     '    if (l != active && inside_bones(l)) {',
     "The Bone Group panel edits drawings that aren't picked", 'tests/test_layer_bone_group_panel.py'),
    ('src/ops/vector_ops.cc', '    return l && l->type == LayerType::Vector && layer_armature(doc, l->id) != nullptr;',
     '    return l && l->type == LayerType::Vector;',
     'The Bone Group panel shows on drawings outside a bone layer', 'tests/test_layer_bone_group_panel.py'),
    ('src/ops/pose_clipboard.cc', '  return float2_of(j[key]) + (look && j.contains(add) ? float2_of(j[add]) : float2());',
     '  return float2_of(j[key]);',
     'Paste Pose As Same Look drops what actions added where it was copied', 'tests/test_pose_paste_as.py'),
    ('src/ops/pose_clipboard.cc', '  return look ? T{} : ch.from_action_bones;',
     '  return ch.from_action_bones;',
     'Paste Pose As Same Look counts what actions add here twice', 'tests/test_pose_paste_as.py'),
    ('src/ops/pose_clipboard.cc', '    g_paste_as = op_arg_bool(C, "ignore_bones") ? PasteAs::Place : PasteAs::Keys;',
     '    g_paste_as = PasteAs::Keys;',
     'Paste Pose ignore_bones=1 is no longer Same Place', 'tests/test_pose_paste_as.py'),
    ('src/editors/timeline.cc', '      full[i].filter.channels = summed;',
     '      (void)summed;',
     "The timeline's Summary shows the keys of rows the filters take away", 'tests/test_timeline_summary_shown.py'),
    ('src/ops/anim_ops.cc', '    filter.channels = timeline_summary_channels(C);',
     '',
     "Keying or picking through the Summary reaches channels the filters hide", 'tests/test_timeline_summary_shown.py'),
    ('src/editors/timeline.cc', '    args["summary"] = "1";',
     '',
     "A click on the Summary picks keys of rows the filters take away", 'tests/test_timeline_summary_shown.py'),
    ('src/data/quick_shape.cc', '        shape.radii = {float(1.0 / std::sqrt(fa)), float(1.0 / std::sqrt(fb))};',
     '        (void)fa;',
     "Hold to Shape's ellipse takes the spread's radii, rounder than the loop drawn", 'tests/test_hold_to_shape.py'),
    ('src/data/quick_shape.cc', '  if (shape.circle) {\n    const float r',
     '  if (false && shape.circle) {\n    const float r',
     "Hold to Shape's Circle stays the ellipse", 'tests/test_hold_to_shape.py'),
    ('src/ops/draw_ops.cc', '  shape.has_fill = curve.closed && fill;',
     '  shape.has_fill = curve.closed || fill;',
     'Hold to Shape fills an ellipse with Close and Fill off', 'tests/test_hold_to_shape.py'),
    ('src/ops/draw_ops.cc', '  shape.style.line_width = line_width;',
     '  (void)line_width;',
     'Size Unit View: a line takes the width field\'s width, not its size on screen', 'tests/test_draw_size_nib.py'),
    ('src/wm/context.hh', '  return ts.ink.size_view ? ts.ink.view_size * 0.5f * pixel : draw_width(ts, mode) * 0.5f;',
     '  (void)pixel;\n  return draw_width(ts, mode) * 0.5f;',
     'Size Unit View draws at the Scene width', 'tests/test_draw_size_nib.py'),
    ('src/data/ink_stroke.cc', '  float v = (s.use_pressure ? pressure_curve(s, pressure) : 1.0f) * nib;',
     '  float v = (s.use_pressure ? pressure_curve(s, pressure) : 1.0f) * std::max(nib, 1.0f);',
     'The nib leaves the line its full width every way', 'tests/test_draw_size_nib.py'),
    ('src/assets/draw_presets.cc', '  ink.nib_direction = amount("nibDirection", none.nib_direction);',
     '',
     "A saved pen loses its nib", 'tests/test_draw_size_nib.py'),
    ('src/ops/draw_ops.cc', '  std::erase_if(ts.brush_recent, [&](const BrushSettings &b) { return brush_settings_unnamed(b) == used; });',
     '  (void)used;',
     'Recently Used lists a brush drawn with twice', 'tests/test_draw_size_nib.py'),
    ('src/ops/draw_ops.cc', '    draw_brush_used(ts);\n    return true;',
     '    return true;',
     'A stroke leaves its brush out of Recently Used', 'tests/test_draw_size_nib.py'),
    ('src/data/ink_stroke.cc', '  return s.min_opacity + (1.0f - s.min_opacity) * pressure_curve(s, pressure);',
     '  (void)pressure;\n  return 1.0f;',
     "Opacity's pressure leaves the line solid", 'tests/test_point_opacity.py'),
    ('src/data/ink_stroke.cc', '    knot.opacity = kept[sample].opacity;',
     '',
     "The fit drops the points' opacity", 'tests/test_point_opacity.py'),
    ('src/data/ink_stroke.cc', '    fitter.opacity = &opacity;',
     '',
     'The fit leaves out a point the opacity needs', 'tests/test_point_opacity.py'),
    ('src/ops/draw_ops.cc', '      drawing.points[p].opacity = std::clamp(knot.opacity, 0.0f, 1.0f);',
     '',
     "A drawn line's points stay solid", 'tests/test_point_opacity.py'),
    ('src/ops/draw_ops.cc', '    k.opacity = opacity;',
     '    k.opacity = 1.0f + 0.0f * opacity;',
     'Hold to Shape draws solid', 'tests/test_point_opacity.py'),
    ('src/io/oanim_file.cc', '      drawing.points.back().opacity = std::clamp(get_float(p, "opacity", 1.0f), 0.0f, 1.0f);',
     '',
     'Opening a file makes every point solid', 'tests/test_point_opacity.py'),
    ('src/gpu/tessellate.cc', '    const float core_alpha = (hw < aa * 0.5f ? std::max(hw * 2.0f / aa, 0.05f) : 1.0f) * fade(i);',
     '    const float core_alpha = hw < aa * 0.5f ? std::max(hw * 2.0f / aa, 0.05f) : 1.0f;',
     "A solid line draws its points' opacity solid", 'tests/test_point_opacity.py'),
    ('src/anim/layer_pick.cc', '    stroke(outline, radii, closed, joins, opacity ? *opacity : no_opacity);',
     '    stroke(outline, radii, closed, joins, no_opacity);',
     "A line's runs drop its points' opacity", 'tests/test_point_opacity.py'),
    ('src/data/vector.cc', '        r_opacity->push_back(o0 + (o1 - o0) * blend);',
     '        r_opacity->push_back(1.0f + 0.0f * (o0 + o1));',
     'The outline samples every point solid', 'tests/test_point_opacity.py'),
    ('src/gpu/brush_stroke.cc', '    const float faded = std::clamp(edge.opacity0 + (edge.opacity1 - edge.opacity0) * u, 0.0f, 1.0f);',
     '    const float faded = 1.0f;',
     "A brushed line's dabs ignore the points' opacity", 'tests/test_point_opacity.py'),
    ('src/data/vector.cc', '      p.opacity = std::clamp(p.opacity + delta, 0.0f, 1.0f);',
     '      p.opacity = std::clamp(p.opacity + delta * 0.0f, 0.0f, 1.0f);',
     'Mean Opacity changes nothing', 'tests/test_point_opacity.py'),
    ('src/data/vector.cc', '    drawing.points[point].opacity = drawing.points[from].opacity + (drawing.points[to].opacity - drawing.points[from].opacity) * blend;',
     '    drawing.points[point].opacity = 1.0f;',
     'Subdivide makes its new point solid', 'tests/test_point_opacity.py'),
    ('src/data/vector.cc', '    to.opacity = from.opacity;',
     '',
     "Symmetrize leaves the partner's opacity as it was", 'tests/test_point_opacity.py'),
    ('src/assets/draw_presets.cc', '  ink.opacity_pressure = j.value("opacityPressure", none.opacity_pressure);',
     '',
     "A saved pen loses Opacity's pressure", 'tests/test_point_opacity.py'),
]

def build(root):
    return subprocess.run([CMAKE, "--build", "--preset", "release"], cwd=root, capture_output=True,
                          text=True).returncode == 0


def git(root, *args, data=None):
    r = subprocess.run(["git", *args], cwd=root, input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} in {root}: {r.stderr.decode(errors='replace')}")
    return r.stdout


def lane_roots(root, count):
    parent, name = os.path.split(os.path.abspath(root))
    return [os.path.join(parent, f"{name}-mut{k}") for k in range(1, count)]


def lane_ready(root, lane):
    """Bring a lane worktree to this folder's commit and uncommitted changes, made and built the first time."""
    sha = git(root, "rev-parse", "HEAD").decode().strip()
    if not os.path.isdir(lane):
        git(root, "worktree", "add", "--detach", lane, sha)
        deps = os.path.join(root, "build", "_deps")
        fetched = [f"-DFETCHCONTENT_SOURCE_DIR_{d[:-4].upper()}={os.path.join(deps, d)}"
                   for d in (os.listdir(deps) if os.path.isdir(deps) else []) if d.endswith("-src")]
        if subprocess.run([CMAKE, "--preset", "windows", *fetched], cwd=lane, capture_output=True).returncode:
            raise RuntimeError(f"configure failed in {lane}")
    else:
        git(lane, "checkout", "-f", "--detach", sha)
        git(lane, "clean", "-fdq", "--", "src", "tests", "scripts", "tools")
    diff = git(root, "diff", "--binary", "HEAD")
    if diff:
        git(lane, "apply", "--whitespace=nowarn", "-", data=diff)
    for path in git(root, "ls-files", "--others", "--exclude-standard").decode().splitlines():
        os.makedirs(os.path.dirname(os.path.join(lane, path)) or lane, exist_ok=True)
        shutil.copyfile(os.path.join(root, path), os.path.join(lane, path))
    if not build(lane):
        raise RuntimeError(f"build failed in {lane}")


class Lane:
    def __init__(self, root, number):
        self.root, self.number = root, number
        self.rebuilt = False  # its build holds a native entry's change
        self.last = None      # the file it last changed


def check(lane, i, entry, say):
    """Run one check in a lane: True when its test fails with the fix undone."""
    path, old, new, name, test = entry
    full = os.path.join(lane.root, path)
    if not os.path.exists(os.path.join(lane.root, test)):
        # Older entries name the test without its folder and prefix.
        test = os.path.join("tests", f"test_{test}.py")
    if not os.path.exists(os.path.join(lane.root, test)):
        say(f"{i} {name}: no test {test}; fix the entry")
        return False
    with open(full, encoding="utf-8") as f:
        src = f.read()
    if src.count(old) != 1:
        say(f"{i} {name}: its code is found {src.count(old)} times in {path}; fix the entry")
        return False
    backup = os.path.join(tempfile.gettempdir(), f"oanim_mutation_{os.getpid()}_{lane.number}_{os.path.basename(path)}")
    shutil.copyfile(full, backup)
    # On disk before the source changes: a power cut mid-check once left a source file zeroed with no copy to go back to.
    with open(backup, "rb+") as f:
        os.fsync(f.fileno())
    try:
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(src.replace(old, new))
        lane.last = path
        native = not path.endswith(".py")
        if not native and lane.rebuilt:
            # The build still holds the last native entry's change: a script-only entry runs on a clean one.
            shutil.copyfile(backup, full)
            if not build(lane.root):
                raise RuntimeError(f"the build in {lane.root} with every file put back failed: look before going on")
            lane.rebuilt = False
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(src.replace(old, new))
        if native:
            lane.rebuilt = True
            if not build(lane.root):
                say(f"{i} {name}: BUILD FAILED with it undone; fix the entry")
                return False
        r = subprocess.run([os.path.join(lane.root, EXE), "--background", "--python", test], cwd=lane.root,
                           capture_output=True, text=True)
        why = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "assert" in l][-1:]
        if r.returncode:
            say(f"{i} {name}: caught {why}")
            return True
        say(f"{i} {name}: NOT CAUGHT by {test}")
        return False
    finally:
        shutil.copyfile(backup, full)
        os.remove(backup)


def main():
    root = os.getcwd()
    args = sys.argv[1:]
    if "--remove-lanes" in args:
        parent, name = os.path.split(root)
        for lane in sorted(d for d in os.listdir(parent) if d.startswith(f"{name}-mut")):
            git(root, "worktree", "remove", "--force", os.path.join(parent, lane))
            print(f"removed {lane}", flush=True)
        return
    count = 1
    if "--lanes" in args:
        at = args.index("--lanes")
        count = max(1, int(args[at + 1]))
        del args[at:at + 2]
    only = set(args) - {"--prepare", "--not-here"}
    todo = [i for i in range(len(PENDING)) if not only or str(i) in only]
    # --not-here: only the lane folders, so this one stays free for editing while they run.
    here = "--not-here" not in args
    lanes = [Lane(root, 0)] if here else []
    extra = lane_roots(root, min(count, len(todo) + (not here)))
    if extra:
        print(f"getting {len(extra)} lane folder(s) ready", flush=True)
        errors = []

        def ready(lane):
            try:
                lane_ready(root, lane)
            except RuntimeError as e:
                errors.append(str(e))

        threads = [threading.Thread(target=ready, args=(lane,)) for lane in extra]
        [t.start() for t in threads]
        [t.join() for t in threads]
        if errors:
            print("\n".join(errors), flush=True)
            sys.exit(2)
        lanes += [Lane(lane, k + 1) for k, lane in enumerate(extra)]
    if "--prepare" in args:
        # Lanes made and built ahead of a run (it brings them up to date again).
        return
    lock = threading.Lock()
    tally = {"caught": 0, "missed": 0}
    broken = []

    def say(line):
        with lock:
            print(line, flush=True)

    def next_for(lane):
        with lock:
            if not todo or broken:
                return None
            # The next check on the file this lane last changed: its rebuild then compiles that one file.
            k = next((k for k, i in enumerate(todo) if PENDING[i][0] == lane.last), 0)
            return todo.pop(k)

    def work(lane):
        try:
            while (i := next_for(lane)) is not None:
                ok = check(lane, i, PENDING[i], say)
                with lock:
                    tally["caught" if ok else "missed"] += 1
            if lane.rebuilt and not build(lane.root):
                raise RuntimeError(f"the build in {lane.root} with every file put back failed: look before going on")
        except RuntimeError as e:
            with lock:
                broken.append(str(e))

    threads = [threading.Thread(target=work, args=(lane,)) for lane in lanes]
    [t.start() for t in threads]
    [t.join() for t in threads]
    if broken:
        print("\n".join(broken), flush=True)
        sys.exit(2)
    print(f"{tally['caught']} caught, {tally['missed']} not", flush=True)
    sys.exit(1 if tally["missed"] else 0)


if __name__ == "__main__":
    main()
