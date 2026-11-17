#pragma once

#include <map>

/* Editor types and areas. An area is one dockable panel of the window showing one
 * editor, like Blender's ScrArea + SpaceType. Splitting and joining areas uses ImGui
 * docking: drag an area's tab onto another area. */

#include <cstdint>
#include <functional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "anim/path_brush.hh"
#include "data/document.hh"
#include "anim/sculpt.hh"
#include "editors/tool_shelf.hh"

struct ImDrawList;
struct ImVec2;

namespace oanim {

struct Context;
struct Document;
struct BoneFixKnobLine;
struct Bone;

enum class EditorType { Viewport, Properties, Layers, Timeline, TextEditor, Console, Info, AssetShelf, PathTiming };

inline constexpr EditorType EDITOR_TYPES[] = {EditorType::Viewport,   EditorType::Properties, EditorType::Layers,
                                              EditorType::Timeline,   EditorType::PathTiming, EditorType::AssetShelf,
                                              EditorType::TextEditor, EditorType::Console,    EditorType::Info};

const char *editor_type_label(EditorType type);
/* Name of the editor's keymap, tried before "Window" while the mouse is over it. */
const char *editor_keymap_name(EditorType type);

enum class AreaSplit { None, Vertical, Horizontal };

struct Area {
  int id = 0;
  EditorType type = EditorType::Viewport;
  bool open = true;
  /* Set from the area menu; the app splits the area at the start of the next frame. */
  AreaSplit split_request = AreaSplit::None;

  /* Timeline view: the frame range visible across the area. */
  float view_start = 0.0f;
  float view_end = 250.0f;
  bool view_initialized = false;
  /* Timeline: how far the channel rows are scrolled, in pixels (which folding rows are open is the
   * project's: Document::ui_open). */
  float channel_scroll = 0.0f;
  /* The names column's width, dragged by its edge (0: the default). */
  float timeline_names_w = 0.0f;

  /* Viewport view: the document point at the centre and pixels per document unit (the project
   * keeps a copy, Document::view, saved with it; `view_serial` is the project's view it took). */
  uint64_t view_serial = 0;
  float view_center_x = 0.0f;
  float view_center_y = 0.0f;
  float view_zoom = 0.0f;
  /* Until the user zooms or pans, the view keeps the camera framed as the area changes size
   * (the docking layout only settles a frame or two after startup). */
  bool view_navigated = false;
  float view_fit_width = 0.0f;
  float view_fit_height = 0.0f;

  /* Properties editor tab. */
  int properties_tab = 0;

  /* Layers editor: the layer being renamed, or 0. */
  uint64_t renaming_layer = 0;
  /* Layers editor: the last Show Active it took (WindowManager::layers_show_active_serial), and the
   * row it scrolled to, flashing since `show_active_time`. */
  uint64_t show_active_seen = 0;
  uint64_t show_active_layer = 0;
  double show_active_time = -10.0;
  /* Frames it still scrolls to that row: groups Show Active opened only make the list taller once drawn, and a scroll
   * can't go past the list's height of the frame before, so it goes on till the list has its full height. */
  int show_active_frames = 0;
  /* That scroll only brings the row into sight (Auto Focus): none when it is already in sight. */
  bool show_active_only_if_hidden = false;
  /* Layers editor, Auto Focus: the picked layers it last folded down to, active first. */
  std::vector<uint64_t> auto_focus_picked;
  /* Layers editor: list the drawing layers in this frame's draw order (top first), to reorder by
   * dragging, instead of the tree. */
  bool layers_draw_order_view = false;

  /* Viewport: the Sculpt and Draw tools' shelves along the bottom (Blender's asset shelf). Sculpt's tabs are 0 All,
   * 1 Move, 2 Shape, 3 Mine. */
  ShelfState sculpt_shelf;
  ShelfState draw_shelf;
  /* The Motion Path tool's brushes: 0 All, 1 Shape, 2 Speed. */
  ShelfState path_shelf;
  /* Viewport: the Tool Settings strip's width last frame (0: the tool has no settings), and how far it is
   * scrolled when it doesn't fit, in pixels. */
  float tool_settings_width = 0.0f;
  float tool_settings_scroll = 0.0f;

