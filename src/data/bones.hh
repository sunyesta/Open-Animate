#pragma once

/* Skeletons: where each bone of a bone layer is, in the setup pose (frame 0) and now.
 *
 * A bone's frame is its parent's frame (a root's is the bone layer's space) moved by its
 * position, turned by its angle and scaled by its scale. What moves bound artwork is each
 * bone's change from setup to now: skin = pose * setup^-1. */

#include <functional>
#include <map>
#include <string>
#include <vector>

#include "core/math.hh"

namespace oanim {

struct Bone;
struct BoneCollection;
struct Collection;
struct BoneConstraint;
enum class BoneConstraintType;
struct Document;
struct Layer;

struct BonePose {
  uint64_t id = 0;
  /* Bone frame -> bone layer space, in the setup pose and now. */
  Transform2D setup;
  Transform2D pose;
  /* Setup to now, in bone layer space: what the bone moves (weights, layers bound to it). A 2 Axis Controller's is its
   * knob's, which moves and turns like a pin inside the box. */
  Transform2D skin;
  /* Setup to now of the bone itself: for a controller the box's, resting on its parent (else the same as `skin`). */
  Transform2D box_skin;
  /* Bone frame -> bone layer space now, at a controller's knob, turned by its angle (else the same as `pose`): what
   * children that follow the knob hang from. */
  Transform2D knob;
  /* What carries an independent knob: its Knob Parent's setup to now (else none). */
  Transform2D knob_parent_skin;
  /* How far a controller's constraints move its knob, in frames against its box (else none). */
  float2 knob_pull;
  /* Where the bone runs in the setup pose and now (bone layer space). */
  float2 setup_head, setup_tail;
  float2 head, tail;
  /* How far it is stretched along its length against its setup (posing; 1 unstretched). */
  float stretch = 1.0f;
};

/* Every bone of a bone layer, in the order of `layer.bones`. `setup_frame`: the document is on
 * frame 0, where moving a bone changes the setup pose itself. Elsewhere an edit not yet keyed
 * is a pose: the setup stays where the bone was before it. */
std::vector<BonePose> armature_pose(const Layer &armature, bool setup_frame = true);
/* Which way the axes `bone`'s angle is measured in point now (bone layer space): its parent's as posed,
 * or, for a bone that doesn't inherit its parent's turn (Relations), its parent's as they rest. 0 for a
 * root. For drawing what is measured from them (Limit Angle's lines). */
float bone_parent_axes_angle(const Bone &bone, const BonePose *parent, bool setup_frame);
/* While one is alive, armature_pose works each bone layer's pose out once and hands back the same
 * one after: for a render, where nothing changes and every layer a rig moves asks for its pose.
 * Scopes nest; the poses are forgotten when the outermost ends. Each thread has its own (copies worked out side by side
 * mustn't see each other's), lent to threads working for it with ArmaturePoseCacheBorrow. */
struct ArmaturePoseCacheScope {
  ArmaturePoseCacheScope();
  ~ArmaturePoseCacheScope();
  ArmaturePoseCacheScope(const ArmaturePoseCacheScope &) = delete;
  ArmaturePoseCacheScope &operator=(const ArmaturePoseCacheScope &) = delete;

 private:
  bool owner_ = false;
};
/* The poses kept by the ArmaturePoseCacheScope in effect on this thread (null outside one), to lend. */
const void *armature_pose_cache_current();
/* While it lasts, this thread keeps poses in `cache` (from armature_pose_cache_current on the thread whose scope
 * outlasts this; null: none kept). */
class ArmaturePoseCacheBorrow {
 public:
  explicit ArmaturePoseCacheBorrow(const void *cache);
  ~ArmaturePoseCacheBorrow();
  ArmaturePoseCacheBorrow(const ArmaturePoseCacheBorrow &) = delete;
  ArmaturePoseCacheBorrow &operator=(const ArmaturePoseCacheBorrow &) = delete;

