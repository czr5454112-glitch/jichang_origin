#pragma once

namespace czr005::ics {

struct PathNode {
  int location = -1;
  double t1 = 0.0;
  double t2 = 0.0;
  double gcost = 0.0;
  double hcost = 0.0;
  double fcost = 0.0;
};

}  // namespace czr005::ics

