#pragma once

/* The pose library (the Asset Shelf's Poses): poses kept in the file (Document::poses), each Copy Pose's record of the
 * bones and points selected when it was saved, under a name and a collection. Its rows are the collections the
 * selection is in (every collection with poses while nothing is selected); a click puts the pose back on the frame
 * shown. Operators poselib.*. */

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "core/math.hh"
#include "data/document.hh"

namespace oanim {

struct Context;

void pose_library_operators_register();

PoseAsset *pose_asset_find(Document &doc, uint64_t id);
const PoseAsset *pose_asset_find(const Document &doc, uint64_t id);
/* The document's collections the selected bones and drawings (those whose points are selected) are in, in the order
 * of the document's collections. */
std::vector<uint64_t> pose_selection_collections(Context &C);

/* A row of the shelf's Poses: a collection (0: Unsorted, for poses whose collection is gone) and its poses, in the
 * order they were saved. */
struct PoseShelfRow {
  uint64_t collection = 0;
  std::string name;
  std::vector<uint64_t> poses;
};
/* While something is selected, a row for each collection it is in that has poses; else every
 * collection with poses, and Unsorted. `search` keeps the poses whose name holds it (any case), and the rows with any.
 * `collections` (pinned rows): those collections' rows instead (0 Unsorted), whatever is selected. */
std::vector<PoseShelfRow> pose_shelf_rows(Context &C, const std::string &search,
                                          const std::vector<uint64_t> *collections = nullptr);

/* A copy of `doc` with the pose put on (on frame 0, where poses don't go, on frame 1), for its thumbnail: nothing in
 * `doc` changes. The box (document space) of what it moves from the setup pose (all of the character when nothing),
 * and the layers to show (the bone layer and the drawings outside it). False when none of its bones and points is in
 * the file. */
bool pose_posed_copy(const Document &doc, const PoseAsset &pose, Document &r_copy, float2 *r_lo, float2 *r_hi,
                     std::vector<uint64_t> *r_layers, std::vector<std::pair<uint64_t, size_t>> *r_framed = nullptr);

/* A thumbnail's frame (a square: its middle and side) round the box `lo`..`hi`, with room around. */
void pose_frame_round(float2 lo, float2 hi, float2 *r_center, float *r_size);
/* Where every drawing's points show (document space) and their ids, by layer. */
struct PointsShown {
  std::map<uint64_t, std::vector<float2>> at;
  std::map<uint64_t, std::vector<uint64_t>> ids;
};
PointsShown pose_points_shown(const Document &doc);
/* Where pose's given frame comes to with its points showing as in `shown` (holding them as it did when framed, grown to
 * hold them all if they spread), or from `anchor` for one framed on no points. False: none given, or none of its
 * points shows. */
bool pose_frame_place(const PoseAsset &pose, const PointsShown &shown, float2 anchor, float2 *r_center, float *r_size);
/* Frame `r_pose` on the square `center`, `size` as `doc` shows now (`shown`): the points of the drawings its thumbnail
 * shows (`layers`, pose_posed_copy's) inside it are kept with it, the square kept from them (from `anchor` with none
 * inside). */
void pose_frame_capture(const Document &doc, const PointsShown &shown, const std::vector<uint64_t> &layers, float2 anchor,
                        float2 center, float size, PoseAsset &r_pose);
/* The frame pose's thumbnail is drawn in, `posed` its posed copy and `lo`..`hi` the box of what it moves there: the one
 * it was given (pose_frame_place), else round that. */
void pose_frame_choose(const Document &posed, const PoseAsset &pose, float2 lo, float2 hi, float2 *r_center,
                       float *r_size);
/* The same worked out from a posed copy (pose_posed_copy); false when none of its bones and points is in the file. */
bool pose_thumbnail_frame(const Document &doc, const PoseAsset &pose, float2 *r_center, float *r_size);
/* Where the middle of what pose moves (pose_posed_copy's box) shows in `doc` now, which its frame is kept from (it
 * follows them to another frame, or the character moved), and the side of the frame round them. False when none of
 * its bones and points is in the file. */
bool pose_frame_anchor(const Document &doc, const PoseAsset &pose, float2 *r_anchor, float *r_auto_size,
                       std::vector<uint64_t> *r_layers = nullptr);
/* The same for the selected bones' and points' pose now: what Save Pose's frame is kept from. */
bool pose_frame_anchor_of_selection(Context &C, float2 *r_anchor, float *r_auto_size,
                                    std::vector<uint64_t> *r_layers = nullptr);
/* The selected bones' and points' pose now, as a pose (no name or id). */
PoseAsset pose_of_selection(Context &C);

}  // namespace oanim