  /* Asset Shelf (asset_shelf.cc): the tab (0 Context, 1 All Switches), pinned and its rows (switch ids),
   * the rows that fitted last (kept while nothing fits), the search, the tiles' size and whether hovering
   * previews. */
  int shelf_tab = 0;
  bool shelf_pinned = false;
  std::vector<uint64_t> shelf_pins;
  std::vector<uint64_t> shelf_last;
  std::string shelf_search;
  float shelf_tile = 72.0f;
  bool shelf_hover_preview = true;
  /* Which of its sections shows: 0 Switches, 1 Poses (the pose library), 2 Actions. The Poses' search, and whether
   * its rows are pinned (collection ids, 0 Unsorted). */
  int shelf_section = 0;
  std::string shelf_pose_search;
  bool shelf_pose_pinned = false;
  std::vector<uint64_t> shelf_pose_pins;

  /* Text editor. */
  bool show_line_numbers = true;

  /* Console: the line being typed, the history entry shown, and the scrollback seen. */
  std::string console_input;
  int console_history_pos = -1;
  uint64_t console_seen_version = 0;

  /* ImGui window name: the label shows on the tab; "###area<id>" keeps the window's
   * identity when the editor type changes. */
  std::string window_name() const;
};

/* Draws the area as a dockable window. Returns true while the mouse is over it. */
bool area_draw(Area &area, Context &C);
/* The viewport's own operators (mesh.transform_selected). */
void viewport_operators_register();
/* The ViewportActionPanel checkboxes kept for the next moves until the frame or action changes. */
struct MoveOptions {
  bool keep_poses = false;
  bool only_bones = false;
  bool without_children = false;
};
MoveOptions viewport_move_options(const Document &doc);

/* Starts every area header: a grip to drag the area elsewhere (right-click for the area
 * menu), then the editor-type dropdown. */
void area_editor_type_menu(Area &area);

/* Viewport, in viewport.cc. */
void viewport_draw(Area &area, Context &C);
/* The Sculpt tool's brush shelf (sculpt_shelf.cc): how much of the viewport's height it takes (0 unless
 * Sculpt is the tool), drawn into the strip below the view. */
float sculpt_shelf_height(const Context &C, const Area &area);
void sculpt_shelf_draw(Context &C, Area &area, ImVec2 min, ImVec2 size);
/* The Draw tool's shelf (draw_shelf.cc): the same for Draw, and its pens in a popup ("##draw_presets", opened by the
 * caller); a line of varying width drawn with the stroke tessellator into an ImGui draw list. */
float draw_shelf_height(const Context &C, const Area &area);
void draw_shelf_draw(Context &C, Area &area, ImVec2 min, ImVec2 size);
void draw_presets_popup(Context &C);
/* The Motion Path tool's brush shelf (motion_path_shelf.cc), the same way. */
float path_shelf_height(const Context &C, const Area &area);
void path_shelf_draw(Context &C, Area &area, ImVec2 min, ImVec2 size);
/* A path brush's picture (the shelf's tiles). */
void path_brush_icon(ImDrawList *dl, PathBrush brush, ImVec2 center, float size, unsigned int col);
/* `opacity` (optional, one per point) fades it there, as a line's points' opacity does. */
void ink_line_draw(ImDrawList *dl, const std::vector<float2> &points, const std::vector<float> &half_widths, Color color,
                   const std::vector<float> *opacity = nullptr);
/* Fixes' lines in a knob's box (the viewport's and the Spots panel's), `at` taking frames to the screen: each fainter as
 * less of it plays, the edited one brighter, a dot where it plays. */
/* Whether a 2 Axis Controller's box shows in the viewport (Show Box), `picked` or not. */
bool controller_box_shown(const Document &doc, const Bone &bone, bool picked);
void bone_fix_lines_draw(ImDrawList *dl, const std::vector<BoneFixKnobLine> &lines,
                         const std::function<ImVec2(float2)> &at);
/* A sculpt brush's picture: a line before and after it (the shelf's tiles, the tool bar). */
void sculpt_brush_icon(ImDrawList *dl, SculptBrush brush, ImVec2 center, float size, unsigned int col,
                       unsigned int before);
/* Whether something is being moved in a viewport (G, R, S, W, a Transform tool's box). */
bool viewport_drag_active();
/* How the viewport draws (and picks) a bone: "PIN", "CUSTOM" (its Custom shape, a pin's too), "CONTROLLER" or "BONE". */
const char *viewport_bone_drawn_as(const Document &doc, const Bone &bone);
/* What a Collections row's Assign Selected (`assign`) or Unassign Selected would change ("2 bones, 1 drawing", "" for
 * nothing), on the rig its operators work on: `armature`, or the sub bone group being worked in. */
std::string collection_row_change_text(Document &doc, Layer &armature, uint64_t id, bool assign);
/* Whether the edit going on (a point move: G, R, S, Extrude, a handle tweak) says which layers it changes,
 * each update (see Revision); any other edit with the mouse down may change anything. */
bool viewport_precise_edit();
/* Whether a viewport is being panned or zoomed with the middle button (the view only, not a camera looked
 * through): it changes nothing in the document. */
bool viewport_navigating();
/* The frame moved on while playing during that drag: what it began from takes the keys just recorded
 * and, where it isn't holding anything, the new frame (animation_follow_playback). `dragged` is the
 * document as the drag had it before the frame changed. */
void viewport_drag_follow_playback(Document &dragged, Document &now);
/* Called every frame no drag is going on: forgets what the last one held. */
void viewport_drag_follow_forget();
/* For tests: where Ctrl puts a turn of `degrees` of the active bone layer's picked bones (R when `rotate_key`, else
 * the Transform Bones tool's turn), and what it snapped to ("45Â°", "start" or "setup"). */
float viewport_bone_turn_snap(Document &doc, float degrees, bool rotate_key, std::string *r_what);
/* Properties editor, in properties.cc. */
void properties_draw(Area &area, Context &C);
/* The Properties editor's tabs for what is active, in order (the labels shown). */
struct PropertiesTabEntry {
  const char *label;
  int id;
};
std::vector<PropertiesTabEntry> properties_tabs(Document &doc);
/* Affected By: what moves a field besides its own keys and value, in src/editors/driver_ui.cc: at the top of its right-click menu (and a timeline
 * row's). `kind`: "OWN" first where actions move it (`name` its own value and what it shows), then one row each for
 * "ACTION_BONE", "KNOB", "FIX", "ACTION" (one playing at its own Frame) and "DRIVER": `name` and `detail` as shown
 * ("jaw_open", "Mouth Open · 42%"), `layer`, `bone` and `action` where clicking it goes. */
struct AffectedRow {
  std::string kind, name, detail;
  uint64_t layer = 0;
  std::string bone, action;
};
std::vector<AffectedRow> ui_affected_rows(Document &doc, uint64_t layer, const std::string &path, int component);
/* How a field shows its drivers: 0 plain, 1 driven (purple, a two-way link's driven side too), 2 a driver that doesn't
 * work (red); `r_linked`: either side of a two-way link (the link icon in it). */
int ui_driver_field_look(Document &doc, uint64_t layer, const std::string &path, int component, bool *r_linked);
/* Whether a field has Affected By: every animatable property (a channel), whatever moves it. */
bool ui_affected_available(Document &doc, uint64_t layer, const std::string &path);
/* How many things move it (shown left of Affected By's arrow): its rows but the own value. */
int ui_affected_count(const std::vector<AffectedRow> &rows);
/* The empty submenu's line, naming what the field belongs to: "Nothing else moves this bone". */
std::string ui_affected_empty_text(const std::string &path);
/* "Moved by 2 action bones, 1 fix, 1 driver" (the field's tooltip), "" when nothing does. */
std::string ui_affected_summary(const std::vector<AffectedRow> &rows);
/* Goes where a row says: selects the action bone or knob (a fix's first bone, the fix picked in the Bone tab), a
 * bone layer for an action of its own, or opens the field's Driver window. */
void ui_affected_go(Context &C, uint64_t layer, const std::string &path, int component, const AffectedRow &row);
/* Shows the Bone tab (`fix`: with that fix picked in its Fix Actions) or, `bone` false, the Armature tab. */
void properties_show_bone(Context &C, uint64_t armature, bool bone, const std::string &fix = "");
/* Layers editor, in layers_editor.cc. */
void layers_draw(Area &area, Context &C);
/* Timeline editor, in timeline.cc. */
void timeline_draw(Area &area, Context &C);
/* Asset Shelf, in asset_shelf.cc. */
void asset_shelf_draw(Area &area, Context &C);
/* Path Timing: the Motion Path tool's timing graph for one stretch, in timeline_path.cc. */
void path_timing_draw(Area &area, Context &C);
/* The timeline's channel rows as a timeline with every row open lists them (for tests). */
struct TimelineRowInfo {
  int depth = 0;
  std::string name;
  /* Pinned, or a picked bone's or the selected points' (red). */
  bool red = false;
  /* A pinned property's row (with its pin). */
  bool pinned = false;
  /* A copy's (reference layer's) channel changed from its original (teal). */
  bool changed = false;
  /* A layer's own row: that layer's id (clicking its name makes it active); else 0. */
  uint64_t layer = 0;
  /* A folding row's key in the project's fold states ("Timeline/<fold>"), "" when it doesn't fold. */
  std::string fold;
  bool open = false;
  bool summary = false;
  /* As shown: "Summary / <name>" for a lone layer's row that is the Summary too, else the name. */
  std::string label;
  /* A group not shown itself, listed dimmed for the shown layers inside it. */
  bool dim = false;
  /* A folding row holding the pick (points or bones): open while it lasts, unless folded since. */
  bool holds_pick = false;
  /* Shaded teal (the selected stretch, first and last frame) on this row: the most specific row shown of a channel
   * moving its dots. (0, 0) when not. */
  std::pair<int, int> teal{0, 0};
  /* Every picked stretch shaded on it: first and last frame, and whether it is the active one (lighter). */
  std::vector<std::tuple<int, int, bool>> teal_spans;
  /* The frames it shows keys on, and those whose keys are all fillers (drawn grey and hollow). */
  std::vector<int> frames;
  std::vector<int> filler_frames;
  /* Keyed as one, a chain where the arrow would be: "TOGETHER" (Key Together), "DRAWING" (Key Whole Drawing), "". */
  std::string chain;
  /* The frames drawn hollow: where something inside has keys but nothing picked (bones, points) has its own. */
  std::vector<int> hollow_frames;
  /* Whether an Alt click picks a stretch on it (a chained row or a single channel's). */
  bool stretch_pickable = false;
};
/* A press on the key at `frame` of row `row` (as timeline_rows_list(as_shown=true) lists them) with the timeline's
 * click and drag (`ctrl`, `shift`: held as it is pressed): dragged to `to_frame` (or by the frames `typed`) when it
 * moves the keys, Ctrl held while dragging (`ripple`) or Alt (`alt`). For tests. */
/* The timeline header's key group, in order, whether it edits the selected keys (red) or sets what
 * new keys get (grey), and its colour either way. */
std::vector<std::string> timeline_key_header_parts();
/* 0: new keys' (grey), 1: the selected keys' (red), 2: the selected stretch (teal: the one the Motion Path tool's picks
 * are in, else the path's at the playhead), 3: picks in different stretches (grey, editing them all). */
uint32_t key_header_color(int mode, bool hovered);
/* What the header's key group edits now: mode as key_header_color's; in the teal mode the stretch (its target's label,
 * first and last frame). */
/* A picked stretch shaded teal: its first and last frame, and whether it is the active one (shown lighter). */
struct KeyFocusSpan {
  int start = 0, end = 0;
  bool active = false;
};
struct KeyHeaderFocus {
  int mode = 0;
  std::string label;
  int start = 0, end = 0;
  /* Teal from picks (not the playhead), and whose stretch it is. */
  bool picked = false;
  std::vector<MotionPathTarget> targets;
};
KeyHeaderFocus timeline_key_header_focus(Context &C);
/* Test hook: runs an operator as the header's buttons do (on what it edits now). */
bool timeline_key_header_call(Context &C, const std::string &idname, const std::map<std::string, std::string> &args);
/* The Motion Path tool's proportional editing (the timeline's Motion Paths popover). */
void motion_path_proportional_settings(Context &C);
/* The right-click key menu's top level for timeline row `row` on `frame`: each item's label and whether it opens. */
std::vector<std::pair<std::string, bool>> timeline_key_menu_top(Context &C, int row, int frame);
bool timeline_key_press_simulate(Context &C, int row, int frame, int to_frame, bool ctrl, bool shift,
                                 bool double_click, bool ripple, bool alt, const std::string &typed);
/* The timeline's scroll bar dragged by `frames`: part 0 the bar (pans the view), 1 its left end, 2 its right end
 * (zooming that side, never closer than 10 frames). Returns the new view. */
std::pair<float, float> timeline_scrollbar_drag(float start, float end, int part, float frames);
/* How many channels' rows the timeline's filters take away (its red "N hidden"). */
int timeline_hidden_count(Context &C);
/* Folds or opens a timeline row (`key`, its fold) as its arrow does: a row holding the pick is folded only
 * while the pick lasts, the project's fold left as it is; any other row's fold is the project's. */
void timeline_row_fold(const std::string &key, bool fold_default, bool holds_pick, bool open);
/* The tool for the active layer's kind, as the viewport's tool bar picks it each frame (viewport.cc). */
void tool_follow_active_layer(Context &C);
/* The same for row `row` as timeline_rows_list(as_shown=true) lists them; false when it doesn't fold. */
bool timeline_row_fold_at(Context &C, int row, bool open);
/* Clicking row `row`'s name for its path (a bone's or point's row shows its path, one shown at a time). */
bool timeline_row_path_show_at(Context &C, int row);
/* Clicks row `row`'s chain (as timeline_rows_list(as_shown=true) lists them): its Key Together or Key Whole Drawing
 * turned off, an undo step. False when it has none. */
bool timeline_row_chain_at(Context &C, int row);
/* Clear Timeline's question before it deletes: "Delete all N keys on <Mainline or the action>?". */
std::string timeline_clear_question(Document &doc);
/* Paste Timeline's question when the timeline has keys: "Replace all N keys on <it> with the M keys copied from <the
 * copied timeline>?". */
std::string timeline_paste_question(Document &doc);

/* A row of the timeline's action menu, top to bottom (oanim.wm.action_menu_rows). */
struct ActionMenuRow {
  /* -1 Mainline, above the tabs; 0 the Actions tab; 1 the Bone actions tab (action bone actions and fixes). */
  int tab = 0;
  /* The bone layer it belongs to, and its name when it isn't the first one listed (a heading over its rows). */
  uint64_t rig = 0;
  std::string rig_heading;
  /* Its group in the Bone actions tab: the bone's name ("" for none) and what it is: 1 a bone, 2 a 2 Axis Controller,
   * 3 the fixes ("Fixes"). */
  std::string group;
  int group_kind = 0;
  /* The action; "" for a New row (`add`). */
  std::string name;
  bool add = false;
  /* Its arrow, by ControllerSide: a controller's side, or the way a bone's turn goes (Left counterclockwise, Right
   * clockwise); -1 for none. */
  int arrow = -1;
  bool full_turn = false;
  /* A fix's strength now; -1 for anything else. */
  float strength = -1.0f;
};
/* The rows, those whose name (or bone's name) has `filter` in it, any case. */
std::vector<ActionMenuRow> action_menu_rows(Document &doc, const std::string &filter);
/* The tab the menu opens on: the timeline being edited's, on the mainline the one used last. */
int action_menu_tab_opening(Document &doc);
/* An Alt click on `frame` of row `row` (as timeline_rows_list(as_shown=true) lists them), Shift held or not:
 * anim.timeline_stretch_pick on its channels. False when it did nothing. */
bool timeline_row_alt_click(Context &C, int row, int frame, bool shift);
/* Whether a press in a row (between keys) keys its channels there: a double-click, not with Alt held. */
bool timeline_double_click_keys(bool double_click, bool alt);
/* `as_shown`: folded rows as the project keeps them (else every row open). */
std::vector<TimelineRowInfo> timeline_rows_list(Context &C, bool as_shown = false);
/* Text editor, in text_editor.cc. */
void text_editor_draw(Area &area, Context &C);
/* Python console, in console.cc. */
void console_draw(Area &area, Context &C);

/* A header button that opens a popup menu of the same name, styled like Blender's
 * flat header menus. Returns true while the menu is open; then call ImGui::EndPopup(). */
bool header_menu(const char *label);

}  // namespace oanim
