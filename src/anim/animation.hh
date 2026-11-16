#pragma once

/* How animation reaches the document's plain values, Moho style.
 *
 * Every animatable value (a layer's position, rotation, scale and opacity; a point's position
 * and radius; a curve point's curvature and stored handles) has a Channel beside it. The plain
 * value is the one at the evaluated frame, so tools and the renderer just read and write it.
 *
 * - Recording: a plain value that differs from what the channel last gave is an edit. At
 *   frame 0 (the setup frame) the edit sets the frame-0 key, so it changes every frame without
 *   its own key. At other frames, with auto-keying on, it keys that frame; the first key on a
 *   channel also keys frame 0 with the value from before the edit. With auto-keying off an
 *   unanimated value just changes, and an animated one snaps back at the next evaluation.
 * - Evaluating: each animated channel writes its value at the frame into the plain value.
 *
 * Recording runs before every undo step, before the frame changes, and before saving, so
 * edits always land on the frame they were made at. */

#include <functional>
#include <optional>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>

#include <array>

#include "anim/channel.hh"

namespace oanim {

struct Bone;
struct ActionPlay;
struct BoneFix;

struct Document;
struct Layer;

/* Turns edits since the last evaluation into keys at the evaluated frame. */
void animation_record(Document &doc);
/* Writes every animated channel's value at `frame` into its plain value. */
void animation_evaluate(Document &doc, int frame);
/* While one is open, animation_evaluate on this thread works out values only: channels, action bone actions and
 * drivers, leaving out what poses bones after them (dynamics, Follow Point, Limit to Shape, Look At, outer parents)
 * and the rounds of action bone actions read from those. For a caller reading only bones' own values, whose actions
 * are played from bones' values alone (a path put On Path). */
struct AnimationValuesOnly {
  bool was;
  AnimationValuesOnly();
  ~AnimationValuesOnly();
};
/* After the current frame changed: records edits at the old frame, then evaluates the new one.
 * Does nothing when the frame is already evaluated. */
void animation_sync(Document &doc);
/* How many times the current frame has changed this session (counted by animation_sync; not part of
 * the document, so undo leaves it alone): what lasts "until the frame changes" checks it. */
uint64_t animation_frame_changes();

/* Playing while something is dragged, as Blender records with auto-key: animation_sync has keyed the
 * frame just left with what the drag gave it. A drag puts back how things were when it began on every
 * update, so `start` (that state) takes the keys, and whatever the drag isn't holding takes the new
 * frame's value: the rest plays on while the dragged parts stay where the mouse has them. `dragged` is
 * the state as the drag left it on the frame just left, `now` as the new frame has it. `held` is kept
 * by the caller for the whole drag: what the drag has held once stays held (on a frame the drag didn't
 * update, the mouse outside the window, say, it would look unheld and the move be added again). Returns
 * false (changing nothing) when they don't hold the same channels. */
bool animation_follow_playback(Document &start, Document &dragged, Document &now, std::vector<char> &held);
/* The same for a bone layer's bones (a drag that keeps only those). */
bool animation_follow_playback(std::vector<Bone> &start, std::vector<Bone> &dragged, std::vector<Bone> &now,
                               std::vector<char> &held);

/* --- Actions (Moho's): named alternative timelines of a bone layer and everything inside it.
 * Editing one swaps its keys into the channels, so keying, the timeline and evaluation all work
 * on it unchanged; layers outside keep playing the mainline. Frame 0 stays the shared setup pose:
 * editing it in an action changes the setup. ------------------------------------------------- */

/* The bone layer whose actions a layer can use: itself, or the one it sits in; null if neither. */
Layer *action_owner(Document &doc, uint64_t layer_id);
/* Every bone layer whose actions reach a layer, nearest first: action_owner, then those around it, since an action
 * animates everything inside its bone layer. */
std::vector<Layer *> action_owners(Document &doc, uint64_t layer_id);
struct VectorDrawing;
/* Puts `drawing`'s keys being edited away under timeline `from` and brings out `to` ("": the mainline), for a drawing
 * not in the document, as document_set_action does for those that are. */
void drawing_timeline_swap(VectorDrawing &drawing, const std::string &from, const std::string &to);
/* Edits action `name` of bone layer `owner` ("" for the mainline). Returns false when there is
 * no such action. */
bool document_set_action(Document &doc, uint64_t owner, const std::string &name);
/* By name alone: the bone layer is found from the active layer (the nearest around it that has it), else any bone layer
 * that has it. */
bool document_set_action_by_name(Document &doc, const std::string &name);
/* The action being edited (its bone layer and name) and its frame 0 keys, for work that looks through other actions
 * and comes back (Keep Animation): leaving an action takes its frame 0 keys back into the setup, and coming back makes
 * them again only where the channel is keyed after frame 0 (or on the mainline), so a key made on frame 0 alone would be
 * lost on the way. */
struct EditedAction {
  uint64_t owner = 0;
  std::string name;
  /* Per channel of the owner and the layers inside it, in order: its frame 0 key, if it had one. */
  std::vector<std::shared_ptr<void>> setup_keys;
};
EditedAction edited_action_save(Document &doc);
/* Back into it (by its bone layer, not just its name), its frame 0 keys as they were. */
void edited_action_restore(Document &doc, const EditedAction &saved);
/* Adds an action to `owner` (named uniquely from `name`) and starts editing it. Returns its name. */
std::string document_action_new(Document &doc, uint64_t owner, const std::string &name);
/* Deletes action `name` of `owner` and its keys (editing it: back to the mainline first). Returns
 * false when there is no such action. */
bool document_action_delete(Document &doc, uint64_t owner, const std::string &name);

/* Action bone actions (Moho's smart bones): an action named after a bone of its bone layer (or the
 * name plus " 2", for turning the other way). In it the bone's angle is keyed from its setup
 * angle onwards; elsewhere the bone's angle picks the matching frame of the action, and every
 * other channel the action keys gets that frame's change from frame 0 added on top. Several action bone
 * actions add together. Returns the driving bone, or null for an ordinary action. A 2 Axis Controller's
 * ordinary actions are played the same way, by its knob (anim/controller.hh), and it is what this returns. */
const Bone *action_bone_of(const Layer &owner, const std::string &action);

/* --- 2 Axis Controllers (anim/controller.hh) ------------------------------------------------------- */

/* Where a controller's knob shows, in frames: where it is, or inside one of its own actions the frame shown on that
 * side. */
float2 controller_knob_shown(const Document &doc, const Layer &owner, const Bone &knob);
/* Ctrl on a knob: onto its nearest spot (controller_knob_snap). */
void armature_knob_snap(const Layer &armature, Bone &knob);
/* What the sides' actions key, found again after keys change (Bone::controller_keys). */
void controllers_update(Document &doc);
/* Makes the bone a controller, or regular again, on the mainline. To a controller: its own action bone actions go into
 * Right and Left, its angle keys becoming knob keys; any other position keys are read as frames. Back: they come out
 * the same way. Returns anything the user should hear of. */
std::string bone_convert_to_controller(Document &doc, uint64_t owner, uint64_t bone);
std::string bone_convert_to_regular(Document &doc, uint64_t owner, uint64_t bone);
/* Makes the bone a Pin (BoneType::Pin; a controller becomes Regular first). Its children connected to its tip are
 * let go, keeping where they are: nothing connects to a pin. */
std::string bone_convert_to_pin(Document &doc, uint64_t owner, uint64_t bone);
/* Puts an ordinary `action` in a side ("" empties it), from the mainline: never a bone's own action (an action bone
 * action), a fix or another side's. False with why, nothing changed. */
bool controller_side_set(Document &doc, uint64_t owner, uint64_t knob, int side, const std::string &action,
                         std::string *r_why);
/* Older files linked a side to a bone's own action (one set of keys, the knob's): each such side gets an ordinary
 * action of its own instead, keying that bone's turn as its action did, so the knob still drives it. Returns how
 * many. */
int controller_links_undo(Document &doc);
/* Each fix named by itself (BoneFix::auto_name) named again after the actions playing where it ends, as leaving it
 * names it: once a side's action changes, or on opening a file saved with one out of date; of `owner_id`'s fixes, 0
 * every bone layer's. The fix being edited waits until it is left. Returns how many were renamed. */
int bone_fix_names_follow(Document &doc, uint64_t owner_id = 0);
/* What the action bone actions of bone layer `owner` add to its bones on `frame`, as apply_action_bone_actions plays
 * them on the frame shown: `bones` (owner's, in its order) hold the keyed values there, without action bone
 * actions, and get the action bone actions' amounts added. For working out other frames than the one shown
 * (dynamics simulate every frame up to it). */
void action_bone_actions_add_at(const Layer &owner, int frame, std::vector<Bone> &bones);
/* --- Fix actions that follow bones (BoneFix, data/layer.hh: the Bone tab's Fix Actions). One is an ordinary action
 * while edited (its bones keyed and moved in it, the action bone actions playing under it from where they are); on the
 * mainline it plays after the action bone actions, never moving the bones it follows or an action
 * bone, at the frame the bones' pose picks. ----------------------------------------------------------------------- */

const BoneFix *bone_fix_find(const Layer &owner, const std::string &name);
/* Whether action `name` is a fix following `bone` whose keys on `ch` (one of the bone's channels) are its line, which
 * it never plays onto the bone. */
bool bone_fix_line_of(const Layer &owner, const std::string &name, const Bone &bone, const void *ch);
/* How far a bone counts toward a fix: a 2 Axis Controller 2 (its knob goes two ways), any other 1. */
int bone_fix_ways(const Bone &bone);
/* Where a fix plays as the bones are now: its line from `start` (1) to `end` (the last frame its bones are keyed on;
 * nothing plays with none past 1), `frame` the frame of it whose pose is nearest along what changes on the line, and
 * `strength` how much plays (0 to 1: each bone or knob axis staying put on the line, away from rest, as a share of
 * where it stays). */
struct BoneFixPlay {
  float start = 1.0f, end = 1.0f, frame = 1.0f, strength = 0.0f;
};
BoneFixPlay bone_fix_play(const Layer &owner, const BoneFix &fix, bool edited = false);
/* "Bone Up and Right": the actions its bones play where it ends (on `frame`, or its last), as named by the side or turn
 * they are on, else its bones' names with "Fix". `edited`: its keys are in the channels, the timeline edited. */
std::string bone_fix_name(const Layer &owner, const BoneFix &fix, bool edited = false, int frame = -1);
/* "Up 24 · Right 0": where `fix`'s bones are on `frame` of it (a knob in frames each way, a bone's turn in degrees),
 * each named when it follows more than one. */
std::string bone_fix_pose_label(const Layer &owner, const BoneFix &fix, bool edited, float frame);
/* A fix's line in a knob's box: where the knob is along it (frames each way, from frame 1 to its end), where it plays
 * now (`now`) and how much (`strength`, 0 muted). `edited`: the fix is the action edited. */
struct BoneFixKnobLine {
  std::string name;
  std::vector<float2> points;
  float2 now;
  float strength = 0.0f;
  bool edited = false;
};
/* The lines of the fixes that follow knob `knob` of `owner`. */
std::vector<BoneFixKnobLine> bone_fix_knob_lines(const Document &doc, const Layer &owner, const Bone &knob);
/* "Up · Right": the ways bone `bone` has gone where `fix` ends (a knob's sides, a bone's turn), "" for none. */
std::string bone_fix_bone_ways(const Layer &owner, const BoneFix &fix, uint64_t bone, bool edited);
/* A new fix following `follows` (bone ids), keyed on frame 1 where they are now, named for that, and opened on
 * frame 1. Returns its name, or "" (none of them in `owner`). */
std::string document_bone_fix_new(Document &doc, uint64_t owner, const std::vector<uint64_t> &follows);
/* Fix `name`'s mirror image (bone Symmetrize's Mirror Action Bone Actions): a fix following the other side's bones, its
 * keys mirrored as an action's are (a knob's line Left and Right swapped, as its spots are), its fade the same. One
 * there already following those bones is replaced (`r_replaced`). Named for where it ends if `name` is, else as the
 * other side's action. Returns its name, or "" (none of its bones has another side). */
std::string document_bone_fix_mirror(Document &doc, uint64_t owner, const std::string &name, bool *r_replaced = nullptr);
/* Bone `bone` added to or taken from what fix `name` follows. Taken, its keys in the fix go with it (they would play as
 * the fix). */
bool document_bone_fix_follow(Document &doc, uint64_t owner, const std::string &name, uint64_t bone, bool follow);
/* The actions playing under fix `name` that Take Out offers: those of the bones it follows, and the fixes those bones
 * alone play. */
std::vector<std::string> bone_fix_take_out_choices(const Layer &owner, const std::string &name);
/* Take Out: keys fix `name` with the opposite of what `action` adds under it (times `factor`) on each of its poses (the
 * frames its line has keys on), on every channel the action keys (`selected_only`: the selected bones' and points').
 * Opens the fix for it and goes back. Returns how many keys it set. */
int document_bone_fix_take_out(Document &doc, uint64_t owner, const std::string &name, const std::string &action,
                               float factor = 1.0f, bool selected_only = false);
/* The action bone actions of `owner` playing now, its bones as they are: each with the frame its bone's turn
 * picks (more than 0). */
std::vector<std::pair<std::string, float>> action_bone_actions_playing(const Layer &owner);
/* An action bone action's length: its driving bone's last key there (0 with none). */
float action_bone_action_length(const Layer &owner, const std::string &name);
/* A 360 action bone action (Moho's 360 action bone): its bone's last key is exactly one whole turn from the setup,
 * so the bone's turn counts round and round (modulo a turn). */
bool action_bone_action_full_turn(const Layer &owner, const std::string &name);
/* A regular or pin bone's own action bone actions (named after it, and its name with " 2"), each in the slot of the way
 * its last key turns the bone: [0] counterclockwise (a positive turn), [1] clockwise; one not keyed yet goes where its
 * name puts it ([0] the plain name), the other slot when that is taken. `full_turn`: its Turns is Full Turn (set, or
 * an action of its turning a whole turn): the one action in [0]. The Bone tab's Actions. */
struct BoneTurnSlots {
  std::array<std::string, 2> action;
  bool full_turn = false;
};
BoneTurnSlots bone_turn_slots(const Document &doc, const Layer &owner, const Bone &bone);
/* The bone's turn keys in action `name`: the timeline's while it is open, else those put away; null with none. */
const std::vector<Key<float>> *bone_turn_keys(const Document &doc, const Layer &owner, const Bone &bone,
                                              const std::string &name);

/* --- The Actions panel (ActionPlay, data/layer.hh): every action's Frame, Mute and Loop. ---------------------- */

/* "actions[\"wave\"].frame": the channel of an action's own Frame. */
std::string action_frame_path(const std::string &name);
const ActionPlay *action_play_find(const Layer &owner, const std::string &name);
ActionPlay *action_play_find(Layer &owner, const std::string &name);
/* Made the first time any of it is set. */
ActionPlay &action_play_ensure(Layer &owner, const std::string &name);
/* What says an action's frame: its own Frame, a bone's turn (an action bone action), a knob (a controller's side,
 * linked dials too: the knob holds the keys) or, for a fix, the bones it follows. `r_holder`: the bone or knob. */
enum class ActionFrameBy { Own, Bone, Knob, Fix };
ActionFrameBy action_frame_by(const Layer &owner, const std::string &name, const Bone **r_holder = nullptr);
bool action_muted(const Layer &owner, const std::string &name);
/* Whether it starts over past its last frame (ActionPlay::loop, Auto worked out). */
bool action_loops(const Layer &owner, const std::string &name);
/* Its last frame: its bone's or knob's for those, else the last key in it anywhere in the bone layer. `edited`: its
 * keys are out in the channels. */
float action_length(const Layer &owner, const std::string &name, bool edited = false);
/* The frame it is at, as the panel shows it: its own Frame, or where its bone or knob has it (0: not playing). A fix
 * shows how much of it plays (0 to 1). */
float action_frame_shown(const Layer &owner, const std::string &name);
/* Puts it at `frame` (0: not playing): its own Frame, or its bone turned or knob moved to there (keyed as edits are).
 * False for a fix, or a bone with no keys yet to say how far. */
bool action_frame_set(Layer &owner, const std::string &name, float frame);
/* "12" or "12.5": an action frame as labels show it. */
std::string action_frame_text(float frame);
/* Whether action `name` adds onto the pose rather than being a timeline of its own (an action bone action):
 * its keys are offsets that pose changes elsewhere leave as they are. */
bool action_adds(const Layer &owner, const std::string &name);
/* After every change (each undo step): a fix that follows a bone deleted follows the rest, and fixes named after
 * their bones' actions take their names as they are now (bone_fix_names_follow). */
void bone_fixes_tidy(Document &doc);
/* Renames action `from` of `owner`: its keys, its fix or controller side and, edited, the timeline's name. */
bool document_action_rename(Document &doc, uint64_t owner, const std::string &from, const std::string &to);
/* Bone `from` of `owner` renamed `to`: its action bone actions take the new name. */
void armature_bone_renamed(Document &doc, uint64_t owner, const std::string &from, const std::string &to);

/* Takes what action bone actions add off every plain value, leaving the data (for saving). */
void animation_strip_action_bones(Document &doc);

/* A layer and everything inside it without timeline keys (Duplicate in a switch): each channel keeps
 * its setup value (frame 0), or with `from_now` the value it has now, its drawings then taking that as
 * their setup pose. With `keep_actions` its actions' keys (action bone actions) stay. */
void layer_strip_keys(Layer &layer, bool from_now, bool keep_actions);
/* Every channel of `layer` (not its children): the keys of each action it isn't editing (and frame 0's path handles)
 * under the name `rename` gives theirs, left out where it gives none. Every name is renamed at once, so two swap. */
void layer_actions_rename(Layer &layer, const std::function<std::optional<std::string>(const std::string &)> &rename);
/* `doc` as only what evaluating a frame works from: its keys, its plain values, its settings, no values a frame worked
 * out (a keyed channel's value, what action bone actions added, a bone's or a point's place, constraints' shapes).
 * Two documents alike this way show every frame alike. False where an edit isn't taken into its changes from the setup
 * pose yet (a bone or a point moved and not recorded): nothing to compare by. */
bool animation_inputs_only(Document &doc);
/* Works action bone actions out again for the bones as they are now (a bone turned without changing
 * frame). animation_sync does this when the frame hasn't moved. */
/* As animation_sync, for the main loop's own frame changes (playing): `edits` stamps every edit the app can see
 * coming (Python runs, undo steps, operators run, edits in the UI). While it and the keys stay as they were, a
 * drawing a switch hides that comes out the same on every frame (no keys, no action data, nothing action bone actions
 * added) is neither recorded nor evaluated again: on a rig with many views, most of the document. */
void animation_sync_playing(Document &doc, uint64_t edits);
void animation_refresh_action_bones(Document &doc);
/* A bone drag's update, once the bones are where it has them: action bone actions played again from them, then what
 * is worked out from the pose (outer parents' frames, Follow Point's, Limit to Shape's and a Look At's eye shape), so
 * what the update draws holds to the picture as it is now, not as it was an update before. */
void animation_drag_refresh(Document &doc);
/* A bone drag on `doc` begins: until it ends, the layers action bone actions play into are the ones found now (it
 * changes no layers, only bones), and the drag works action bone actions out again itself every update, so
 * animation_sync leaves them. End it before the document is put back or replaced. */
void animation_action_bone_drag_begin(Document &doc);
void animation_action_bone_drag_end();
/* The layers action bone actions play into during the bone drag going on (their ids). */
std::unordered_set<uint64_t> animation_action_bone_drag_layers();

/* The document's Simulation settings (gravity, wind, wind_direction, wind_gusts, wind_gust_speed,
 * wind_turbulence) as channels of Document::simulation, made ready. */
Layer &document_simulation(Document &doc);
/* Whether a path names one of them. */
bool simulation_path(const std::string &path);
/* Writes the Simulation channels' values into the document's settings (after drivers set them). */
void simulation_values_out(Document &doc);
/* One of them on `frame`: its keys there when animated, else `plain` (the setting now). */
float simulation_value_at(const Document &doc, const char *path, float plain, int frame);

/* One named channel of a layer and the plain value it drives: "position", "rotation", "scale",
 * "opacity", "points[3].pos", "points[3].radius", "curves[0].points[2].curvature",
 * "curves[0].points[2].handle_in", "curves[0].points[2].handle_out". */
struct ChannelRef {
  std::string path;
  Channel<float> *scalar = nullptr;
  float *scalar_value = nullptr;
  Channel<float2> *vector = nullptr;
  float2 *vector_value = nullptr;
};
/* The layer's channels: its own, then (with `drawing`) those of its points and curves. */
std::vector<ChannelRef> layer_channels(Layer &layer, bool drawing = true);
bool layer_channel(Layer &layer, const std::string &path, ChannelRef *r_ref);

/* Keys every channel of the layer at `frame` with its current value (Blender's I). Returns
 * how many keys were set. */
int layer_insert_keys(Layer &layer, int frame);
/* Removes the layer's keys at `frame` (Alt I). Returns how many were removed. */
int layer_delete_keys(Layer &layer, int frame);
/* Deletes the channel's key on `frame`. Frame 0's key is the setup (the rest pose, in the mainline and
 * every action): it goes only with the last of the keys, since without it frame 0 would show the
 * nearest key's pose, and recording there would take that pose as the rest. A setup key left alone
 * goes too, the channel keeping its value. Returns whether a key went. */
bool channel_delete_key(Channel<float> &ch, float &value, int frame);
bool channel_delete_key(Channel<float2> &ch, float2 &value, int frame);
/* Blender's keyframe button for some channels of a layer (by path): keys them at `frame`, or, when
 * any is keyed there, takes those keys away (frame 0's only with the last key). `mode` 1 only keys
 * and -1 only takes away, whatever is keyed (a group's button for the layers inside it). Returns how
 * many were added or went. */
int layer_toggle_keys(Layer &layer, const std::vector<std::string> &paths, int frame, int mode = 0);
/* 0: none of them animated; 1: animated; 2: keyed at `frame`. */
int layer_key_state(Layer &layer, const std::vector<std::string> &paths, int frame);
/* An action bone action, a knob or a fix moves one of them now (their fields say so in Affected By, not in colour:
 * green and yellow are the timeline's own keys only). */
inline constexpr int KEY_STATE_ACTION_BONE = 4;
/* KEY_STATE_ACTION_BONE when an action bone action is playing into any of them now, else 0. */
int layer_action_bone_state(Layer &layer, const std::vector<std::string> &paths);
/* What moves a channel now besides its own keys and value (a field's Affected By): each action playing into it,
 * by what plays it, with how far (0..1: its frame of the action's length, a fix's strength). Not the action
 * edited (its keys are the timeline's). */
enum class ChannelSourceKind : uint8_t { ActionBone, Knob, Fix, Action };
struct ChannelSource {
  ChannelSourceKind kind = ChannelSourceKind::Action;
  /* The bone layer whose action it is. */
  uint64_t owner = 0;
  std::string action;
  /* The action bone or knob; a fix's first bone. */
  std::string bone;
  float amount = 0.0f;
};
std::vector<ChannelSource> layer_channel_sources(Document &doc, Layer &layer, const std::string &path);
/* A channel's own value (without what actions add) and what it shows. False when `path` isn't a channel. */
bool layer_channel_own_value(Layer &layer, const std::string &path, float2 *r_own, float2 *r_shown, bool *r_vector);
/* Key Whole Drawing: every channel of the drawing's shape (each point's position and width, each curve point's
 * curvature and handles) keyed on every frame any of them is, each new key holding what the channel has there and
 * taking the timing (interpolation, hold, speeds...) most keys on that frame have. A frame that lost a key since the
 * last call (in the same `action`) more than the others did is deleted from them all. With `settle`, keys already there
 * take that timing too (once, as it is turned on). Returns how many keys already there had their timing changed. */
int drawing_key_whole(Layer &layer, bool settle, const std::string &action, bool *r_keys_went = nullptr);

/* Key Together (Layer::key_together) is for groups, bone layers and vector layers (a vector layer alone: its own
 * channels and drawing). In the timeline it is the layer's row folded. */
bool key_together_allowed(const Layer &layer);
/* The outermost group keying the layer (or itself) together, or null. */
Layer *key_together_group(Document &doc, uint64_t layer_id);
/* The channels a Key Together group keys as one: its layers' turn, move, size and opacity, their bones', and their
 * drawings' shapes. */
std::vector<ChannelRef> key_together_channels(Document &doc, Layer &group);
/* The group and every layer inside it, flat. */
std::vector<Layer *> key_together_layers(Document &doc, Layer &group);
/* Keys the group's channels as one (drawing_key_whole's way, the keys added fillers). Returns how many keys had their
 * timing changed (with `settle`). `r_keys_went`, when given, is set if a frame deleted from one was taken from all. */
int key_together_sync(Document &doc, Layer &group, bool settle, bool *r_keys_went = nullptr);
/* Turned off: the filler keys never edited go. Returns how many went and how many fillers stayed. */
std::pair<int, int> key_together_release(Document &doc, Layer &group);
/* Auto-Freeze Keys for a channel keyed outside animation_record (a switch pick): before its key on `frame` goes in,
 * a key at `layer`'s poses either side holding what it shows there. Nothing when Auto-Freeze doesn't apply or it has a
 * key on the frame already. */
void auto_freeze_hold(Document &doc, Layer &layer, Channel<float> &ch, int frame);

/* Frames where the layer (or its drawing) has keys, sorted, each once. */
std::vector<int> layer_key_frames(const Layer &layer);
/* Whether any of the layer's channels has a key (cheaper than layer_key_frames). */
bool layer_has_keys(const Layer &layer);

/* --- Editing keys in the timeline: the keys of several layers, by frame. ---------------- */

/* How a key looks in the timeline, by the family of its mode. */
enum KeyShape : int8_t {
  KEY_SHAPE_SMOOTH,  /* diamond */
  KEY_SHAPE_LINEAR,  /* thin diamond */
  KEY_SHAPE_STEP,    /* square */
  KEY_SHAPE_EASE,    /* circle */
  KEY_SHAPE_BOUNCY,  /* star: Back, Bounce, Elastic */
  KEY_SHAPE_SPECIAL, /* hexagon: Noisy, Cycle, Bezier, Pose */
  KEY_SHAPE_MIXED,   /* keys of different families on one frame: diamond */
};
KeyShape interp_key_shape(Interp interp);

struct KeyFrameSummary {
  int keys = 0;
  int selected = 0;
  /* How many of the keys are breakdowns (drawn as a small circle when all are). */
  int breakdowns = 0;
  /* How many are Key Together's or Key Whole Drawing's fillers (drawn grey and hollow when all are). */
  int fillers = 0;
  /* The family of the keys' modes (yes/no channels, always Step, only count when there is
   * nothing else). */
  KeyShape shape = KEY_SHAPE_STEP;
  bool shape_set = false;
};
/* Which channels a timeline row covers: kinds of channel, and whether only those of selected
 * things (selected points, and bones picked by body or ball). */
enum KeyKind : uint32_t {
  KEY_LAYER_ANGLE = 1 << 0,     /* "rotation" */
  KEY_LAYER_TRANSFORM = 1 << 1, /* "position", "scale" */
  KEY_OPACITY = 1 << 2,
  KEY_VISIBILITY = 1 << 3,
  KEY_BONE_ANGLE = 1 << 4,
  KEY_BONE_TRANSFORM = 1 << 5, /* a bone's position and scale */
  KEY_POINTS = 1 << 6,         /* points' position and width, curves' shape and handles */
  KEY_SIMULATION = 1 << 7,     /* the document's gravity and wind (Document::simulation) */
  KEY_CONSTRAINTS = 1 << 8,    /* a bone's constraints' settings (influence, dynamics) */
  KEY_DRAW_ORDER = 1 << 9,     /* "draw_order" */
  KEY_SWITCH = 1 << 10,        /* "switch": the child a switch shows (on its own row, not with the layer's properties) */
  KEY_LAYER = KEY_LAYER_ANGLE | KEY_LAYER_TRANSFORM | KEY_OPACITY | KEY_VISIBILITY | KEY_DRAW_ORDER,
  KEY_BONES = KEY_BONE_ANGLE | KEY_BONE_TRANSFORM | KEY_CONSTRAINTS,
  KEY_ALL = KEY_LAYER | KEY_BONES | KEY_POINTS | KEY_SIMULATION | KEY_SWITCH,
};
struct KeyFilter {
  uint32_t kinds = KEY_ALL;
  bool selected_only = false;
  /* Only this channel (a timeline row of one property), or, ending in '.', the channels under it
   * ('bones["arm"].': one bone's). */
  std::string path;
  /* Only pinned channels. */
  bool pinned_only = false;
  /* With selected_only: the layers whose selected points count, those being edited (a selection
   * left in a layer no longer edited stays stored, but isn't the selection now); null: every layer's. */
  std::shared_ptr<const std::set<uint64_t>> point_layers;
  /* Bones' channels only for the picked bones (other channels all pass): a picked bone layer's timeline row
   * with Only Selected, its own keys and its picked bones'. */
  bool picked_bones_only = false;
  /* Only these channels (a folded Key Together group's path: what the group keys as one, on the layers inside it). */
  std::shared_ptr<const std::set<const void *>> channels;
  bool everything() const
  {
    return kinds == KEY_ALL && !selected_only && path.empty() && !pinned_only && !picked_bones_only && !channels;
  }
};
/* The kind of channel a path names (see ChannelRef). */
KeyKind channel_kind(const std::string &path);
/* A layer's channels that pass the filter. */
std::vector<ChannelRef> layer_filtered_channels(Layer &layer, const KeyFilter &filter);
/* Keys the layer's channels that pass `filter` at `frame` with their current values (a timeline row's
 * channels, double-clicked). Returns how many keys were set. */
int layer_insert_filtered_keys(Layer &layer, const KeyFilter &filter, int frame);

/* Whether any channel of `layers` passing `filter` is one of `channels` (a timeline row's, Time Together's marks). */
bool layers_channel_among(const std::vector<Layer *> &layers, const KeyFilter &filter,
                          const std::set<const void *> &channels);

/* Whether a channel passes the filter's path ('bones["arm"].' covers the bone's channels). */
bool key_filter_path_matches(const KeyFilter &filter, const std::string &path);

/* --- Pinning channels to the timeline ------------------------------------------------------ */

/* Whether the layer's channel at `path` is pinned. */
bool layer_channel_pinned(Layer &layer, const std::string &path);
/* Pins (or unpins) the layer's channels at `paths`. Returns how many changed. */
int layer_pin_channels(Layer &layer, const std::vector<std::string> &paths, bool pinned);
/* Unpins every channel of the document (its layers and its Simulation settings). Returns how many. */
int document_clear_pins(Document &doc);
/* What a channel is called in the timeline: "Position", "Angle", "IK: Influence", "Dynamics: Angle
 * Bounce", "Gravity". With `owner`, whose it is first: "Layer 1: Opacity", "arm: Angle",
 * "Simulation: Wind". */
std::string channel_label(Layer &layer, const std::string &path, bool owner);

/* The channels of `layers` that pass `filter` and have a key at `frame` (the timeline's Keyed Here
 * list): each layer with the path of each such channel, in the layer's channel order. */
std::vector<std::pair<Layer *, std::string>> layers_keyed_at(const std::vector<Layer *> &layers,
                                                             const KeyFilter &filter, int frame);

/* For each keyed frame: how many keys there are, and how many of them are selected. */
std::map<int, KeyFrameSummary> layers_key_summary(const std::vector<Layer *> &layers, const KeyFilter &filter = {});
/* Selects (or deselects) every key on frames `first`..`last`. */
/* The selected flags of the keys on `frame` of the channels passing `filter`. */
std::vector<bool *> layers_key_selected_flags(const std::vector<Layer *> &layers, int frame, const KeyFilter &filter);
/* The frames the channels passing `filter` have keys on. */
std::set<int> layers_filtered_key_frames(const std::vector<Layer *> &layers, const KeyFilter &filter);
/* The channels passing `filter` (to ask layers_channel_among about). */
std::set<const void *> layers_filtered_channel_set(const std::vector<Layer *> &layers, const KeyFilter &filter);
void layers_select_keys(const std::vector<Layer *> &layers, int first, int last, bool select,
                        const KeyFilter &filter = {});
void layers_deselect_keys(const std::vector<Layer *> &layers);
/* Whether a key is selected on a channel of `layers` that isn't one of `channels`, or on the setup frame (keys the
 * Motion Path tool's picked stretches don't account for). Visibility's always-Step keys are left out. */
bool layers_key_selected_outside(const std::vector<Layer *> &layers, const std::set<const void *> &channels);
bool layers_any_key_selected(const std::vector<Layer *> &layers);

/* The selected keys' interpolation: how many there are, the first one's settings, and whether
 * their modes (or ease strengths) differ. */
struct SelectedKeys {
  int count = 0;
  KeySettings first;
  bool mixed = false;
  bool mixed_ease = false;
  /* Some keys and some breakdowns. */
  bool mixed_type = false;
  /* Frames the stretch arriving at the first key moves over (0: it is a channel's first key). */
  int first_span = 0;
  /* Up to six other curves among them (differing from the first's and each other's). */
  std::vector<KeySettings> others;
  /* The first one's timing curve, when it is Custom. */
  TimingCurve first_timing;
};
SelectedKeys layers_selected_keys(const std::vector<Layer *> &layers);
/* Changes the selected keys' interpolation settings with `change`; yes/no channels' keys stay
 * Step. A key left Custom takes the curve `custom` when given. Returns how many keys there were. */
int layers_change_selected_keys(const std::vector<Layer *> &layers, const std::function<void(KeySettings &)> &change,
                                const TimingCurve *custom = nullptr);
/* Copy and Paste Interpolation's clipboard, one for the timeline and the Path Timing graph: a key's settings and,
 * when Custom, its timing curve (by share of the stretch's time, so it fits a stretch of any length). */
struct InterpClipboard {
  bool copied = false;
  KeySettings settings;
  TimingCurve timing;
};
InterpClipboard &interp_clipboard();
/* What it holds, for Paste's tooltip ("Ease In/Out (Quad)", "Custom curve, 6 points"); empty while nothing is. */
std::string interp_clipboard_text();
/* Moves the selected keys to `to(frame)` (never below 1; frame-0 keys, the setup, stay put).
 * A moved key landing on an unselected one replaces it, as in Blender. */
/* Ripple: the unselected keys after each channel's last selected key move by as much as it does. */
void layers_move_selected_keys(const std::vector<Layer *> &layers, const std::function<int(int)> &to,
                               bool ripple = false);

/* Time Together (Document::time_together). The channels it can link: of the selected layers, each one's move, turn,
 * size, shear and opacity and its drawing's shape, and the selected bones' position, angle, scale and depth. */
std::vector<const void *> time_together_candidates(Document &doc);
/* The candidates the selected keys of `layers` carry along: keyed on both ends of a stretch they edit (from the
 * unmoved key before to the unmoved key after), with none of their own selected. Empty while it is off. */
std::set<const void *> time_together_linked(Document &doc, const std::vector<Layer *> &layers);
/* layers_move_selected_keys, and with `together` (and Time Together on) the linked channels' keys inside each edited
 * stretch go through the same stretch, so a key halfway along stays halfway, rounded to whole frames and kept a
 * frame apart. Returns how many linked channels moved. */
int keys_move_selected(Document &doc, const std::vector<Layer *> &layers, const std::function<int(int)> &to,
                       bool ripple, bool together);
/* Cascadeur's + and -: `amount` frames more (or fewer) in the stretch of each of the layer's channels that the frame is
 * in (from a key on or before it to the next), the keys after going along; never below one frame. With `together`
 * and Time Together on, the linked channels keyed on the same two frames take it too, their keys inside through the
 * same stretch. Returns how many of the layer's channels changed and how many linked ones went along. */
std::pair<int, int> keys_span_frames_add(Document &doc, Layer &layer, int frame, int amount, bool together);
/* Match Timing (animBot's key-time copy): the selected layers' and bones' other channels (Time Together's candidates)
 * keyed on the source layer's frames, stretched over each one's own first to last key; with as many keys as frames
 * each key goes to its frame, else to the nearest (the nearest wins a frame two reach) and frames none reached are
 * keyed with what it held there. Returns how many channels changed and how many keys merged. */
std::pair<int, int> keys_match_timing(Document &doc, Layer &source);
/* `offset` held so the selected keys move without reaching the unselected keys either side (a frame short; with
 * Ripple the one after the last goes along), nor frame 0: sliding a stretch keeps its length. */
int keys_offset_clamp(const std::vector<Layer *> &layers, int offset, bool ripple);
/* Every key's timing (as a number), to see after a timing edit which keys it changed. */
struct TimingSnapshot {
  std::map<const void *, std::vector<std::pair<int, uint32_t>>> keys;
};
TimingSnapshot time_together_timing_snapshot(Document &doc);
/* Each key whose timing changed since `before` gives it to the linked channels' key on its frame, where they are keyed
 * on the frames of the keys either side and nowhere between (the same stretches): interpolation, hold, type and
 * Custom speeds alike. Returns how many channels took it. */
int time_together_timing_follow(Document &doc, const TimingSnapshot &before);
/* Time Together around one timing edit (an operator flagged OPTYPE_TIMING, a timing brush's stroke in the viewport):
 * started before it (doing anything only with Time Together on), finished after it, the linked channels taking the
 * new timing (time_together_timing_follow). `finish` returns how many went along. */
struct TimeTogetherEdit {
  bool on = false;
  TimingSnapshot before;
  void start(Document &doc);
  int finish(Document &doc);
};
/* Deletes the selected keys, except frame 0's. Returns how many went. */
int layers_delete_selected_keys(const std::vector<Layer *> &layers);
/* Clear Timeline: every key of the timeline being edited goes but frame 0's, the setup pose, so all of it shows the
 * setup again. On the mainline that is every layer's, the camera's and the Simulation's; in an action, only that
 * action's (its bone layer and what is inside it), the mainline and the other actions left alone. With `count_only`
 * nothing changes. Returns how many keys (or would) go. */
int timeline_clear(Document &doc, bool count_only = false);
/* Copy Timeline: every key of the timeline being edited but frame 0's (the layers Clear Timeline clears), kept apart
 * from Copy Keys' clipboard. Returns how many (none copied, the last copy kept). */
int timeline_copy(Document &doc);
bool timeline_clipboard_empty();
/* The copied timeline's name ("Mainline" or the action's) and how many keys it holds. */
std::string timeline_clipboard_name();
int timeline_clipboard_count();
/* Paste Timeline: the timeline being edited cleared (as Clear Timeline), then the copied timeline's keys put on their
 * own frames, onto the same layers' channels (a layer not there matched by name, a knob's timing only back into its
 * own action). Returns how many keys pasted; with none the timeline is cleared still (the caller puts it back). */
int timeline_paste(Document &doc);
/* What the timeline being edited is called: "Mainline", or the action's name. */
std::string timeline_edited_name(const Document &doc);
/* Copies the selected keys `offset` frames later (never below 1); the copies become the
 * selection and replace keys where they land (Blender's Duplicate, then moving the copies). */
/* The offset copies of the selected keys go by: `offset`, or as far short of it as keeps every copy past the setup
 * frame, their spacing kept. */
/* The last frame a key can go on: the playhead's last. */
constexpr int KEY_FRAME_LAST = 1048574;
int keys_duplicate_offset(const std::vector<Layer *> &layers, int offset);
void layers_duplicate_selected_keys(const std::vector<Layer *> &layers, int offset);
/* Neighbouring keyed frames (a, b) across which nothing changes: every channel keyed at either
 * has a key at both with the same value. Blender draws a hold bar between such keys. */
std::vector<std::pair<int, int>> layers_hold_spans(const std::vector<Layer *> &layers, const KeyFilter &filter = {});

/* Blender's Copy and Paste Keyframes. Copying keeps the selected keys, by layer and channel, in a
 * clipboard that outlives switching actions (and documents). Pasting puts them at `frame` (the
 * first copied key lands there, the rest keep their spacing) onto the same layers' channels; a
 * layer that isn't there is matched by name, and keys copied from one layer go onto the first of
 * `layers` that has the channel. The pasted keys become the selection; one landing on frame 0
 * becomes the setup pose, and any before it are left out. Each returns how many keys it copied or
 * pasted. */
int layers_copy_selected_keys(const Document &doc, const std::vector<Layer *> &layers);
/* With `r_layers` and `r_frames`: each layer pasted onto with the layer its keys were copied from, and
 * each copied key's frame with the frame it was pasted on (for Ignore Bones). */
int layers_paste_keys(const Document &doc, const std::vector<Layer *> &layers, int frame,
                      std::vector<std::pair<uint64_t, uint64_t>> *r_layers = nullptr,
                      std::vector<std::pair<int, int>> *r_frames = nullptr);
bool key_clipboard_empty();
/* The document the copied keys came from, as it was when they were copied (for Ignore Bones), or null. */
void key_clipboard_set_source(const Document &doc);
const Document *key_clipboard_source();

/* Ignore Bones (Duplicate and Paste Keys): the point and handle keys just placed on each `frames`
 * (source frame, new frame) of `layers` (the layer in `doc`, the one in `source` its keys came from) are
 * worked out again so each point shows where it did on the source frame in `source`, whatever the
 * bones do on the new frame. Only selected keys (the new ones) change; detail points follow their
 * parents, and a point a bone flattens to nothing keeps its key. Returns how many keys changed. */
int keys_ignore_bones(Document &doc, const Document &source, const std::vector<std::pair<uint64_t, uint64_t>> &layers,
                      const std::vector<std::pair<int, int>> &frames);
/* Keep Place (Duplicate and Paste Keys): the copied shape without its place. The points whose
 * position keys were just placed on each `frames` (source frame, new frame) of `layers` (selected keys,
 * the new ones) move together, so their centre shows on the new frame where the same points' centre
 * did there before the copy (`before`: the document as it was). Their shape, and how the copied pieces
 * sit together, stay as copied. Detail points follow their parents. Returns how many keys changed. */
int keys_keep_place(Document &doc, const Document &before, const std::vector<uint64_t> &layers,
                    const std::vector<std::pair<int, int>> &frames);
/* Whether bones move any point of `layer` (its Armature modifier, or Parent Bone moving its points). */
bool layer_bones_move_points(const Document &doc, const Layer &layer);

}  // namespace oanim