 private:
  const void *before_ = nullptr;
};
/* The pose `bones` would have in place of the armature's own (an edited copy of them), as armature_pose works it out;
 * never kept. */
std::vector<BonePose> armature_pose_of(const Layer &armature, const std::vector<Bone> &bones, bool setup_frame);
/* The pose without bone dynamics: where the keys (constraints and IK included) put the bones.
 * Editing works from it, so a dynamic bone lands where it is put, the physics swinging after. */
std::vector<BonePose> armature_keyed_pose(const Layer &armature, bool setup_frame);
/* A root's frame: that of its parent in a bone layer around it, or none. */
Transform2D bone_outer_frame(const Bone &bone, bool setup_frame);
/* Every bone with a parent in a bone layer around its own gets that parent's frame, the outermost bone layers first as
 * those inside hang from them. One whose parent has gone, or whose bone layer has left that one, lets go and stays
 * where it rests. */
void bone_outer_parents_update(Document &doc);
/* For a move of the bones picked in `moving`: marks those a bone moving in another of them carries (Bone::outer_carried). */
void bones_mark_carried(Document &doc, const std::vector<Layer *> &moving);
/* Interactive IK while posing (Moho's): turns the bone and its parents (up to a bone Ignored by
 * IK) so the bone's tip reaches `goal` (bone layer space); an Arc IK bone bends its chain evenly.
 * Returns false when the bone has no parent to turn with. */
bool armature_reach(Layer &armature, uint64_t bone, float2 goal);
/* IK points moved by hand. Where bone `i`'s IK End or IK Base puts its point, in `poses`. */
float2 armature_ik_point(const Layer &armature, const std::vector<BonePose> &poses, size_t i, BoneConstraintType type);
/* How a move of an IK point bends its chain: `more` bones longer (or shorter) than up to its base, stretching out of
 * reach, flipped to bend the other way, Soft drawn in near full reach, `free` of Limit Angle. */
struct IKReach {
  int more = 0;
  bool stretch = false, flip = false, soft = true, free = false;
};
/* How many bones a move with `more` bends. */
int armature_ik_chain_size(const Layer &armature, size_t i, BoneConstraintType type, int more);
/* Turns (and with stretch, stretches) bone `i`'s IK chain, as keyed, so its point reaches `goal` (a root's head: the
 * root moves). False when it has none. */
bool armature_ik_reach(Layer &armature, size_t i, BoneConstraintType type, float2 goal, const IKReach &how);
/* After an edit off the setup frame: every pinned IK End and IK Base whose chain the edit left alone (not moved from
 * `original`) back where `original` showed it (an end pinned to a bone where that bone took it), bases first. The
 * point `skip` of `skip_type` is the one being moved. `stretch` (Alt): a chain stretches to hold a point out of reach. */
void armature_ik_hold(Layer &armature, const std::vector<Bone> &original, size_t skip, BoneConstraintType skip_type,
                      bool stretch = false);
/* After clearing the pose off the setup frame (Alt G / Alt R / Alt S) from `original`: a pinned IK End whose chain lost
 * its scale (`scale`) reaches back to where it was; the pinned ends and bases left alone hold. */
void armature_ik_clear_hold(Layer &armature, const std::vector<Bone> &original, bool scale);
/* Why IK End `end` can't be pinned to bone `to` ("" when it can). */
std::string armature_ik_pin_refusal(const Layer &armature, const Bone &end, const Bone &to);
/* The frames bone `i`'s IK End's path runs between (its stretches): the setup frame, its keys and its chain's. */
std::vector<int> armature_ik_frames(const Layer &armature, size_t i);
/* The bend an IK End's path has on the stretch leaving frame `k0` (kept on a key there; none is straight). */
float2 ik_bend_on(const BoneConstraint &c, int k0);
/* The stretch of bone `i`'s IK End's path `frame` is in: the frames it runs between (false past the last). */
bool armature_ik_stretch_at(const Layer &armature, size_t i, int frame, int &k0, int &k1);
/* How much of its stretch's bend bone `i`'s IK End's point is off its way on `frame`: 2e(1-e), e how far along. */
float armature_ik_bend_weight(const Layer &armature, size_t i, int frame);
/* Bends bone `i`'s IK End's path out by `bend` on the stretch `frame` is in (kept on the key it leaves, the next keeping
 * its own); `frame_shown` the frame the bones are on. False where there is no stretch or it is bent so already. */
bool armature_ik_bend_set(Layer &armature, size_t i, int frame, float2 bend, int frame_shown);
/* Where bone `i`'s IK End's point is on `frame`, as the bones' keys and its pins have it (the bones alone: no action
 * bones or other layers). */
float2 armature_ik_point_at(const Layer &armature, size_t i, int frame);
/* Bone `i`'s IK End chain back to its setup size. */
bool armature_ik_clear_scale(Layer &armature, size_t i);
/* The angle (bone layer space) a Limit Angle on bone `i` measures its turn from: its parent's axes, as `poses` have
 * them, plus its setup angle. Its Min and Max are this plus each. */
float armature_limit_zero(const Layer &armature, const std::vector<BonePose> &poses, size_t i, bool setup_frame);
/* Turn one end (Max, or Min) of Limit Angle `index` on bone `i` to point at `at` (bone layer space) from the bone's
 * head, the nearest way round from where it is; kept 0.05 rad past the other end and within a turn either way. False:
 * nothing changed (no such limit, `at` on the head). */
bool armature_limit_end_toward(Layer &armature, size_t i, size_t index, bool max, float2 at, bool setup_frame);
/* A bone's IK End or IK Base (enabled; null: none). */
const BoneConstraint *bone_ik_end(const Bone &bone);
const BoneConstraint *bone_ik_base(const Bone &bone);
/* The bone whose tail an IK End or IK Base on bone `i` puts its point at: itself, or with Head its parent (-1: a root's
 * head). */
int armature_ik_point_bone(const Layer &armature, size_t i, bool head);
/* The chain the IK End (or IK Base) of bone `i` turns, its point's bone first, up to the nearest IK Base (empty: none). */
std::vector<size_t> armature_ik_chain(const Layer &armature, size_t i, BoneConstraintType type);
const BonePose *bone_pose_find(const std::vector<BonePose> &poses, uint64_t id);
/* Limit to Shape: where a head (bone layer space) is kept, inside the constraint's shape as last worked
 * out (anim/shape_limit.hh); `head` itself when it fits or there is no shape. */
float2 bone_shape_limit(const BoneConstraint &c, float2 head);
/* How many times a Look At's or Limit to Shape's fit was worked out (not taken from the ones kept), since the last
 * clear: oanim.wm.deform_counts()["shape_fits"]. */
long long bone_shape_fits_count();
void bone_shape_fits_count_clear();
/* Affect Transform: a bone just moved (its position differs from what its keys give) past its Limit to
 * Shape edge is put back where the limit holds it, on a posed frame, before the move is recorded. */
void bone_shape_limit_affect(const Layer &armature, Bone &bone);
/* Look At: the way an eye at `eye` looks at `target` standing `target_depth` in front of the face (yaw
 * and pitch, radians, from the camera), the face turned `face` in the picture. */
float2 bone_look_gaze(float face, float2 eye, float2 target, float target_depth);
Bone *bone_find(Layer &armature, uint64_t id);
const Bone *bone_find(const Layer &armature, uint64_t id);
const Bone *bone_find_by_name(const Layer &armature, const std::string &name);
/* A bone and everything below it. */
bool bone_is_descendant(const Layer &armature, uint64_t id, uint64_t ancestor);

/* Selects or deselects a whole bone: its body and both ends. */
void bone_select(Bone &bone, bool select);
void armature_deselect_all(Layer &armature);
/* Whether an end is selected, counting the shared joint of connected bones. */
bool bone_head_selected(const Layer &armature, const Bone &bone);
bool bone_tail_selected(const Layer &armature, const Bone &bone);
/* After ends were picked one by one: a bone whose two ends are both selected is selected, as in
 * Blender, and one missing an end is not. */
void armature_flush_selection(Layer &armature);

/* G, R and S on bones, from the bones as they were (`original`) so a drag can be redone every
 * update. `delta` is in the bone layer's space. G moves a bone picked by its body or base, and
 * aims a bone picked by its tip alone (on the setup frame the tip also sets its length); R turns
 * picked bones about their bases; S scales them. Children always come along, as in Moho. */
bool armature_any_picked(const Layer &armature);
/* Alt G, Alt R and Alt S while posing, as Blender's Clear Location / Rotation / Scale: the picked
 * bones' position, angle or scale go back to the setup pose (frame 0). Returns false when no bone
 * is picked. */
bool armature_clear_pose(Layer &armature, bool position, bool angle, bool scale);
/* A bone's position and angle in the setup pose (frame 0). Posing shows them as Blender's pose
 * transform: Transform and Angle, the change from these, which is what their keys hold. */
float2 bone_setup_position(const Bone &bone);
float bone_setup_angle(const Bone &bone);
/* A move of the bone's base from its setup position, measured along its rest axes (x along the bone
 * as it rests in the setup pose, y across it), and back to a position in its parent's space. */
float2 bone_transform_from_position(const Bone &bone, float2 position);
float2 bone_position_from_transform(const Bone &bone, float2 transform);
/* Transform and Angle (Bone::transform, Bone::turn) from the bone's position and angle, and back. */
void bone_changes_from_values(Bone &bone);
void bone_values_from_changes(Bone &bone);
/* Frame 0's edits become the setup pose (the bone's changes there are none). */
void bone_take_setup(Bone &bone);
/* The bone's position and angle as its keys have them on `frame` (the setup plus its Transform or
 * Angle there); not animated, as they are now. `without_action_bones`: less what action bone actions add. */
float2 bone_position_at(const Bone &bone, int frame, bool without_action_bones);
float bone_angle_at(const Bone &bone, int frame, bool without_action_bones);
/* The bases of the picked bones (bone layer space), for the pivot shown while turning. */
std::vector<float2> armature_picked_heads(const Layer &armature, bool setup_frame);
/* `stretch` (Alt, posing): a grabbed tip goes exactly to the mouse, the bone stretching; a connected bone grabbed by
 * its body moves whole, its parent turning and stretching to stay connected; pinned points out of reach stretch their
 * chains to hold. */
void armature_grab_selected(Layer &armature, const std::vector<Bone> &original, float2 delta, bool setup_frame,
                            bool auto_ik = false, bool stretch = false);
void armature_rotate_selected(Layer &armature, const std::vector<Bone> &original, float angle,
                              bool setup_frame = false);
/* S. On the setup frame it resizes the picked bones (their joints spread about the middle of
 * their bases, so bones get longer; their scale stays). Posing, it scales each along its own axes:
 * `axis` 0 both, 1 X (thickness), 2 Y (length); `squash` makes it longer and thinner (or shorter
 * and fatter), keeping its area. */
void armature_scale_selected(Layer &armature, const std::vector<Bone> &original, float factor, bool setup_frame,
                             int axis = 0, bool squash = false);
/* X mirror editing: every bone that changed since `original` puts its other side (by _L / _R name)
 * in the mirror image across the bone layer's vertical axis, on any frame. */
void armature_mirror_edits(Layer &armature, const std::vector<Bone> &original, bool setup_frame);

/* The Transform Bones gizmo (Moho's sz_transform_bones_gizmo). The bounds of the picked bones'
 * ends (bone layer space), at least 0.01 across; false when nothing is picked. */
bool armature_picked_bounds(const Layer &armature, bool setup_frame, float2 &lo, float2 &hi);
/* Sends each picked bone's base and tip through `map` (bone layer space), from `original`. Unpicked
 * children of picked bones stay where they are. The setup pose takes new lengths; a pose takes
 * scales instead. */
void armature_map_selected(Layer &armature, const std::vector<Bone> &original, const Transform2D &map,
                           bool setup_frame);
/* The same through any map (a Distort or Warp cage's): each bone's width follows how the map stretches
 * across it at its base. */
void armature_map_selected(Layer &armature, const std::vector<Bone> &original,
                           const std::function<float2(float2)> &map, bool setup_frame);
/* Move Without Children (posing), after a G, R or S from `original`: every unpicked child of a picked bone put
 * back where it showed before (its base and its tip), so only the picked bones move. A connected child's
 * base stays on its parent's tip: it keeps its direction and length instead. The setup pose takes new
 * lengths; a pose takes scales instead. */
void armature_keep_children(Layer &armature, const std::vector<Bone> &original, bool setup_frame);
/* Box selection. `inside` tests a point in bone layer space. Joints: on the setup frame the ends
 * inside are picked, as Blender's edit-mode box select does (a bone with both ends inside is
 * selected); posing, a bone with either end inside is picked whole, as its pose mode does. Bones: a bone any part of
 * which is inside is picked whole, as Moho's gizmo does. `extend` keeps the selection; `deselect`
 * removes instead. */
/* `panels` (bone_panels): the collections panels the bones show through; their own alone when null. */
void armature_select_joints_in(Layer &armature, bool setup_frame, const std::function<bool(float2)> &inside,
                               bool extend, bool deselect, const std::vector<const Layer *> *panels = nullptr);
void armature_select_bones_in(Layer &armature, bool setup_frame, const std::function<bool(float2)> &inside,
                              bool extend, bool deselect, const std::vector<const Layer *> *panels = nullptr);
/* Puts bones' ends (setup pose, bone layer space) where `targets` says, by bone id, keeping every
 * other bone where it is (connected heads follow their parent's tail). `world_angles` (optional):
 * which way bones with no length point (bone layer space), as their ends can't say. */
void armature_set_joints(Layer &armature, const std::map<uint64_t, std::pair<float2, float2>> &targets,
                         const std::map<uint64_t, float> *world_angles = nullptr);

/* Blender's symmetry names: "arm_L" <-> "arm_R", "arm.L" <-> "arm.R", "Left arm" <-> "Right arm".
 * Names without a side come back unchanged. */
std::string bone_mirror_name(const std::string &name);
/* The other side's name for `action`, an action of bone `bone`: where it has the bone's name, that flips with a Left or
 * Right in the rest ("Pupil_L Left" -> "Pupil_R Right"); otherwise as bone_mirror_name. */
std::string action_mirror_name(const std::string &action, const std::string &bone);
/* The id of the bone on the other side (by name), or `id` itself when there is none. */
uint64_t bone_mirror_id(const Layer &armature, uint64_t id);

/* A bone colour set's shades (display colours): drawn normally, selected, and active. */
struct BoneColors {
  Color regular, select, active;
};
/* The shades of colour set `set` (0 Default Colors, 1-15 Blender's theme sets). */
BoneColors bone_color_set(int set);
/* "Default Colors", "01 - Red" ... "15 - Dark Green", "Custom Color Set". */
const char *bone_color_set_name(int set);
/* "DEFAULT", "THEME01" ... "THEME15", "CUSTOM" (as Blender's Python names them); -1 for none. */
std::string bone_color_set_identifier(int set);
int bone_color_set_from_identifier(const std::string &identifier);
/* The shades a bone is drawn in. */
BoneColors bone_colors(const Bone &bone);
/* Gives a bone colour set `set`. Going to Custom starts from the shades it had, as in Blender. */
void bone_set_color_set(Bone &bone, int set);
/* The shades a drawing edited with bones is drawn in (Layer::color_set), and giving it a set, as a bone's. */
BoneColors layer_colors(const Layer &layer);
void layer_set_color_set(Layer &layer, int set);

/* --- Collections ---------------------------------------------------------------------------- */

/* The All collection's name: every bone layer's panel has it, holding all its bones (and editable
 * drawings); no collection takes the name. */
inline constexpr const char *BONE_COLLECTION_ALL = "All";
Collection *collection_find(Document &doc, uint64_t id);
const Collection *collection_find(const Document &doc, uint64_t id);
Collection *collection_find_by_name(Document &doc, const std::string &name);
const Collection *collection_find_by_name(const Document &doc, const std::string &name);
/* Its name ("" for none). */
std::string collection_name(const Document &doc, uint64_t id);
/* "Collection", "Collection.001", ... unique among the document's collections (and not All). */
std::string collection_unique_name(const Document &doc, const std::string &name);
/* A new collection, its name made unique. */
Collection &collection_new(Document &doc, const std::string &name);
/* The collection of that name, made if there is none (null for All or nothing). */
Collection *collection_ensure(Document &doc, const std::string &name);
/* Deletes a collection: every bone and layer leaves it, and every bone layer's panel loses it. */
void collection_delete(Document &doc, uint64_t id);
/* Empties a collection: every bone and layer leaves it, and it stays (on the panels it is on). How many left it. */
int collection_unassign_all(Document &doc, uint64_t id);
/* How many of the bone layer's selected bones, and of the drawings Assign takes (collection_drawings), Assign
 * Selected (`assign`) or Unassign Selected would change for collection `id`. */
void collection_selected_change(Document &doc, Layer &armature, uint64_t id, bool assign, int *r_bones,
                                int *r_drawings);
/* "2 bones, 1 drawing", "" for none: what Assign or Unassign Selected would change, as the menu shows it. */
std::string collection_change_text(int bones, int drawings);
/* How many of layer `layer` and the picked layers a Layer tab chip's Assign Selected (`assign`) or Unassign Selected
 * would change for collection `id`, and that as its menu shows it ("2 layers", "" for none). */
int collection_layers_change(Document &doc, uint64_t layer, uint64_t id, bool assign);
std::string collection_layers_change_text(int layers);
/* Ids as names, and names as ids (those not found left out). */
std::vector<std::string> collection_names(const Document &doc, const std::vector<uint64_t> &ids);

/* A bone layer's panel entry for a collection. */
BoneCollection *bone_collection_find(Layer &armature, uint64_t id);
const BoneCollection *bone_collection_find(const Layer &armature, uint64_t id);
BoneCollection *bone_collection_find_by_name(const Document &doc, Layer &armature, const std::string &name);
/* Whether a collection shows: by its eye, or, while any collection is soloed (All included), by its
 * star. */
bool bone_collection_shown(const Layer &armature, const BoneCollection &collection);
/* Whether All shows. */
bool bone_collection_all_shown(const Layer &armature);
/* Whether a bone (or an editable drawing, by its collections) shows: as in Blender, while any
 * collection holding it shows, and always when none on this panel holds it (in no collection). All holds
 * everything, so while it shows, everything does. */
bool bone_collections_show(const Layer &armature, const std::vector<uint64_t> &collections);
bool bone_shown(const Layer &armature, const Bone &bone);
/* The collections panels a bone of `armature` shows through: while a bone layer around it is worked in (active) and it
 * is a sub bone group shown inside that one, the worked-in one's and each sub bone group's on the way down to its own,
 * so a collection hidden on the panel worked in hides the inner groups' bones in it too; else its own alone. */
std::vector<const Layer *> bone_panels(const Document &doc, const Layer &armature);
/* Whether a bone shows through every one of `panels` (from bone_panels). */
bool bone_shown(const std::vector<const Layer *> &panels, const Bone &bone);
/* Whether a drawing is edited along with its bone layer's bones: it is Editable in Bone Group, and
 * shows by its collections. */
bool layer_edited_with_bones(const Document &doc, const Layer &layer);
/* Puts the document's collection `id` on the bone layer's panel after the active one (if it isn't there)
 * and makes it active. */
BoneCollection &bone_collection_add(Layer &armature, uint64_t id);
/* Puts it on the bone layer's panel, last, if it isn't there; the active one stays. */
void bone_collection_ensure(Layer &armature, uint64_t id);
/* Takes a collection off the bone layer's panel; its bones and drawings stay in it. */
void bone_collection_remove(Layer &armature, uint64_t id);
/* The bone layer whose collections M and Shift M (and Assign) work with: the active layer when it is a
 * bone layer, else the one the active drawing is inside; null for neither. */
Layer *collection_armature(Document &doc);
/* The drawings inside `armature` they take, of those Editable in Bone Group: those picked in the Layers
 * editor, the active layer when it is one of them, and those edited along with the bones whose points
 * are selected in the viewport. */
std::vector<Layer *> collection_drawings(Document &doc, const Layer &armature);
/* What the M menu's collections are given to: in the Layers editor (`in_layers`, or with no bone layer active)
 * the picked layers; otherwise the active bone layer's selected bones and the drawings edited with them that
 * are picked. */
void collection_targets(Document &doc, bool in_layers, std::vector<Bone *> &r_bones, std::vector<Layer *> &r_layers);
/* Bones that no longer show are deselected (after hiding or soloing), so moves leave them be. */
void armature_deselect_hidden(Layer &armature);

/* The nearest bone layer the layer sits in, or null. */
const Layer *layer_armature(const Document &doc, uint64_t layer_id);
/* The group (inside that bone layer) above the layer whose Parent Bone moves it, the outermost if
 * several have one, or null. Its bone overrides the layer's own Parent Bone and weights: everything
 * inside moves as a whole with it. */
const Layer *layer_binding_group(const Document &doc, uint64_t layer_id);
/* Gives every vector layer inside a bone layer its Armature modifier, and takes it from those
 * that left one. Returns true when anything changed. */
bool document_sync_armature_modifiers(Document &doc);

}  // namespace oanim
