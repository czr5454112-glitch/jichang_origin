#pragma once

#include <algorithm>
#include <numeric>
#include <vector>

#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar_types.hpp"

namespace czr005::ics {

struct EpisodeMetrics {
  int planned_count = 0;
  int unplanned_count = 0;
  double mean_travel_time = 0.0;
  double makespan = 0.0;
  int reservation_conflicts = 0;
};

inline EpisodeMetrics compute_episode_metrics(const std::vector<std::vector<PathNode>>& routes,
                                              int unplanned_count,
                                              const ReservationTable& reservations) {
  std::vector<double> travel_times;
  double makespan = 0.0;
  for (const auto& route : routes) {
    if (route.empty()) {
      continue;
    }
    travel_times.push_back(route.back().t2 - route.front().t1);
    makespan = std::max(makespan, route.back().t2);
  }
  const double sum = std::accumulate(travel_times.begin(), travel_times.end(), 0.0);
  return EpisodeMetrics{static_cast<int>(travel_times.size()),
                        unplanned_count,
                        travel_times.empty() ? 0.0 : sum / static_cast<double>(travel_times.size()),
                        makespan,
                        reservations.conflict_count()};
}

}  // namespace czr005::ics

