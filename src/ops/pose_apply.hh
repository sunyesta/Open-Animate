#pragma once

/* Recording a pose and putting one back (ops/pose_clipboard.cc): what Copy Pose and Paste Pose do, shared with the
 * Asset Shelf's pose library (ops/pose_library.cc), which keeps poses in the file. */

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "ops/operator.hh"

namespace oanim {

struct Context;
struct Document;
struct Layer;

/* What a paste gives: the keys (what the actions here add coming on top), the look, or the place it showed. */
enum class PasteAs { Keys, Look, Place };

struct PoseApplyOptions {
  PasteAs as = PasteAs::Keys;
  /* The shape only: the pasted points' centre stays where it shows now (not with Same Place). */
  bool keep_place = false;
  /* Onto the bones and points selected now among the pose's (all of them when none is). */
  bool selected_only = false;
  /* How far from the pose shown to the one put back (0.5: halfway). */
  float factor = 1.0f;
  /* No note or report of what it did. */
  bool quiet = false;
  /* Warnings when it can't (a pose's thumbnail makes none). */
  bool warn = true;
  /* The bone layer and drawings found anywhere in the document (by id, else name), not only the ones being edited: a
   * pose kept in the file goes back on what it was saved from whatever is active. */
  bool anywhere = false;
  /* Filled with what it posed: (bone layer, bone id) and (drawing, point index). */
  std::vector<std::pair<uint64_t, uint64_t>> *r_bones = nullptr;
  std::vector<std::pair<uint64_t, size_t>> *r_points = nullptr;
};

/* The bone layer active (or null), and the bone layers whose selected bones Copy Pose takes: it and those worked in
 * together with it (its sub bone groups, whose bones are clicked with its own: the teeth's in a mouth), and the
 * drawings whose selected points it takes (those being edited). */
Layer *pose_rig(Context &C);
std::vector<Layer *> pose_rigs(Context &C);
std::vector<Layer *> pose_drawings(Context &C);
/* Whether anything Copy Pose takes is selected: bones of pose_rigs(), points of the drawings being edited. */
bool pose_anything_selected(Context &C);
/* The selected bones' and points' pose on the frame shown (Copy Pose's record). */
nlohmann::ordered_json pose_copy_json(Context &C, int *r_bones, int *r_points);
/* The same for bone layers `rigs` and `drawings`, their selected bones and points. */
nlohmann::ordered_json pose_record(Document &doc, const std::vector<Layer *> &rigs, const std::vector<Layer *> &drawings,
                                   int *r_bones, int *r_points);
/* Puts a recorded pose back on the frame shown (flipped: mirrored left to right). Cancelled on frame 0, or when none of
 * its bones and points is here. */
OpStatus pose_apply(Context &C, const nlohmann::ordered_json &pose, bool flipped, const PoseApplyOptions &options);

}  // namespace oanim
