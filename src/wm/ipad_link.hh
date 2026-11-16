#pragma once

/* Draw on iPad's side in Open Animate (the server is wm/ipad_server.hh; the messages are oanim.ipad's): the canvas
 * the iPad shows, and its Pencil's strokes drawn by this side's own Stroke Pen, so a line drawn on the iPad is the
 * line the viewport would make of the same hand.
 *
 * The iPad's canvas is the camera's frame as Render Frame draws it, `width` x `height` pixels, y down: its points
 * come in in those pixels and go back the same way. */

#include <cstdint>
#include <string>
#include <vector>

#include "core/math.hh"

namespace oanim {

struct Context;
struct Document;

/* Document space to the canvas's pixels. */
Transform2D ipad_canvas_transform(const Document &doc, int width, int height);

/* The canvas as a message: {"t":"canvas","w","h","svg","frame","onion":[{"c":[r,g,b,a],"lines":[[x,y,...],...]}]},
 * the onion skins being the viewport's (the drawings being edited, on the frames around). */
std::string ipad_canvas_message(Context &C, int width, int height);

/* One of the Pencil's samples: canvas pixels, pressure 0-1, tilt in degrees (across, up), seconds. */
struct IpadSample {
  float x = 0.0f, y = 0.0f;
  float pressure = 1.0f;
  float tilt_x = 0.0f, tilt_y = 0.0f;
  double time = 0.0;
};

/* Why the iPad can't draw now ("" when it can): as the viewport, only with the Draw tool, on the setup frame, on a
 * drawing being edited, and with a pen that draws by dragging. */
std::string ipad_draw_refused(Context &C);
/* Starts a stroke as the viewport's press does: the pen, or its eraser end (`eraser`) as Ctrl does. `zoom` is the
 * iPad's screen pixels per canvas pixel, so a pen sized on screen is that size on the iPad. "" when started, else
 * why not. */
std::string ipad_stroke_begin(Context &C, int width, int height, float zoom, bool eraser);
/* Adds samples, and gives the message showing the line as it now stands ("" with no stroke): what changed since the
 * last, {"t":"live","kind":"line"|"dabs",...}. */
std::string ipad_stroke_add(Context &C, const std::vector<IpadSample> &samples);
/* Ends it as the viewport's release does: the undo step's name it made ("Draw", "Erase Line", ...), "" for none. */
std::string ipad_stroke_end(Context &C);
void ipad_stroke_cancel();
bool ipad_stroke_active();
/* The brush images sent so far are forgotten (a page connecting has none of them). */
void ipad_images_reset();

/* The Draw shelf's tiles, `size` pixels square, for every pen: [{"name","rects","strokes","dots"}, ...]. */
std::string ipad_tiles_json(Context &C, float size);
/* The brush button's picture: the line brush along a short line `width` x `height` pixels, as a "live" message's
 * body ({"kind":"line"|"dabs",...}). */
std::string ipad_brush_preview_json(Context &C, float width, float height);
/* Gives the Draw tool's line the brush shape `name` ("" plain), its other brush settings as they are. */
void ipad_brush_shape_set(Context &C, const std::string &name);

/* Each frame, from the main loop: the pages' messages handled (oanim.ipad). */
void ipad_process(Context &C);

/* wm.ipad_draw_start and wm.ipad_draw_stop. */
void ipad_operators_register();
/* The Draw on iPad window (Window > Draw on iPad...): the QR code to scan, the address, who is connected, Stop. */
bool ipad_window_shown();
void ipad_window_draw(Context &C);
/* The port the server asks for first. */
inline constexpr int IPAD_PORT = 8765;

}  // namespace oanim
