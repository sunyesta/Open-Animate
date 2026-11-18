#pragma once

/* The pose library (the Asset Shelf's Poses): poses kept in the file (Document::poses), each Copy Pose's record of the
 * bones and points selected when it was saved, under a name and a collection. Its rows are the collections the
 * selection is in (every collection with poses while nothing is selected); a click puts the pose back on the frame
 * shown. Operators poselib.*. */

#include <cstdint>
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
                     std::vector<uint64_t> *r_layers);

/* A thumbnail's frame (a square: its middle and side) round the box `lo`..`hi`, with room around. */
void pose_frame_round(float2 lo, float2 hi, float2 *r_center, float *r_size);
/* The frame pose's thumbnail is drawn in, `lo`..`hi` the box of what it moves: the one it was given, else round that. */
void pose_frame_choose(const PoseAsset &pose, float2 lo, float2 hi, float2 *r_center, float *r_size);
/* The same worked out from a posed copy (pose_posed_copy); false when none of its bones and points is in the file. */
bool pose_thumbnail_frame(const Document &doc, const PoseAsset &pose, float2 *r_center, float *r_size);
/* The frame a pose's thumbnail gets on its own (round what it moves, pose_posed_copy), whatever frame it was given. */
bool pose_frame_auto(const Document &doc, const PoseAsset &pose, float2 *r_center, float *r_size);
/* The same for the selected bones' and points' pose now: what Save Pose's frame starts as. */
bool pose_frame_of_selection(Context &C, float2 *r_center, float *r_size);

}  // namespace oanim
