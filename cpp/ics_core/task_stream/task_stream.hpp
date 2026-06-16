#pragma once

#include <algorithm>
#include <string>
#include <vector>

namespace czr005::ics {

struct TaskLeg {
  std::string segment_id;
  int task_id = -1;
  int pallet_id = -1;
  double pass_time = 0.0;
  double std = 0.0;
  int start = -1;
  int goal = -1;
  int original_start = -1;
  int original_goal = -1;
  double original_entry_time = 0.0;
  std::string leg;
  bool early_bag_split = false;
};

class TaskStream {
 public:
  void add(TaskLeg task) { tasks_.push_back(std::move(task)); }

  void sort_by_pass_time() {
    std::stable_sort(tasks_.begin(), tasks_.end(), [](const TaskLeg& left, const TaskLeg& right) {
      if (left.pass_time != right.pass_time) {
        return left.pass_time < right.pass_time;
      }
      return left.task_id < right.task_id;
    });
  }

  [[nodiscard]] const std::vector<TaskLeg>& tasks() const { return tasks_; }
  [[nodiscard]] std::size_t size() const { return tasks_.size(); }

 private:
  std::vector<TaskLeg> tasks_;
};

}  // namespace czr005::ics

