#pragma once

/* The Fill Pen and Fill Eraser: growing the shape a stroke starts on by a brushed area, and cutting one out of it.
 *
 * Both work the area into that shape as the shape tree's Apply does (Clipper2 on its outline and the area): the points
 * its outline still runs through stay, with their keys, and new ones fitted to Bezier curves go in only where it
 * changed. */

#include <vector>

#include "data/fill_area.hh"

namespace oanim {

/* The shape a Fill Pen or Fill Eraser stroke starting at `start` (layer space) works on: the top shown one it starts
 * inside (its own outline, a sub shape's too) or on the line of (within `reach`, or the line's half width), -1 for
 * none. */
int drawing_fill_start_shape(const VectorDrawing &drawing, float2 start, float reach);

/* The Fill Pen: grows the fill of the shape the stroke starts on by `area` (layer space), that shape keeping its points
 * where its outline doesn't change and its line following the new outline, and gaining a fill in `style`'s colour if
 * it had none (a line that doesn't go round takes the area in as a loop of its own). Started on nothing, a new shape
 * on top. `pixel`: layer units a screen pixel stands for; `tolerance`: how far (screen pixels) new curves may be off. */
void drawing_fill_paint(VectorDrawing &drawing, const std::vector<FillPiece> &area, const Style &style, float pixel,
                        float tolerance, float2 start);

/* The Fill Eraser: cuts `area` out of the fill of the shape the stroke starts on (`selected_only`: if it is selected),
 * keeping its points where its outline doesn't change; all of it cut, it goes. False: nothing was cut. */
bool drawing_fill_erase(VectorDrawing &drawing, const std::vector<FillPiece> &area, float pixel, float tolerance,
                        float2 start, bool selected_only);

}  // namespace oanim
