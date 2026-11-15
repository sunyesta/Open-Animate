#pragma once

/* Symmetrize Layers' animation: what the other side's copy keeps of the keys (src/ops/layer_ops.cc makes the copy).
 *
 * - Mirror (the default): the copy plays the source's animation mirrored, every timeline: each key flipped as its
 *   setup value is (points and handles across, the layers inside with their x and turn negated, bones reflected), the
 *   timing (interpolation, timing curves, breakdowns, holds) as it was. Keys of an action of a bone layer around the
 *   copy go to that action's mirror (Blink_L's into Blink_R; a bone's own action into the one its other side turns the
 *   other way by, Head into Head 2; a controller's side into the opposite one), or are left out when there is none.
 *   Actions of the bone layers inside the copy are mirrored with it: they take their other side's names.
 * - Keep Partner's: the shape comes from the source, the animation from the partner it remakes, its keys moved onto
 *   the new points (by point where the drawings match, else each new point the keys of the old one nearest it).
 * - None: no point, handle, transform or bone keys, as Symmetrize first did. */

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <type_traits>
#include <vector>

#include "anim/channel.hh"
#include "core/math.hh"

namespace oanim {

struct Document;
struct Layer;
struct VectorDrawing;

enum class SymmetrizeAnimation : uint8_t { Mirror, KeepPartner, None };

/* Every key's value of `ch` through `map` (each timeline: the one being edited and every action's), their path
 * handles too (offsets, mirrored as the places they reach), and its last value. `map` is linear: a reflection. */
template<typename T, typename F> void channel_values_map(Channel<T> &ch, F &&map)
{
  const auto keys = [&](std::vector<Key<T>> &list) {
    for (Key<T> &k : list) {
      const T was = k.value;
      k.value = map(was);
      if constexpr (std::is_same_v<T, float2>) {
        if (k.path_handles != PathHandles::Auto) {
          k.path_in = map(was + k.path_in) - k.value;
          k.path_out = map(was + k.path_out) - k.value;
        }
      }
      k.selected = false;
    }
  };
  keys(ch.keys);
  for (auto &[name, list] : ch.actions) {
    keys(list);
  }
  if constexpr (std::is_same_v<T, float2>) {
    for (auto &[name, k] : ch.action_setup) {
      k.path_in = map(k.path_in) - map(T{});
      k.path_out = map(k.path_out) - map(T{});
    }
  }
  if (ch.has_last) {
    ch.last = map(ch.last);
  }
}

/* A drawing mirrored across its x = 0 from its setup pose (drawing_mirror_setup_x), keeping its keys mirrored. */
void drawing_mirror_setup_x_keeping_keys(VectorDrawing &drawing);

/* Where the keys of each action go on the other side of `source` (a sided layer or group about to be copied across):
 * names left out stay as they are, a name mapped to nothing has its keys left out. `notes` says what had nowhere to go
 * once its keys are known to be there (symmetrize_actions_dropped). */
struct SymmetrizeNames {
  std::map<std::string, std::optional<std::string>> to;
  /* The bone layers inside `source` (by id), whose own actions are renamed with them. */
  std::vector<uint64_t> inside_owners;
  std::string rename(const std::string &name, bool *r_dropped) const;
};
SymmetrizeNames symmetrize_action_names(Document &doc, const Layer &source);

/* `copy` (the source copied, its contents mirrored) with its actions under their other side's names, keys of those that
 * have none left out: their names, for the status bar. Its bone layers' lists (actions, how they play, fixes, a
 * controller's sides, which swap Left and Right, and its spots) follow. */
std::vector<std::string> symmetrize_actions_apply(Layer &copy, const SymmetrizeNames &names);

/* `now` (the remade partner) with `old`'s animation (the partner as it was): its keys, moved onto the new drawings'
 * points, the transforms' as changes from the setup, the bones' by name; layers inside matched by id. */
void symmetrize_keep_partner(Layer &now, const Layer &old);

}  // namespace oanim
