#pragma once

/* Thumbnails of the pose library's poses, for the Asset Shelf's Poses: the bone layer (or drawings) the pose was saved
 * from with it put on, from a posed copy (ops/pose_library.hh), framed on the bones and points it holds. Kept until the
 * document, the frame, the pose or the size changes; drawn again once the document has been still a moment, one a
 * frame, the rest showing their last picture till their turn. */

namespace oanim {

struct Document;
struct PoseAsset;

/* The pose's thumbnail, `size` pixels square: an OpenGL texture (straight alpha), 0 until drawn, without OpenGL
 * (background runs) or when none of its bones and points is in the file. */
unsigned int pose_thumbnail(Document &doc, const PoseAsset &pose, int size);

}  // namespace oanim
