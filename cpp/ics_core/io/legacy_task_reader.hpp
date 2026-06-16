#pragma once

#include <fstream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "ics_core/task_stream/task_stream.hpp"

namespace czr005::ics {

constexpr double kEarlyBagThresholdSeconds = 4800.0;
constexpr int kStorageInGoal = 47;
constexpr int kStorageOutStart = 52;
constexpr double kStorageOutLeadSeconds = 2700.0;

struct LegacyTaskReadResult {
  std::string header;
  TaskStream stream;
  int raw_task_count = 0;
  int direct_raw_task_count = 0;
  int early_split_raw_task_count = 0;
  std::map<int, int> expanded_by_start;
};

struct RawLegacyTask {
  int task_id = -1;
  double entry_time = 0.0;
  double std_time = 0.0;
  int start = -1;
  int goal = -1;
  int source_line = -1;
};

inline bool is_blank_line(const std::string& line) {
  return line.find_first_not_of(" \t\r\n") == std::string::npos;
}

inline TaskLeg make_task_leg(const RawLegacyTask& raw,
                             std::string leg,
                             bool early_bag_split,
                             double pass_time,
                             int start,
                             int goal) {
  TaskLeg task;
  task.segment_id = std::to_string(raw.task_id) + ":" + leg;
  task.task_id = raw.task_id;
  task.pallet_id = raw.task_id;
  task.pass_time = pass_time;
  task.std = raw.std_time;
  task.start = start;
  task.goal = goal;
  task.original_start = raw.start;
  task.original_goal = raw.goal;
  task.original_entry_time = raw.entry_time;
  task.leg = std::move(leg);
  task.early_bag_split = early_bag_split;
  task.source_line = raw.source_line;
  return task;
}

inline void add_task_leg(LegacyTaskReadResult& result, TaskLeg task) {
  ++result.expanded_by_start[task.start];
  result.stream.add(std::move(task));
}

inline LegacyTaskReadResult read_legacy_inputdata(
    const std::string& path,
    double early_bag_threshold = kEarlyBagThresholdSeconds,
    int storage_in_goal = kStorageInGoal,
    int storage_out_start = kStorageOutStart,
    double storage_out_lead_seconds = kStorageOutLeadSeconds) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("failed to open legacy inputdata: " + path);
  }

  LegacyTaskReadResult result;
  if (!std::getline(input, result.header)) {
    throw std::runtime_error("empty legacy inputdata: " + path);
  }

  std::string line;
  int line_no = 1;
  while (std::getline(input, line)) {
    ++line_no;
    if (is_blank_line(line)) {
      continue;
    }

    std::istringstream stream(line);
    RawLegacyTask raw;
    raw.source_line = line_no;
    stream >> raw.task_id >> raw.entry_time >> raw.std_time >> raw.start >> raw.goal;
    if (!stream) {
      throw std::runtime_error("invalid legacy inputdata row at line " + std::to_string(line_no));
    }

    ++result.raw_task_count;
    if (raw.std_time - raw.entry_time < early_bag_threshold) {
      ++result.direct_raw_task_count;
      add_task_leg(result,
                   make_task_leg(raw, "direct", false, raw.entry_time, raw.start, raw.goal));
    } else {
      ++result.early_split_raw_task_count;
      add_task_leg(result,
                   make_task_leg(raw, "storage_in", true, raw.entry_time, raw.start, storage_in_goal));
      add_task_leg(result,
                   make_task_leg(raw,
                                 "storage_out",
                                 true,
                                 raw.std_time - storage_out_lead_seconds,
                                 storage_out_start,
                                 raw.goal));
    }
  }

  result.stream.sort_by_pass_time();
  return result;
}

}  // namespace czr005::ics
