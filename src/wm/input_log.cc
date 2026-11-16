#include "wm/input_log.hh"

#include <deque>

#include "wm/pen_input.hh"

namespace oanim {

/* The window's messages and SDL's events both come on the main thread. */
static bool g_on = false;
static std::deque<InputLogEntry> g_entries;
static constexpr size_t MAX_ENTRIES = 500000;

void input_log_set(bool on)
{
  g_on = on;
  g_entries.clear();
}

bool input_log_on()
{
  return g_on;
}

void input_log_add(const char *what, uint64_t which, float x, float y, int button, uint32_t extra, bool dropped)
{
  if (!g_on) {
    return;
  }
  g_entries.push_back({pen_now(), what, which, x, y, button, extra, dropped});
  if (g_entries.size() > MAX_ENTRIES) {
    g_entries.pop_front();
  }
}

std::vector<InputLogEntry> input_log_take()
{
  std::vector<InputLogEntry> out(g_entries.begin(), g_entries.end());
  g_entries.clear();
  return out;
}

}  // namespace oanim
