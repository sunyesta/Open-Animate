#pragma once

#include <vector>

#include "anim/motion_path.hh"

namespace oanim {

struct Context;

/* Stretches picked in different stretches with the Motion Path tool: a timing edit to the active one (the one Path
 * Timing shows) is copied to the other picked stretches the edit left as they were, each fitted to its own length
 * (motion_path_span_interp_set). Started before the edit (an operator flagged OPTYPE_TIMING, a drag, a stroke) and
 * finished after it, inside its undo step; finish may be called again after each step of a drag shown live. */
struct PickedStretchSync {
  struct Snap {
    MotionPathPickedStretch pick;
    KeySettings settings;
    TimingCurve curve;
  };
  std::vector<Snap> snaps;
  int active = -1;
  void start(Context &C);
  /* How many stretches took the active one's timing. */
  int finish(Context &C) const;
};

}  // namespace oanim
