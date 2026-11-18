#pragma once

/* Thumbnails of the pose library's poses, for the Asset Shelf's Poses: the bone layer (or drawings) the pose was saved
 * from with it put on, from a posed copy (ops/pose_library.hh), framed on the bones and points it holds. Kept until the
 * document, the frame, the pose or the size changes; drawn again once the document has been still a moment, one a
 * frame, the rest showing their last picture till their turn. */

#include <cstdint>

#include "core/math.hh"

namespace oanim {

struct Document;
struct PoseAsset;
struct Context;

/* The pose's thumbnail, `size` pixels square: an OpenGL texture (straight alpha), 0 until drawn, without OpenGL
 * (background runs) or when none of its bones and points is in the file. */
unsigned int pose_thumbnail(Document &doc, const PoseAsset &pose, int size);

/* The thumbnail's frame (document space, a square: its middle and side) the viewport shows while the Save Pose dialog
 * or Edit Frame is open (editors/asset_shelf.cc); false while neither is. Setting it (dragged in the viewport) keeps it
 * from fitting the pose. */
bool pose_frame_shown(Context &C, float2 *r_center, float *r_size);
void pose_frame_shown_set(Context &C, float2 center, float size);
/* Test hooks: opens Save Pose (`pose` 0) or Edit Frame for pose `pose`, as the shelf does (-1 closes it); and a press
 * at `from` dragged to `to` (document space) on the frame, a corner within `reach` (viewport.cc). */
void pose_frame_dialog_test(Context &C, int64_t pose);
bool pose_frame_drag_test(Context &C, float2 from, float2 to, float reach);

}  // namespace oanim
