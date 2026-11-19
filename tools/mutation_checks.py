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
    # Long IK chains bend in proportion to how they rest.
    ('src/data/bones.cc', '      if (n >= 3 && most > 1e-4) {\n', '      if (n >= 3 && most > 1e30) {\n',
     'a long IK chain bends smoothly, each joint the way it rests', 'tests/test_ik_axes.py'),
    # Bendy bones.
    ('src/anim/bone_curve.cc', '  s.head_mirror = s.kid >= 0 ? -s.tail_turn : 0.0f;\n',
     '  s.head_mirror = 0.0f;\n',
     'a free end mirrors the other end (the bone an arc)', 'tests/test_bendy_bones.py'),
    ('src/anim/bone_curve.cc', '        b.curve_parent_angle = other;\n        b.curve_head_angle = dev;\n        b.curve_lined = 0.0f;\n',
     '        b.curve_turn = wrap_angle(way - halfway(angle_of(way_of(poses, size_t(s.parent), false)), s.angle));\n        b.curve_lined = 1.0f;\n        (void)other;\n',
     'Alt on a joint handle breaks the joint, each side keeping its angle', 'tests/test_bendy_bones.py'),
    ('src/anim/deform.cc', '  if (!d.curve_rest.empty() && !d.curve_now.empty()) {\n',
     '  if (false && !d.curve_rest.empty() && !d.curve_now.empty()) {\n',
     'Deform: Curve bends a drawing along its chain', 'tests/test_bendy_bones.py'),
    ('src/io/oanim_file.cc', '        if (value != bone_curve_channel_default(name) || keys.animated()) {\n',
     '        if (false && (value != bone_curve_channel_default(name) || keys.animated())) {\n',
     'curve channels and their keys are saved', 'tests/test_bendy_bones.py'),
    ('src/anim/action_mirror.cc', '        mirror_keys(*theirs[k++], keys, from, to, [angle](float v) { return angle ? -v : v; });\n',
     '        mirror_keys(*theirs[k++], keys, from, to, [angle](float v) { return angle ? v : v; });\n',
     'a mirrored action turns curve handles the other way', 'tests/test_action_mirror.py'),
    # IK Ends and IK Bases (stage 2: data, evaluation, operators).
    ('src/data/bones.cc', '    if (k0 < 0 || k0 == frame) {\n', '    if (true) {\n',
     'a pinned IK End holds between keys', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  return u * u * (3.0f - 2.0f * u);\n}\n', '  return u;\n}\n',
     'a pinned end eases between keys as the keys do', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '        goal = poses[b].pose.apply(l0 + (l1 - l0) * e);\n', '        goal = l0 + (l1 - l0) * e;\n',
     'an end pinned to a bone rides it', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '        ik_angle[j] += wrap_pi(was - transform_angle(poses[j].pose));\n', '        ik_angle[j] += 0.0f * wrap_pi(was - transform_angle(poses[j].pose));\n',
     "Keep Angle: the end bone's children keep their angle", 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '    if (const BoneConstraint *base = bone_ik_base(bones[p])) {\n', '    if (const BoneConstraint *base = nullptr; base) {\n',
     'an IK chain stops at the IK Base', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  std::set<int> frames = {0};\n', '  std::set<int> frames;\n',
     'a point pinned with no keys stays where the setup frame has it', 'tests/test_ik_end.py'),
    ('src/ops/rig_ops.cc', '    c.ik_head = parent && bone_find(armature, parent->parent) && b.length < 0.6f * parent->length;\n', '    c.ik_head = false;\n',
     'a short end bone (a foot) puts its IK point at its head', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  if (moves(end, to)) {\n', '  if (false) {\n',
     'pinning to a bone the chain moves is refused', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  return follows(to) ? to.name + " already follows " + end.name : std::string();\n', '  return (false && follows(to)) ? to.name + " already follows " + end.name : std::string();\n',
     'pinning to a bone already following this end is refused', 'tests/test_ik_end.py'),
    ('src/anim/action_mirror.cc', '          return id ? float(id) : v;\n', '          return id && false ? float(id) : v;\n',
     "a mirrored action pins to the other side's bone", 'tests/test_ik_end.py'),
    ('src/ops/rig_ops.cc', '    constraint_pin_map(c, [&](uint64_t id) { return bone_mirror_id(armature, id); });\n', '',
     "Symmetrize's copy is pinned to its own side's bone", 'tests/test_ik_end.py'),
    ('src/anim/animation.cc', '    f(c.pin_keys, c.pin);\n', '',
     'Pinned To is keyed', 'tests/test_ik_end.py'),
    ('src/io/oanim_file.cc', '          put_keys(cj, "pin_keys", c.pin_keys);\n', '',
     "Pinned To's keys are saved", 'tests/test_ik_end.py'),
    ('src/io/oanim_file.cc', '                     {"pin", num(c.pin)},\n', '                     {"pin", num(IK_PIN_NONE)},\n',
     'Pinned To is saved', 'tests/test_ik_end.py'),
    # IK Ends and IK Bases (stage 3: moving IK points by hand, holds).
    ('src/data/bones.cc', '  if (how.flip && chain.size() >= 2) {\n', '  if (false) {\n',
     'Flip Bend bends the chain the other way, its point staying', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '    goal = ik_soft_goal(base, goal, reach);\n', '    goal = goal + ik_soft_goal(base, goal, reach) * 0.0f;\n',
     'Soft draws a goal near full reach in', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '      root.scale.y *= want / now;\n', '      root.scale.y *= 1.0f + 0.0f * want / now;\n',
     'Alt stretches a chain out of reach', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  for (; more > 0; more--) {\n', '  for (; more > 0 && false; more--) {\n',
     'a drag can bend one bone more than up to the base', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '    /* Pinned ends and bases the move left alone stay where they were. */\n    armature_ik_hold(armature, original, armature.bones.size(), BoneConstraintType::IKEnd, stretch);\n', '',
     'moving bones keeps pinned ends outside the moved chain put', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '      goal = ik_fk_pose(armature)[size_t(h.on)].pose.apply(h.local);\n', '      goal = h.place + h.local * 0.0f;\n',
     'a held end pinned to a bone rides that bone', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '    x.scale = setup_value(x.scale_keys, x.scale, false) + x.scale_keys.from_action_bones;\n', '    (void)x;\n',
     'Clear Chain Scale puts the chain back to its size', 'tests/test_ik_end.py'),
    # IK Ends and IK Bases, stage 4: bent paths.
    ('src/data/bones.cc', '    goal += bump;\n', '    goal += bump * 0.0f;\n',
     'an IK End path bends out by its bend, most at the middle', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '      goal = poses[pp.end].tail;\n', '      (void)0;\n',
     'an unpinned IK End path bends off the keys\' own way', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '          (!c.pin_keys.animated() && c.pin == IK_PIN_NONE && !c.bend_keys.animated()))\n',
     '          (!c.pin_keys.animated() && c.pin == IK_PIN_NONE))\n',
     'an unpinned IK End with a bent path is worked out', 'tests/test_ik_end.py'),
    ('src/anim/channel.cc', '  if (on_key_only) {\n', '  if (false && on_key_only) {\n',
     'an IK End bend is read on its key only, a stretch after it straight', 'tests/test_ik_end.py'),
    ('src/anim/animation.cc', '  return ch.on_key_only && value == T{} && !ch.key_at(frame);\n',
     '  return false && ch.on_key_only && value == T{} && !ch.key_at(frame);\n',
     'keying a whole bone keys no bend where there is none', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '    c->bend_keys.remove_key(k0);\n', '    c->bend_keys.set_key(k0, bend);\n',
     'a straightened IK End path keeps no bend key', 'tests/test_ik_end.py'),
    # IK Ends and IK Bases, stage 5: stretching, clears, end distance, Limit Angle ends.
    ('src/data/bones.cc', '        position.x = position.x > 0.5f * l ? l + (position.x - l) / r : position.x / r;\n', '        (void)0;\n',
     "a stretched bone's children keep their distance from its nearer end", 'tests/test_ik_end.py'),
    ('src/io/oanim_file.cc', '    b.keep_end_distance = get_bool(bj, "end_distance", false);\n', '    b.keep_end_distance = get_bool(bj, "end_distance", true);\n',
     "an older file's bones spread with a stretch, as they did", 'tests/test_ik_end.py'),
    ('src/ops/rig_ops.cc', '                   bone->keep_end_distance = keep;\n', '                   (void)keep;\n',
     'Keep End Distance turned off: the child spreads with the stretch', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '        b.scale.y *= length(d) / now;\n', '        (void)now;\n',
     "Alt on a bone's tip stretches it to the mouse", 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '          p->scale.y *= want / now;\n', '          (void)want;\n',
     "Alt on a connected bone's body: the parent stretches to reach it", 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '    how.stretch = stretch;\n', '    (void)stretch;\n',
     'Alt moving the root: pinned chains stretch to hold', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '                       [&](size_t j) { return armature.bones[j].scale != original[j].scale; }))\n',
     '                       [&](size_t) { return false; }))\n',
     'Alt S on a pinned chain reaches back to the pin', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  v = max ? std::max(v, c.min_angle + 0.05f) : std::min(v, c.max_angle - 0.05f);\n', '  (void)0;\n',
     'a Limit Angle end is kept short of the other', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  float v = end + wrap_pi(std::atan2(d.y, d.x) - armature_limit_zero(armature, poses, i, setup_frame) - end);\n', '  float v = wrap_pi(std::atan2(d.y, d.x) - armature_limit_zero(armature, poses, i, setup_frame));\n',
     'a Limit Angle end turns the nearest way round from where it is', 'tests/test_ik_end.py'),
    ('src/data/bones.cc', '  return bone_parent_axes_angle(bone, parent, setup_frame) + bone.setup_angle;\n', '  (void)parent;\n  return bone.setup_angle;\n',
     "a Limit Angle's arc is measured from its parent's axes", 'tests/test_ik_end.py'),
    # IK Ends and IK Bases, stage 6: a drawing's right-click on a bone extends its chain.
    ('src/anim/bone_curve.cc', '    top = to;\n', '    (void)0;\n',
     "a drawing's chain extended above its Parent Bone starts there", 'tests/test_bendy_bones.py'),
    ('src/anim/bone_curve.cc', '    end = to;\n', '    (void)0;\n',
     "a drawing's chain extended below its end ends there", 'tests/test_bendy_bones.py'),
    ('src/ops/rig_ops.cc', '                   set_chain = true;\n', '                   (void)0;\n',
     "Extend To sets the drawing's chain", 'tests/test_bendy_bones.py'),
    # The old IK constraint removed: loops through an IK End's chain.
    ('src/anim/follow_point.cc', '        grew |= add(b.id);\n', '        (void)0;\n',
     "a shape moved by an IK End's chain is a loop for that end's bone", 'tests/test_shape_loop.py'),
    # Bendy Bones a toggle, in its own panel.
    ('src/anim/bone_curve.cc', '  return bone.bendy && bone_curve_able(bone);\n', '  return bone_curve_able(bone);\n',
     'a bone with Bendy Bones off is straight', 'tests/test_bendy_bones.py'),
    ('src/ops/rig_ops.cc', '                   bent += armature && layer_curve_bones_bendy(*layer_find(doc, armature->id), *layer) ? 1 : 0;\n', '                   (void)armature;\n',
     "Deform: Curve turns Bendy Bones on for the chain's bones", 'tests/test_bendy_bones.py'),
    ('src/io/oanim_file.cc', '    b.bendy = g_loading_version < 10 ? bent : get_bool(bj, "bendy", false);\n', '    (void)bent;\n    b.bendy = get_bool(bj, "bendy", false);\n',
     'a bent or keyed bone in a file from before opens bendy', 'tests/test_bendy_bones.py'),
    ('src/io/oanim_file.cc', '        layer_curve_bones_bendy(*layer_find(doc, armature->id), *layer);\n', '        (void)armature;\n',
     "a file from before's Deform: Curve drawing's bones open bendy", 'tests/test_bendy_bones.py'),
    ('src/anim/animation.cc', '  if (bone_curve_listed(bone)) {\n    bone_curve_channels(bone, [&](std::string_view, float &value, Channel<float> &keys) { f(keys, value); });', '  if (bone_curve_listed(bone) || true) {\n    bone_curve_channels(bone, [&](std::string_view, float &value, Channel<float> &keys) { f(keys, value); });',
     'a straight bone keys no curve', 'tests/test_bendy_bones.py'),
    ('src/anim/bone_curve.cc', '      return true;\n    }\n    x = chain_parent(armature, size_t(x));', '      return true;\n    }\n    x = bone_curve_parent(armature, size_t(x));',
     "a drawing's chain runs on through straight bones", 'tests/test_bendy_bones.py'),
    # The Select tool drags bones as the IK mockup does (armature_bone_drag; an Alt press handed over from the layer pick).
    ('src/editors/viewport.cc', '  if (hit.hit.part == BonePart::Body && select_press_grab(C, view, mouse, false).layer) {\n', '  if (false && hit.hit.part == BonePart::Body && select_press_grab(C, view, mouse, false).layer) {\n',
     "a point over a bone's body takes the press, not the bone", 'tests/test_bone_drag.py'),
    ('src/editors/viewport.cc', '      if (tail_d <= reach && tail_d <= head_d) {\n        press.part = BoneDragPart::Tip;', '      if (false && tail_d <= reach && tail_d <= head_d) {\n        press.part = BoneDragPart::Tip;',
     'posing, a press on a tip drags the tip', 'tests/test_bone_drag.py'),
    ('src/editors/viewport.cc', '      else if (head_d <= reach && !bone->connected) {\n        press.part = BoneDragPart::Head;', '      else if (false && head_d <= reach && !bone->connected) {\n        press.part = BoneDragPart::Head;',
     "a loose bone's head pressed drags the head", 'tests/test_bone_drag.py'),
    ('src/editors/viewport.cc', '  if (!picked) {\n    family_and_points_deselect(C, doc, armature);', '  if (false) {\n    family_and_points_deselect(C, doc, armature);',
     'an unpicked bone pressed and dragged is picked alone first', 'tests/test_bone_drag.py'),
    ('src/editors/viewport.cc', '  return C.wm->tool_settings.tool == Tool::Select && bone_press_drag_begin(C, area, armature, view, start);', '  return false && bone_press_drag_begin(C, area, armature, view, start);',
     "an Alt press on a bone (a layer pick's) that moves becomes the bone's drag", 'tests/test_bone_drag.py'),
    ('src/data/bones.cc', '    if (!grow) {\n      const float2 way = goal - now[k].head;', '    if (false) {\n      const float2 way = goal - now[k].head;',
     "a plain drag under a stretched parent keeps the bone's length", 'tests/test_bone_drag.py'),
    ('src/data/bones.cc', '      if (stretch) {\n        /* Its connected children keep their tips', '      if (false) {\n        /* Its connected children keep their tips',
     'Alt on a tip: its connected child keeps its tip, the rest stay', 'tests/test_bone_drag.py'),
    ('src/data/bones.cc', '      if (stretch && b.connected && parent && !parent->outer_carried', '      if (false && b.connected && parent && !parent->outer_carried',
     "Alt on a connected bone's body moves it whole, its parent reaching", 'tests/test_bone_drag.py'),
    ('src/data/bones.cc', '          if (stretch) {\n            for (const size_t c : children(index)) {\n              carried(', '          if (false) {\n            for (const size_t c : children(index)) {\n              carried(',
     'Alt on a body: its children carried as one piece, not stretched', 'tests/test_bone_drag.py'),
    ('src/data/bones.cc', '      if (!stretch || b.connected) {\n        b.position +=', '      if (true) {\n        b.position +=',
     'Alt on a loose head moves the head alone', 'tests/test_bone_drag.py'),
    ('src/editors/viewport.cc', '    if (!bone || doc.frame_current == 0 || std::find(family.begin(), family.end(), owner) == family.end()) {', '    if (!bone || std::find(family.begin(), family.end(), owner) == family.end()) {',
     'armature.bone_drag only poses (not the setup frame)', 'tests/test_bone_drag.py'),
    # Attached To (Body, Head, Tail) and Turn on a layer's Parent Bone (bone_follow_skin).
    ('src/data/bones.cc', '  const Bone *b = attach == BoneAttach::Body ? nullptr : bone_find(armature, bone.id);', '  const Bone *b = nullptr;',
     'Attached To Head or Tail: the layer follows only that end, never squashed', 'tests/test_bone_attach.py'),
    ('src/data/bones.cc', '  if (turn != BoneAttachTurn::None) {\n    angle = turned(bone, *b);', '  if (true) {\n    angle = turned(bone, *b);',
     'Turn Never: an attached layer keeps its angle', 'tests/test_bone_attach.py'),
    ('src/data/bones.cc', '      if (op) {\n        angle += 0.5f * wrap_pi(', '      if (false && op) {\n        angle += 0.5f * wrap_pi(',
     'Turn Halfway: half the bend at a connected joint', 'tests/test_bone_attach.py'),
    ('src/data/bones.cc', '        other = b->connected && b->parent != b->id ? bone_find(armature, b->parent) : nullptr;', '        other = nullptr;',
     'Turn Halfway at a head: with its connected parent', 'tests/test_bone_attach.py'),
    ('src/data/layer.hh', '    return parent_bone != 0 && parent_bone_points && !attached_to_end() && !is_group() &&', '    return parent_bone != 0 && parent_bone_points && !is_group() &&',
     'attached to an end, Deform Points still moves the layer as a whole', 'tests/test_bone_attach.py'),
    ('src/ops/rig_ops.cc', '                   if (!regular && layer->parent_bone_attach != BoneAttach::Body) {', '                   if (false && !regular && layer->parent_bone_attach != BoneAttach::Body) {',
     'a pin made the Parent Bone lets go of Attached To', 'tests/test_bone_attach.py'),
    ('src/ops/rig_ops.cc', 'const Transform2D skin = bone_follow_skin(*armature, change, *p, layer->parent_bone_attach, layer->parent_bone_turn);', 'const Transform2D skin = p->skin;',
     'Apply Pose as Rest moves an attached layer as its end moved', 'tests/test_bone_attach.py'),
    ('src/io/oanim_file.cc', '  if (layer.parent_bone_attach != BoneAttach::Body) {\n    j["parent_bone_attach"]', '  if (false) {\n    j["parent_bone_attach"]',
     'Attached To saved', 'tests/test_bone_attach.py'),
    # A stretch stays with its bone (BonePose::carry; IK stretches the whole chain).
    ('src/data/bones.cc', '      p.carry = unstretched(p.pose, p.stretch, scale.x * sy / setup_scale.x, scale.x / setup_scale.x);', '      p.carry = p.pose;',
     'a stretch stays with its bone: what hangs from it is not stretched or skewed', 'tests/test_bone_stretch.py'),
    ('src/data/bones.cc', '      for (const int j : chain) {\n        armature.bones[size_t(j)].scale.y *= want / now;', '      for (const int j : {chain.back()}) {\n        armature.bones[size_t(j)].scale.y *= want / now;',
     'an IK stretch lengthens every bone of the chain', 'tests/test_bone_stretch.py'),
    ('src/data/bones.cc', '  const Transform2D now = knob ? parent->knob : setup_frame ? parent->pose : parent->carry;', '  const Transform2D now = knob ? parent->knob : parent->pose;',
     'G on a tip under a stretched parent: it points where it is taken', 'tests/test_bone_stretch.py'),
    ('src/data/bones.cc', "    /* Its length's and width's scale (constraints, IK and Maintain Volume included) each brought to its keyed width's,\n     * for what hangs from it. */\n    if (setup_frame || rests ||", "    /* Its length's and width's scale (constraints, IK and Maintain Volume included) each brought to its keyed width's,\n     * for what hangs from it. */\n    if (true || setup_frame || rests ||",
     "a bone's size all over still passes down", 'tests/test_bone_stretch.py'),
    # A group's Deform bends every drawing inside; Curve from a bone's head or tail never stretches.
    ('src/anim/bone_curve.cc', '  const float s_now = from == BoneAttach::Head   ? s', '  const float s_now = false   ? s',
     'Head + Curve: as far from the head as it was', 'tests/test_bone_group_deform.py'),
    ('src/anim/bone_curve.cc', '                      : from == BoneAttach::Tail ? now.along.back() - (rest.along.back() - s)', '                      : false ? now.along.back() - (rest.along.back() - s)',
     'Tail + Curve: as far back from the tip', 'tests/test_bone_group_deform.py'),
    ('src/anim/deform.cc', '  r.curve_from = by.end_curve() ? by.parent_bone_attach : BoneAttach::Body;', '  r.curve_from = BoneAttach::Body;',
     "the drawing's end is what its curve is measured from", 'tests/test_bone_group_deform.py'),
    ('src/anim/deform.cc', '  const Layer &by = layer_bone_binder(doc, layer);', '  const Layer &by = layer;',
     "a group's Points and Curve bend every drawing inside, its bone overriding theirs", 'tests/test_bone_group_deform.py'),
    ('src/data/document_layers.cc', '  return binder->points_follow_bone() && !layer.is_group() && !layer.has_drawing() ? binder : nullptr;', '  return nullptr;',
     'a picture inside a bending group rides the bone whole', 'tests/test_bone_group_deform.py'),
    ('src/data/document_layers.cc', '  return armature && layer.is_group() && layer.parent_bone != 0 && !(layer.is_reference() && layer.reference.match_original)', '  return armature && layer.is_group() && layer.followed_bone() != 0 && !(layer.is_reference() && layer.reference.match_original)',
     'a bending group still overrides the Parent Bone of a drawing inside', 'tests/test_bone_group_deform.py'),
    ('src/ops/rig_ops.cc', '                     if (layer->is_group() && layer->parent_bone == 0) {', '                     if (false && layer->is_group() && layer->parent_bone == 0) {',
     'a group given a Parent Bone starts as Layer', 'tests/test_bone_group_deform.py'),
    ('src/io/oanim_file.cc', '  if (g_loading_version < 11 && layer.is_group()) {', '  if (false && g_loading_version < 11 && layer.is_group()) {',
     'a group from an older file opens as Layer', 'tests/test_bone_group_deform.py'),
    ('src/ops/rig_ops.cc', '                   if (deform == "RIGID") {', '                   if (false && deform == "RIGID") {',
     'Rigid only at an end', 'tests/test_bone_group_deform.py'),
    ('src/data/layer.hh', '    return parent_bone != 0 && parent_bone_points && (!attached_to_end() || parent_bone_curve) &&', '    return parent_bone != 0 && parent_bone_points && !attached_to_end() &&',
     'an end with Curve bends its points', 'tests/test_bone_group_deform.py'),
    ('src/data/layer.hh', '    return parent_bone != 0 && parent_bone_points && (!attached_to_end() || parent_bone_curve) &&', '    return parent_bone != 0 && parent_bone_points && (!attached_to_end() || parent_bone_curve) && !is_group() &&',
     "a group's Deform counts", 'tests/test_bone_group_deform.py'),
    # A handle dragged on a drawing bent by a Cage Deform, at the cage's corner.
    ('src/anim/deform.cc', '  if (!fitted) {\n    handles_settle_bent(doc, layer, targets);\n    return;\n  }\n',
     '  if (false && !fitted) {\n    handles_settle_bent(doc, layer, targets);\n    return;\n  }\n',
     'a handle dragged at a cage corner lands where it is taken', 'tests/test_deform_handle_drag_corner.py'),
    ('src/anim/deform.cc', '      const float grow = std::clamp(want_len / shown_len, 0.25f, 4.0f);\n',
     '      const float grow = 1.0f + 0.0f * want_len;\n',
     'the handle grows by how much longer it should show', 'tests/test_deform_handle_drag_corner.py'),
    ('src/anim/deform.cc', 'if (g_resample_left_out != layer.id) {', 'if (true || g_resample_left_out != layer.id) {',
     'with a Resample first, the handles settle against the drawing\'s own, bent', 'tests/test_deform_handle_drag_corner.py'),
    ('src/editors/viewport.cc', '        if (!deformed || fitted) {\n          continue;\n        }\n        if (!own) {\n',
     '        if (true || !deformed || fitted) {\n          continue;\n        }\n        if (!own) {\n',
     'with a Resample first, the handles shown are the drawing\'s own, bent at their points', 'tests/test_deform_handle_drag_corner.py'),
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
