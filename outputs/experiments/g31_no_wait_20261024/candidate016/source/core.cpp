// Research prototype: local bounded lookahead orders a neighbour DFS; a successful
// DFS commits an entire exact-time continuation certificate. This is a separate
// G31 continuous-motion engine; optional in-route transactions retain a fallback.
// Safety queries can reach the goal independently of the local scoring horizon.
// Every calendar is owned by one node. The sequential simulator is the transaction
// coordinator: DFS is read-only, and only a complete certificate is committed.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <functional>
#include <limits>
#include <map>
#include <numeric>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace py = pybind11;
namespace g31_nowait {
constexpr double inf = std::numeric_limits<double>::infinity();
constexpr double ticks_per_second = 1000000.0;
std::int64_t tick(double value) { return static_cast<std::int64_t>(std::llround(value*ticks_per_second)); }
double seconds(std::int64_t value) { return static_cast<double>(value)/ticks_per_second; }
double process_cpu_seconds() {
#ifdef _WIN32
    FILETIME created,exited,kernel,user;
    if (!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user))
        throw std::runtime_error("GetProcessTimes failed");
    ULARGE_INTEGER k,u; k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;
    u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;
    return (static_cast<double>(k.QuadPart)+static_cast<double>(u.QuadPart))*1e-7;
#else
    return static_cast<double>(std::clock())/CLOCKS_PER_SEC;
#endif
}

struct Config {
    double end_time = 98259.0;
    int min_depth = 1, max_depth = 4;
    bool adaptive = true, source_fifo = true;
    std::string source_fifo_order = "activation";
    double congestion_weight = 1.0;
    double pressure_window = 30.0;
    int max_expansions = 256, max_score_expansions = 256;
    int max_retries = 10000;
    std::uint64_t max_events = 10000000;
    std::string retry_mode = "futurecalendar_jump";
    double retry_step = 1.0, release_quantum = 1.0, completion_quantum = 1.0;
    double source_generation_interval = 1.0;
    bool terminal_reservation_service = true;
    bool audit_failed_calendar_hash = false;
    bool enable_ebs_predecessor_gate = false;
    std::string interval_mode = "closed_legacy";
    bool strict_endpoint_resources = false;
    double edge_entry_headway_seconds = 0.0;
    bool skip_scoring_single_choice = false;
    bool enable_inroute_replanning = false;
    double time_grid_seconds = 0.000001;
    double max_route_excess_seconds = inf;
    double route_excess_retry_relaxation_rate = 0.0;
    int future_source_reservation_horizon_seconds = 0;
    double future_source_reservation_min_wait_seconds = 2.0;
    bool future_source_prefer_earlier_finish = false;
    bool future_source_prefer_only_without_ready_successor = false;
};
struct Edge { int to; double travel; int id; };
struct Node { int id; double service; std::vector<Edge> out; int indegree = 0; };
struct Step {
    int node; double arrival, departure;
    int requested_k=0, actual_query_depth=0;
    std::uint64_t local_score_queries=0;
    bool score_budget_exhausted=false;
};
struct ScoreBudget {
    std::uint64_t expansions=0;
    std::uint64_t actual_queries=0;
    int actual_query_depth=0;
    bool exhausted=false;
};
struct Reservation { double end; int task; std::uint64_t id; };
using Calendar = std::multimap<double, Reservation>;
struct Task {
    std::string segment_id, leg;
    std::int64_t task_id = 0;
    double release = 0, deadline = 0;
    double generated_release = 0;
    // Observational clocks only: source activation may precede the first
    // actual planning attempt while another FIFO head remains pending.
    // A failed search must never reset first_planning_attempt_time.
    double activation_time = -1, first_planning_attempt_time = -1;
    double last_effective_route_excess = inf, admission_effective_route_excess = inf;
    double admission_static_remaining = inf, admission_route_excess = inf;
    int start = 0, goal = 0;
    bool released = false, activated = false, admitted = false, complete_event = false;
    std::uint64_t generation = 0;
    int attempts = 0;
    double admission = inf, finish = inf, cleanup = inf, completion_epoch = inf;
    std::string reason = "not_released";
    std::vector<Step> route;
    std::vector<std::pair<int, Calendar::iterator>> reservations;
    std::vector<std::pair<int, Calendar::iterator>> edge_reservations;
    std::uint64_t expansions = 0, scoring_queries = 0, safety_queries = 0;
    std::uint64_t backtracks = 0, score_expansions = 0;
    int max_certificate_depth = 0, max_observation_depth = 0;
    int predecessor = -1, dependent = -1;
    std::uint64_t commit_order = 0;
    std::uint64_t route_generation = 0;
    int arrived_index = 0;
    bool physically_completed = false;
    bool future_reserved=false;
    std::uint64_t future_success_comparisons=0;
    bool future_success_preferred=false;
    double compared_immediate_finish=inf;
    std::uint64_t ready_successor_checks=0,ready_successor_skips=0,ready_successor_activation_pending_skips=0;
    double reservation_time=inf,planned_admission=inf,planned_finish=inf,planned_cleanup=inf;
    std::uint64_t reservation_order=0,future_searches=0,future_calendar_entries_scanned=0;
    std::vector<Step> reserved_route;
    std::vector<std::uint64_t> reserved_node_ids,reserved_edge_ids;
    std::vector<std::uint64_t> node_reservation_ids,edge_reservation_ids;
};
struct RollingRecord {
    std::string kind;
    std::uint64_t order=0,old_generation=0,new_generation=0,event_generation=0;
    int task=-1,index=0,node=-1;
    double time=0,finish=0,cleanup=0,planned_admission=0;
    std::uint64_t reference_reservation_order=0;
    bool valid=true;
    std::vector<Step> route;
    std::vector<std::uint64_t> node_ids,edge_ids,removed;
};
struct GoalData {
    std::vector<double> h;
    std::vector<int> hops, decision_nodes, shortest_successor;
};
struct Event {
    double time;
    int kind; // completion = 0, release = 1, attempt = 2
    std::uint64_t serial;
    int task;
    std::uint64_t generation;
    int route_index=-1;
};
struct EventAfter {
    bool operator()(const Event& a, const Event& b) const {
        const int ap=(a.kind==4 || a.kind==5)?-1:a.kind,bp=(b.kind==4 || b.kind==5)?-1:b.kind;
        return std::tie(a.time,ap,a.serial) > std::tie(b.time,bp,b.serial);
    }
};
struct Attempt {
    int task;
    double admission;
    std::vector<unsigned char> visited;
    std::vector<Step> path;
    std::uint64_t expansions = 0, score_expansions = 0;
    std::uint64_t scoring_queries = 0, safety_queries = 0, backtracks = 0;
    double retry_at = inf;
    bool budget_exhausted = false, score_budget_exhausted = false;
    int max_depth = 0, max_observation_depth = 0;
    int ignore_owner=-1;
    double finish_bound=inf;
    std::uint64_t route_bound_prunes=0;
    bool forced_prefix=true,forced_prefix_denial=false;
};
struct Choice { Edge edge; double arrival,score; };

double finite_nonnegative(double x, const char* name) {
    if (!std::isfinite(x) || x < 0) throw std::invalid_argument(std::string(name)+" must be finite and nonnegative");
    return x;
}
double quantize(double t, double quantum) {
    if (quantum == 0) return t;
    return std::ceil(t / quantum) * quantum;
}
Config parse_config(const py::dict& d) {
    Config c;
    const std::set<std::string> allowed = {"end_time","min_depth","max_depth","adaptive","source_fifo",
        "congestion_weight","max_expansions","max_score_expansions","max_retries","max_events",
        "retry_mode","retry_step","release_quantum","completion_quantum","terminal_reservation_service",
        "audit_failed_calendar_hash","pressure_window","enable_ebs_predecessor_gate","source_generation_interval",
        "interval_mode","strict_endpoint_resources","edge_entry_headway_seconds","skip_scoring_single_choice",
        "enable_inroute_replanning","time_grid_seconds","max_route_excess_seconds","source_fifo_order",
        "route_excess_retry_relaxation_rate","future_source_reservation_horizon_seconds",
        "future_source_reservation_min_wait_seconds","future_source_prefer_earlier_finish","future_source_prefer_only_without_ready_successor"};
    for (auto item : d) if (!allowed.count(py::cast<std::string>(item.first)))
        throw std::invalid_argument("unknown config key: "+py::cast<std::string>(item.first));
#define READ_OPTION(name) if (d.contains(#name)) c.name = py::cast<decltype(c.name)>(d[#name]);
    READ_OPTION(end_time) READ_OPTION(min_depth) READ_OPTION(max_depth) READ_OPTION(adaptive)
    READ_OPTION(source_fifo) READ_OPTION(congestion_weight) READ_OPTION(max_expansions)
    READ_OPTION(max_score_expansions) READ_OPTION(max_retries) READ_OPTION(max_events)
    READ_OPTION(retry_mode) READ_OPTION(retry_step) READ_OPTION(release_quantum)
    READ_OPTION(completion_quantum) READ_OPTION(terminal_reservation_service) READ_OPTION(audit_failed_calendar_hash)
    READ_OPTION(pressure_window) READ_OPTION(enable_ebs_predecessor_gate)
    READ_OPTION(source_generation_interval)
    READ_OPTION(interval_mode) READ_OPTION(strict_endpoint_resources) READ_OPTION(edge_entry_headway_seconds)
    READ_OPTION(skip_scoring_single_choice)
    READ_OPTION(enable_inroute_replanning) READ_OPTION(time_grid_seconds) READ_OPTION(max_route_excess_seconds)
    READ_OPTION(source_fifo_order)
    READ_OPTION(route_excess_retry_relaxation_rate)
    READ_OPTION(future_source_reservation_min_wait_seconds)
    if (d.contains("future_source_prefer_earlier_finish")) {
        const auto value=d["future_source_prefer_earlier_finish"];
        if (!PyBool_Check(value.ptr()))
            throw std::invalid_argument("future_source_prefer_earlier_finish must be a boolean");
        c.future_source_prefer_earlier_finish=py::cast<bool>(value);
    }
    if (d.contains("future_source_prefer_only_without_ready_successor")) {
        const auto value=d["future_source_prefer_only_without_ready_successor"];
        if (!PyBool_Check(value.ptr()))
            throw std::invalid_argument("future_source_prefer_only_without_ready_successor must be a boolean");
        c.future_source_prefer_only_without_ready_successor=py::cast<bool>(value);
    }
    if (d.contains("future_source_reservation_horizon_seconds")) {
        const auto value=d["future_source_reservation_horizon_seconds"];
        if (!PyLong_Check(value.ptr()) || PyBool_Check(value.ptr()))
            throw std::invalid_argument("future_source_reservation_horizon_seconds must be an integer, not bool");
        c.future_source_reservation_horizon_seconds=py::cast<int>(value);
    }
#undef READ_OPTION
    finite_nonnegative(c.end_time,"end_time");
    finite_nonnegative(c.congestion_weight,"congestion_weight");
    finite_nonnegative(c.pressure_window,"pressure_window");
    finite_nonnegative(c.release_quantum,"release_quantum");
    finite_nonnegative(c.completion_quantum,"completion_quantum");
    finite_nonnegative(c.source_generation_interval,"source_generation_interval");
    finite_nonnegative(c.edge_entry_headway_seconds,"edge_entry_headway_seconds");
    finite_nonnegative(c.route_excess_retry_relaxation_rate,"route_excess_retry_relaxation_rate");
    finite_nonnegative(c.future_source_reservation_min_wait_seconds,"future_source_reservation_min_wait_seconds");
    if (c.future_source_reservation_horizon_seconds<0 || c.future_source_reservation_horizon_seconds>60)
        throw std::invalid_argument("future source reservation horizon must be 0..60 integer seconds");
    if (c.future_source_reservation_horizon_seconds>0 &&
        (c.interval_mode!="half_open" || !c.strict_endpoint_resources || c.edge_entry_headway_seconds!=2.0 ||
         !c.enable_inroute_replanning || !c.enable_ebs_predecessor_gate || !c.source_fifo || c.source_fifo_order!="canonical" ||
         c.release_quantum!=1.0 || c.completion_quantum!=1.0 || c.source_generation_interval!=1.0 || (c.congestion_weight!=0.0 && c.congestion_weight!=1.0)))
        throw std::invalid_argument("future source reservation requires canonical FIFO, causal rolling, strict half-open node/edge2 resources, q1 source/completion/feed and congestion weight exactly 0 or 1");
    if (c.future_source_prefer_earlier_finish && c.future_source_reservation_horizon_seconds==0)
        throw std::invalid_argument("earlier-finish source comparison requires enabled future source reservation");
    if (c.future_source_prefer_only_without_ready_successor && !c.future_source_prefer_earlier_finish)
        throw std::invalid_argument("ready-successor gate requires earlier-finish source preference");
    if (c.time_grid_seconds!=0.000001) throw std::invalid_argument("time_grid_seconds must equal 1e-6");
    if (c.source_fifo_order!="activation" && c.source_fifo_order!="canonical")
        throw std::invalid_argument("source_fifo_order must be activation or canonical");
    if (c.source_fifo_order=="canonical" && !c.source_fifo)
        throw std::invalid_argument("canonical source order requires source_fifo=true");
    if (d.contains("max_route_excess_seconds")) finite_nonnegative(c.max_route_excess_seconds,"max_route_excess_seconds");
    if (c.interval_mode!="closed_legacy" && c.interval_mode!="half_open")
        throw std::invalid_argument("interval_mode must be closed_legacy or half_open");
    if (c.route_excess_retry_relaxation_rate>0 &&
        (c.interval_mode!="half_open" || !std::isfinite(c.max_route_excess_seconds)))
        throw std::invalid_argument("retry cap relaxation requires half_open and a finite base route excess");
    if (c.strict_endpoint_resources && !c.terminal_reservation_service)
        throw std::invalid_argument("strict endpoint resources require terminal_reservation_service=true");
    if (c.enable_inroute_replanning && (c.interval_mode!="half_open" || !c.strict_endpoint_resources || c.edge_entry_headway_seconds!=2.0))
        throw std::invalid_argument("in-route replanning requires half_open, strict endpoint resources and exactly 2-second edge entry headway");
    if (!std::isfinite(c.retry_step) || c.retry_step <= 0) throw std::invalid_argument("retry_step must be positive");
    if (c.min_depth < 1 || c.max_depth < c.min_depth || c.max_depth > 32)
        throw std::invalid_argument("require 1 <= min_depth <= max_depth <= 32");
    if (c.max_expansions < 1 || c.max_score_expansions < 0 || c.max_retries < 0 || c.max_events < 1)
        throw std::invalid_argument("invalid search/retry/event budget");
    if (c.retry_mode=="calendar_jump") c.retry_mode="futurecalendar_jump";
    if (c.retry_mode != "futurecalendar_jump" && c.retry_mode != "1s" && c.retry_mode != "fixed_step")
        throw std::invalid_argument("retry_mode must be calendar_jump/futurecalendar_jump, 1s or fixed_step");
    return c;
}

class Planner {
    Config cfg;
    std::vector<Node> nodes;
    std::unordered_map<int,int> index;
    std::vector<std::vector<std::pair<int,double>>> reverse;
    std::vector<Task> tasks;
    std::vector<Calendar> calendars;
    std::vector<Calendar> edge_calendars;
    std::map<std::pair<int,int>,int> edge_ids;
    std::vector<std::pair<int,int>> edge_nodes;
    std::map<int,GoalData> goal_cache;
    std::map<int,std::vector<int>> source_queues;
    std::map<int,std::size_t> source_heads;
    std::map<int,double> last_source_admission;
    std::priority_queue<Event,std::vector<Event>,EventAfter> events;
    std::uint64_t next_serial = 0;
    std::uint64_t calendar_entries = 0, peak_calendar_entries = 0, peak_event_count = 0;
    std::uint64_t event_count = 0, planning_attempts = 0, failed_attempts = 0;
    std::uint64_t static_rank_fastpath_candidates=0,relaxed_source_attempts=0,relaxed_source_admissions=0;
    std::uint64_t search_budget_failures = 0, score_budget_exhaustions = 0;
    std::uint64_t source_ignored_conflicts = 0, goal_ignored_conflicts = 0;
    std::uint64_t failed_hash_checks = 0, retry_jumps = 0;
    std::uint64_t next_commit = 0;
    std::map<int,std::uint64_t> search_k_histogram, committed_k_histogram;
    std::map<int,std::uint64_t> actual_query_depth_histogram;
    std::uint64_t local_score_budget_exhausted_decisions=0, scored_neighbor_candidates=0;
    std::uint64_t edge_safety_queries=0, source_resource_queries=0, goal_resource_queries=0;
    std::uint64_t edge_calendar_entries=0, peak_edge_calendar_entries=0, skipped_single_choice_scoring=0;
    std::uint64_t next_reservation_id=1, next_ledger_order=1;
    std::vector<RollingRecord> rolling_records;
    std::vector<double> inroute_microseconds;
    std::uint64_t inroute_decisions=0,inroute_keep=0,inroute_attempts=0,inroute_success=0,inroute_fallback=0;
    std::uint64_t inroute_expansions=0,inroute_scoring_queries=0,inroute_safety_queries=0;
    std::uint64_t stale_arrivals=0,stale_cleanups=0,route_bound_prunes=0;
    std::map<int,std::uint64_t> source_node_conflicts,source_edge_conflicts,inroute_node_conflicts,inroute_edge_conflicts;
    std::vector<double> decision_microseconds;
    std::uint64_t future_searches=0,future_precommits=0,future_launches=0;
    std::uint64_t future_chain_nodes=0,future_calendar_queries=0,future_calendar_entries_scanned=0;
    std::uint64_t future_validation_queries=0,future_mask_empty=0,future_chain_rejections=0;
    std::uint64_t future_eligible_failures=0;
    std::uint64_t future_success_comparisons=0,future_success_preferred=0,future_success_kept_immediate=0;
    std::uint64_t future_success_finish_bound_rejections=0,future_success_mask_empty=0;
    std::uint64_t ready_successor_checks=0,ready_successor_skips=0,ready_successor_activation_pending_skips=0;
    double simulation_time = 0;
    bool event_budget_exhausted = false;
    double preprocessing_seconds = 0;
    bool fixed_two_second_calendars = false;

    bool half_open() const {return cfg.interval_mode=="half_open";}
    double add_time(double a,double b) const {
        if (!half_open()) return a+b;
        const auto value=tick(a)+tick(b);
        if (value<0 || value>1000000000000000LL) throw std::invalid_argument("physical time exceeds microsecond-grid supported range");
        return seconds(value);
    }
    double grid_release(double value) const {
        return half_open()?std::ceil(value*ticks_per_second)/ticks_per_second:value;
    }
    void require_grid_value(double value,const char* label) const {
        if (!half_open()) return;
        if (!std::isfinite(value) || value<0 || value>1e9 || std::abs(value*ticks_per_second-std::round(value*ticks_per_second))>1e-5)
            throw std::invalid_argument(std::string(label)+" must be nonnegative, <=1e9 seconds, and on the 1-microsecond physical grid");
    }

    int node_index(int id) const {
        auto it = index.find(id);
        if (it == index.end()) throw std::invalid_argument("unknown node id: "+std::to_string(id));
        return it->second;
    }
    void push_event(double t, int kind, int task, std::uint64_t generation = 0,int route_index=-1) {
        if (!std::isfinite(t)) return;
        events.push({t,kind,next_serial++,task,generation,route_index});
        peak_event_count = std::max<std::uint64_t>(peak_event_count,events.size());
    }
    // Closed endpoints are compared directly. Scan active entries by start rather
    // than invert rounded start+service: subtraction can lose more than one ULP
    // of the small start, and equal-start zero-length goals must not hide others.
    bool calendar_conflicts(const Calendar& c,double arrival,double departure,bool use_half_open,
                   double* latest_end=nullptr,double* earliest_cleanup=nullptr,int ignore_owner=-1) const {
        bool result = false;
        double end = -inf, cleanup = inf;
        if (use_half_open && (half_open()?tick(arrival)>=tick(departure):arrival>=departure)) {
            if (latest_end) *latest_end=end;
            if (earliest_cleanup) *earliest_cleanup=cleanup;
            return false;
        }
        // Every stored window is at most 2s under this validated tuple.
        // S < A-2s implies E < A, so these entries cannot contribute to
        // overlap, latest_end, or earliest_cleanup. Keep the original
        // upper loop and all exact tests; legacy/mixed durations fall back.
        auto it = use_half_open && fixed_two_second_calendars
            ? c.lower_bound(seconds(std::max<std::int64_t>(0,tick(arrival)-2000000LL)))
            : c.begin();
        for (; it != c.end() && it->first <= departure; ++it) {
            if (it->second.task==ignore_owner) continue;
            const bool overlap=use_half_open
                ? (half_open()?tick(arrival)<tick(it->second.end) && tick(it->first)<tick(departure)
                              :arrival<it->second.end && it->first<departure)
                : !(arrival > it->second.end || departure < it->first);
            if (overlap) {
                result = true;
                end = std::max(end,it->second.end);
                cleanup = std::min(cleanup,tasks[it->second.task].cleanup);
            }
        }
        if (latest_end) *latest_end = end;
        if (earliest_cleanup) *earliest_cleanup = cleanup;
        return result;
    }
    bool conflicts(int node,double arrival,double departure,double* latest_end=nullptr,
                   double* earliest_cleanup=nullptr,int ignore_owner=-1) const {
        return calendar_conflicts(calendars[node],arrival,departure,half_open(),latest_end,earliest_cleanup,ignore_owner);
    }
    const GoalData& goal_data(int goal) {
        auto found = goal_cache.find(goal);
        if (found != goal_cache.end()) return found->second;
        GoalData data;
        data.h.assign(nodes.size(),inf);
        if (cfg.future_source_reservation_horizon_seconds>0) data.shortest_successor.assign(nodes.size(),-1);
        data.hops.assign(nodes.size(),0);
        data.decision_nodes.assign(nodes.size(),0);
        using Entry = std::pair<double,int>;
        std::priority_queue<Entry,std::vector<Entry>,std::greater<Entry>> queue;
        data.h[goal] = 0;
        queue.push({0,goal});
        while (!queue.empty()) {
            const auto [dist,v] = queue.top(); queue.pop();
            if (dist != data.h[v]) continue;
            for (const auto& [u,travel] : reverse[v]) {
                const double proposal = dist + nodes[u].service + travel;
                if (proposal < data.h[u]) {
                    data.h[u]=proposal; queue.push({proposal,u});
                    // Successor points to the popped Dijkstra node. Strict
                    // improvement preserves an acyclic shortest-path tree.
                    if (cfg.future_source_reservation_horizon_seconds>0) data.shortest_successor[u]=v;
                }
            }
        }
        std::vector<int> order(nodes.size());
        std::iota(order.begin(),order.end(),0);
        std::sort(order.begin(),order.end(),[&](int a,int b) {
            return std::tie(data.h[a],nodes[a].id) < std::tie(data.h[b],nodes[b].id);
        });
        for (int u : order) {
            if (u == goal || !std::isfinite(data.h[u])) continue;
            int next=-1; double best=inf;
            for (const auto& edge : nodes[u].out) {
                const double value=nodes[u].service+edge.travel+data.h[edge.to];
                if (value < best || (value==best && next>=0 && nodes[edge.to].id<nodes[next].id)) {
                    best=value; next=edge.to;
                }
            }
            if (next>=0) {
                data.hops[u]=1+data.hops[next];
                data.decision_nodes[u]=data.decision_nodes[next]+(nodes[u].out.size()>1 || nodes[u].indegree>1 ? 1:0);
            }
        }
        return goal_cache.emplace(goal,std::move(data)).first->second;
    }
    int observation_depth(int node, int start, const GoalData& gd) const {
        if (gd.hops[node] == 0) return 1;
        int selected = cfg.max_depth;
        if (cfg.adaptive) {
            // Topology-only H ratio makes upstream observation deeper. A merge
            // within two outgoing hops raises the local minimum to two. None of
            // these empirical ordering choices is the safety certificate.
            const double ratio=gd.h[start]>0?std::max(0.0,std::min(1.0,gd.h[node]/gd.h[start])):0.0;
            selected=cfg.min_depth+static_cast<int>(std::floor(ratio*(cfg.max_depth-cfg.min_depth)+0.5));
            bool nearby_merge=nodes[node].indegree>1;
            for (const auto& e:nodes[node].out) {
                nearby_merge=nearby_merge||nodes[e.to].indegree>1;
                for (const auto& f:nodes[e.to].out) nearby_merge=nearby_merge||nodes[f.to].indegree>1;
            }
            if (nearby_merge) selected=std::max(selected,std::min(2,cfg.max_depth));
            if (gd.hops[node]<=1 && nodes[node].out.size()<=1 && !nearby_merge) selected=cfg.min_depth;
        }
        return std::max(1,std::min(selected,gd.hops[node]+1));
    }
    double pressure_seconds(int node,double arrival,int ignore_owner=-1) const {
        if (cfg.pressure_window==0 || nodes[node].service==0) return 0;
        const double until=add_time(arrival,cfg.pressure_window);
        double occupied=0, union_start=0, union_end=0;
        bool open=false;
        const auto& c=calendars[node];
        // Under the validated fixed2 half-open tuple, S < A-2s implies
        // E < A. These entries were empty after clipping to [A,until),
        // so skipping them preserves the union operations and their order.
        // Keep the boundary and every original test; other modes full-scan.
        auto it=fixed_two_second_calendars
            ? c.lower_bound(seconds(std::max<std::int64_t>(0,tick(arrival)-2000000LL)))
            : c.begin();
        for (;it!=c.end() && it->first<until;++it) {
            if (it->second.task==ignore_owner) continue;
            const double start=std::max(arrival,it->first), end=std::min(until,it->second.end);
            if (end<=start) continue;
            if (!open) {union_start=start;union_end=end;open=true;}
            else if (start<=union_end) union_end=std::max(union_end,end);
            else {occupied+=union_end-union_start;union_start=start;union_end=end;}
        }
        if (open) occupied+=union_end-union_start;
        return occupied;
    }
    double score_suffix(int node, double arrival, int depth, const GoalData& gd,
                        Attempt& a, std::vector<unsigned char>& seen, ScoreBudget& budget,
                        int query_depth) {
        if (node==tasks[a.task].goal) return 0;
        if (budget.expansions>=static_cast<std::uint64_t>(cfg.max_score_expansions)) {
            a.score_budget_exhausted=true; budget.exhausted=true; return gd.h[node];
        }
        ++budget.expansions;
        // At a one-hop decision with zero pressure weight the exact score is H.
        // Preserve logical budget consumption/exhaustion, but do not perform or
        // report calendar queries whose penalty would be multiplied by zero.
        if (depth==1 && query_depth==1 && cfg.congestion_weight==0.0) {
            ++static_rank_fastpath_candidates;
            return gd.h[node];
        }
        ++budget.actual_queries;
        budget.actual_query_depth=std::max(budget.actual_query_depth,query_depth);
        ++a.score_expansions; ++a.scoring_queries;
        double blocked_end=-inf;
        const bool blocked=conflicts(node,arrival,add_time(arrival,nodes[node].service),&blocked_end,nullptr,a.ignore_owner);
        const double penalty=(blocked ? std::max(0.0,blocked_end-arrival) : 0.0)+pressure_seconds(node,arrival,a.ignore_owner);
        if (depth<=1) return gd.h[node]+cfg.congestion_weight*penalty;
        seen[node]=1;
        double continuation=inf;
        for (const auto& edge:nodes[node].out) {
            if (seen[edge.to] || !std::isfinite(gd.h[edge.to])) continue;
            const double next_arrival=add_time(add_time(arrival,nodes[node].service),edge.travel);
            const double value=nodes[node].service+edge.travel+
                score_suffix(edge.to,next_arrival,depth-1,gd,a,seen,budget,query_depth+1);
            continuation=std::min(continuation,value);
        }
        seen[node]=0;
        // No visible continuation may simply be a truncated/visited branch. DFS
        // independently checks exact acyclic reachability; a score is not proof.
        if (!std::isfinite(continuation)) continuation=gd.h[node];
        return continuation+cfg.congestion_weight*penalty;
    }
    void record_conflict_retry(double arrival, double blocked_end, double cleanup, Attempt& a,
                               bool closed_endpoint) {
        // Scope: this explored prefix only. Minimum over explored conflicts is a
        // search heuristic, not a proof of the globally earliest feasible launch.
        const double offset=arrival-a.admission;
        double retry;
        if (half_open()) {
            auto retry_tick=tick(blocked_end)-(tick(arrival)-tick(a.admission))+(closed_endpoint?1:0);
            retry=seconds(std::max(retry_tick,tick(a.admission)+1));
        } else {
            retry=closed_endpoint?std::nextafter(blocked_end-offset,inf):blocked_end-offset;
            if (!(retry>a.admission)) retry=std::nextafter(a.admission,inf);
            if (closed_endpoint) retry=std::max(retry,a.admission+(std::nextafter(blocked_end,inf)-blocked_end));
            for (int i=0;i<8 && (closed_endpoint?!(retry+offset>blocked_end):retry+offset<blocked_end);++i)
                retry=std::nextafter(retry,inf);
        }
        a.retry_at=std::min(a.retry_at,retry);
        if (cleanup>a.admission) a.retry_at=std::min(a.retry_at,cleanup);
    }
    std::vector<Choice> rank_choices(int node,double departure,const GoalData& gd,Attempt& a,bool force_single_skip=false) {
        std::vector<Choice> choices;
        const int depth=observation_depth(node,tasks[a.task].start,gd);
        ++search_k_histogram[depth];
        a.max_observation_depth=std::max(a.max_observation_depth,depth);
        ScoreBudget score_budget;
        std::size_t legal_count=0;
        if (cfg.skip_scoring_single_choice || force_single_skip)
            for (const auto& edge:nodes[node].out) if (!a.visited[edge.to] && std::isfinite(gd.h[edge.to])) ++legal_count;
        const bool skip_score=(cfg.skip_scoring_single_choice || force_single_skip) && legal_count<=1;
        if (skip_score) ++skipped_single_choice_scoring;
        for (const auto& edge:nodes[node].out) {
            if (a.visited[edge.to] || !std::isfinite(gd.h[edge.to])) continue;
            const double eta=add_time(departure,edge.travel);
            if (!std::isfinite(eta)) continue;
            auto seen=a.visited;
            const double value=edge.travel+(skip_score?gd.h[edge.to]:score_suffix(edge.to,eta,depth,gd,a,seen,score_budget,1));
            choices.push_back({edge,eta,value});
            ++scored_neighbor_candidates;
        }
        a.path.back().requested_k=depth;
        a.path.back().actual_query_depth=score_budget.actual_query_depth;
        a.path.back().local_score_queries=score_budget.actual_queries;
        a.path.back().score_budget_exhausted=score_budget.exhausted;
        ++actual_query_depth_histogram[score_budget.actual_query_depth];
        if (score_budget.exhausted) ++local_score_budget_exhausted_decisions;
        std::stable_sort(choices.begin(),choices.end(),[&](const Choice& l,const Choice& r) {
            return std::tie(l.score,nodes[l.edge.to].id) < std::tie(r.score,nodes[r.edge.to].id);
        });
        return choices;
    }
    bool choice_feasible(const Choice& choice,double departure,Attempt& a) {
            const int next=choice.edge.to;
            if (cfg.edge_entry_headway_seconds>0) {
                ++edge_safety_queries;
                double end=-inf,cleanup=inf;
                const double protected_until=add_time(departure,cfg.edge_entry_headway_seconds);
                if (calendar_conflicts(edge_calendars[choice.edge.id],departure,protected_until,true,&end,&cleanup,a.ignore_owner)) {
                    ++(a.ignore_owner>=0?inroute_edge_conflicts:source_edge_conflicts)[choice.edge.id];
                    record_conflict_retry(departure,end,cleanup,a,false); return false;
                }
            }
            if (next!=tasks[a.task].goal || (cfg.strict_endpoint_resources && nodes[next].service>0)) {
                ++a.safety_queries;
                if (next==tasks[a.task].goal) ++goal_resource_queries;
                double end=-inf, cleanup=inf;
                if (conflicts(next,choice.arrival,add_time(choice.arrival,nodes[next].service),&end,&cleanup,a.ignore_owner)) {
                    ++(a.ignore_owner>=0?inroute_node_conflicts:source_node_conflicts)[next];
                    record_conflict_retry(choice.arrival,end,cleanup,a,!half_open()); return false;
                }
            }
        return true;
    }
    bool dfs(int node, double arrival, const GoalData& gd, Attempt& a) {
        if (a.expansions>=static_cast<std::uint64_t>(cfg.max_expansions)) {
            a.budget_exhausted=true; return false;
        }
        ++a.expansions;
        if (std::isfinite(a.finish_bound)) {
            const bool exceeds=half_open()?tick(arrival)+tick(gd.h[node])>tick(a.finish_bound):arrival+gd.h[node]>a.finish_bound;
            if (exceeds) {++a.route_bound_prunes;return false;}
        }
        const bool terminal=node==tasks[a.task].goal;
        const double departure=add_time(arrival,((terminal&&!cfg.terminal_reservation_service)?0:nodes[node].service));
        if (a.path.empty() && cfg.strict_endpoint_resources && nodes[node].service>0) {
            ++source_resource_queries;
            double end=-inf,cleanup=inf;
            if (conflicts(node,arrival,departure,&end,&cleanup,a.ignore_owner)) {
                ++(a.ignore_owner>=0?inroute_node_conflicts:source_node_conflicts)[node];
                if (cfg.future_source_reservation_horizon_seconds>0 && a.ignore_owner<0 && a.forced_prefix)
                    a.forced_prefix_denial=true;
                record_conflict_retry(arrival,end,cleanup,a,!half_open()); return false;
            }
        }
        a.visited[node]=1;
        a.path.push_back({node,arrival,departure});
        a.max_depth=std::max(a.max_depth,static_cast<int>(a.path.size()));
        if (terminal) return true;
        const auto choices=rank_choices(node,departure,gd,a);
        // Calendar-blocked alternatives do not turn a branch into a forced
        // prefix. The gate closes at the first static reachable choice.
        if (cfg.future_source_reservation_horizon_seconds>0 && a.ignore_owner<0 && choices.size()!=1)
            a.forced_prefix=false;
        for (const auto& choice:choices) {
            const int next=choice.edge.to;
            if (!choice_feasible(choice,departure,a)) {
                if (cfg.future_source_reservation_horizon_seconds>0 && a.ignore_owner<0 && a.forced_prefix)
                    a.forced_prefix_denial=true;
                continue;
            }
            if (dfs(next,choice.arrival,gd,a)) return true;
            if (a.budget_exhausted) break;
        }
        a.path.pop_back(); a.visited[node]=0; ++a.backtracks;
        return false;
    }
    std::uint64_t calendar_hash() const {
        std::uint64_t value=1469598103934665603ULL;
        auto mix=[&](std::uint64_t x) { value^=x; value*=1099511628211ULL; };
        for (std::size_t node=0;node<calendars.size();++node) {
            mix(node);
            for (const auto& r:calendars[node]) {
                std::uint64_t start_bits,end_bits;
                std::memcpy(&start_bits,&r.first,sizeof(double));
                std::memcpy(&end_bits,&r.second.end,sizeof(double));
                mix(start_bits); mix(end_bits); mix(r.second.task);
            }
        }
        if (cfg.edge_entry_headway_seconds>0) for (std::size_t edge=0;edge<edge_calendars.size();++edge) {
            mix(edge+calendars.size());
            for (const auto& r:edge_calendars[edge]) {
                std::uint64_t start_bits,end_bits;
                std::memcpy(&start_bits,&r.first,sizeof(double));std::memcpy(&end_bits,&r.second.end,sizeof(double));
                mix(start_bits);mix(end_bits);mix(r.second.task);
            }
        }
        return value;
    }
    void schedule_attempt(int task, double time) {
        Task& t=tasks[task];
        if (t.admitted || t.future_reserved || !t.released) return;
        if (cfg.source_fifo) {
            auto previous=last_source_admission.find(t.start);
            if (previous!=last_source_admission.end())
                time=quantize(std::max(time,add_time(previous->second,cfg.source_generation_interval)),cfg.release_quantum);
        }
        if (half_open()) time=seconds(tick(time));
        ++t.generation;
        push_event(time,2,task,t.generation);
    }
    bool is_source_head(int task) const {
        if (!cfg.source_fifo) return true;
        const auto& t=tasks[task];
        auto q=source_queues.find(t.start);
        auto h=source_heads.find(t.start);
        return q!=source_queues.end() && h!=source_heads.end() && h->second<q->second.size() && q->second[h->second]==task;
    }
    bool source_successor_ready_now(int task,double time,bool& activation_pending) const {
        activation_pending=false;
        const Task& t=tasks[task];
        const auto q=source_queues.find(t.start);
        const auto h=source_heads.find(t.start);
        if (q==source_queues.end() || h==source_heads.end() || h->second>=q->second.size() || q->second[h->second]!=task)
            throw std::logic_error("ready-successor query requires current canonical source head");
        if (h->second+1>=q->second.size()) return false;
        const Task& next=tasks[q->second[h->second+1]];
        if (!next.released) return false;
        if (next.predecessor>=0) {
            const Task& prior=tasks[next.predecessor];
            if (!prior.physically_completed) return false;
            if (tick(quantize(std::max(next.release,prior.finish),cfg.release_quantum))>tick(time)) return false;
        }
        // Actual arrival precedes attempts, but its EBS activation event can
        // follow them at the same time. Do not use activated=false as unready.
        activation_pending=!next.activated;
        return true;
    }
    void advance_source(int node,double time) {
        if (!cfg.source_fifo) return;
        auto& q=source_queues[node]; auto& head=source_heads[node];
        while (head<q.size() && tasks[q[head]].admitted) ++head;
        if (head<q.size() && tasks[q[head]].activated) schedule_attempt(q[head],time);
    }
    void activate(int task,double time) {
        Task& t=tasks[task];
        if (t.activated || t.admitted) return;
        t.activation_time=time;
        t.activated=true; t.reason="source_fifo_wait";
        if (cfg.source_fifo) {
            if (cfg.source_fifo_order=="activation") {
                source_queues[t.start].push_back(task);
                source_heads.try_emplace(t.start,0);
            }
            if (is_source_head(task)) schedule_attempt(task,time);
        } else schedule_attempt(task,time);
    }
    void refresh_finish(Task& t) {
        t.finish=t.route.back().arrival;
        t.completion_epoch=quantize(t.finish,cfg.completion_quantum);
        if (half_open()) t.completion_epoch=seconds(tick(t.completion_epoch));
        t.cleanup=t.completion_epoch;
        if (cfg.strict_endpoint_resources) {
            double goal_end=t.route.back().departure;
            if (!half_open()) goal_end=std::nextafter(goal_end,inf);
            t.cleanup=std::max(t.cleanup,goal_end);
        }
        if (cfg.edge_entry_headway_seconds>0)
            for (std::size_t i=0;i+1<t.route.size();++i)
                t.cleanup=std::max(t.cleanup,add_time(t.route[i].departure,cfg.edge_entry_headway_seconds));
        t.cleanup=quantize(t.cleanup,cfg.completion_quantum);
        if (half_open()) t.cleanup=seconds(tick(t.cleanup));
        t.reason=t.finish<=cfg.end_time?"completed":"in_network_at_horizon";
    }
    void record_commit(int task,double time,const std::string& kind,std::uint64_t old_gen,
                       const std::vector<std::uint64_t>& removed={}) {
        if (!cfg.enable_inroute_replanning) return;
        const Task& t=tasks[task];
        RollingRecord r;r.kind=kind;r.order=next_ledger_order++;r.time=time;r.task=task;
        r.old_generation=old_gen;r.new_generation=t.route_generation;r.index=t.arrived_index;
        r.node=t.route[t.arrived_index].node;r.finish=t.finish;r.cleanup=t.cleanup;
        r.route=t.route;r.node_ids=t.node_reservation_ids;r.edge_ids=t.edge_reservation_ids;r.removed=removed;
        rolling_records.push_back(std::move(r));
    }
    void finish_physically(int task,double time) {
        Task& t=tasks[task];
        if (tick(time)!=tick(t.finish)) throw std::logic_error("physical goal time differs from certificate");
        t.physically_completed=true;
        if (t.dependent>=0 && tasks[t.dependent].released && !tasks[t.dependent].activated)
            push_event(std::max(time,quantize(std::max(tasks[t.dependent].release,time),cfg.release_quantum)),3,t.dependent,t.route_generation);
    }
    void schedule_next_arrival(int task) {
        const auto& t=tasks[task];
        const int next=t.arrived_index+1;
        if (next<static_cast<int>(t.route.size())) push_event(t.route[next].arrival,4,task,t.route_generation,next);
    }
    double source_route_allowance(const Task& t,double time,const GoalData& gd) const {
        if (cfg.route_excess_retry_relaxation_rate==0.0 || !std::isfinite(gd.h[t.start]))
            return cfg.max_route_excess_seconds;
        // Waiting age is measured only from the immutable first actual attempt.
        // Positive relaxation is supported on the integer-us physical tuple.
        const auto elapsed=std::max<std::int64_t>(0,tick(time)-tick(t.first_planning_attempt_time));
        const long double growth=std::floor(static_cast<long double>(cfg.route_excess_retry_relaxation_rate)*elapsed);
        const long double total=static_cast<long double>(tick(cfg.max_route_excess_seconds))+growth;
        const long double finish=static_cast<long double>(tick(time))+tick(gd.h[t.start])+total;
        if (!std::isfinite(total) || finish>static_cast<long double>(std::numeric_limits<std::int64_t>::max())-1)
            throw std::invalid_argument("effective source route budget exceeds integer microsecond range");
        return seconds(static_cast<std::int64_t>(total));
    }

    // One complete static shortest chain; temporal alternatives are a 61-bit
    // integer-launch mask, not repeated DFS and not spatial lookahead depth.
    bool reserve_future_source(int task,double time,const GoalData& gd,double strict_finish_before=inf) {
        Task& t=tasks[task];
        const auto origin=tick(time),q=std::int64_t(1000000);
        if (origin%q) throw std::logic_error("future source attempt must be on the integer-second grid");
        ++future_searches;++t.future_searches;
        std::vector<Step> path;
        std::vector<unsigned char> seen(nodes.size(),0);
        int current=t.start;double arrival=0;
        for (;;) {
            if (current<0 || seen[current] || path.size()>=nodes.size()) {++future_chain_rejections;return false;}
            seen[current]=1;
            const double departure=add_time(arrival,nodes[current].service);
            path.push_back({current,arrival,departure});++future_chain_nodes;
            if (current==t.goal) break;
            const int next=gd.shortest_successor[current];
            const auto edge=std::find_if(nodes[current].out.begin(),nodes[current].out.end(),[&](const Edge& e){return e.to==next;});
            if (edge==nodes[current].out.end()) {++future_chain_rejections;return false;}
            arrival=add_time(departure,edge->travel);current=next;
        }
        // Freeze extra-distance allowance at the actual attempt, but move the
        // absolute finish bound with the proposed launch, not with attempt time.
        if (std::isfinite(t.last_effective_route_excess) &&
            tick(path.back().arrival)>tick(gd.h[t.start])+tick(t.last_effective_route_excess)) {
            ++future_chain_rejections;return false;
        }
        int horizon=cfg.future_source_reservation_horizon_seconds;
        const bool comparing=std::isfinite(strict_finish_before);
        if (comparing) {
            // Only launches satisfying R + exact-chain-duration < immediate
            // certificate finish can improve this candidate. Integer-us -1
            // preserves strictness, including equality and a one-us boundary.
            const auto headroom=tick(strict_finish_before)-origin-tick(path.back().arrival)-1;
            if (headroom<q) {++future_success_finish_bound_rejections;return false;}
            horizon=static_cast<int>(std::min<std::int64_t>(horizon,headroom/q));
        }
        std::uint64_t mask=((std::uint64_t(1)<<(horizon+1))-1)&~std::uint64_t(1);
        const auto lower=origin+q,upper=origin+horizon*q;
        auto intersect_resource=[&](const Calendar& calendar,std::int64_t lo,std::int64_t hi) {
            if (lo==hi) return;
            ++future_calendar_queries;
            // For all candidate launches R>=lower, an old window ending
            // before lower+lo cannot clear any mask bit. Integer ticks
            // avoid subtracting rounded doubles or skipping equal keys.
            auto it=fixed_two_second_calendars
                ? calendar.lower_bound(seconds(std::max<std::int64_t>(0,lower+lo-2000000LL)))
                : calendar.begin();
            for (;it!=calendar.end();++it) {
                const auto& entry=*it;
                if (tick(entry.first)>=upper+hi) break;
                ++future_calendar_entries_scanned;++t.future_calendar_entries_scanned;
                // Half-open overlap excludes both touching endpoints. Clip
                // before division so every quotient below is nonnegative.
                const auto a=std::max(lower,tick(entry.first)-hi+1);
                const auto b=std::min(upper,tick(entry.second.end)-lo-1);
                if (a>b) continue;
                const int first=static_cast<int>((a-origin+q-1)/q);
                const int last=static_cast<int>((b-origin)/q);
                if (first>last) continue;
                const auto bits=((std::uint64_t(1)<<(last-first+1))-1)<<first;
                mask&=~bits;
            }
        };
        for (std::size_t i=0;i<path.size();++i) {
            const auto& step=path[i];
            intersect_resource(calendars[step.node],tick(step.arrival),tick(step.departure));
            if (i+1<path.size())
                intersect_resource(edge_calendars[edge_ids.at({step.node,path[i+1].node})],tick(step.departure),tick(step.departure)+tick(cfg.edge_entry_headway_seconds));
        }
        if (!mask) {++future_mask_empty;if (comparing) ++future_success_mask_empty;return false;}
        int offset=1;while (!(mask&(std::uint64_t(1)<<offset))) ++offset;
        const double launch=seconds(origin+offset*q);
        for (auto& step:path) {step.arrival=add_time(launch,step.arrival);step.departure=add_time(launch,step.departure);}
        // Reject before changing route state, reservation IDs, calendar or events.
        if (comparing && tick(path.back().arrival)>=tick(strict_finish_before)) {
            ++future_success_finish_bound_rejections;return false;
        }
        // Defensive exact validation uses the same calendars without any event
        // interleaving. It is counted separately and never searches another path.
        for (std::size_t i=0;i<path.size();++i) {
            const auto& step=path[i];
            if (tick(step.arrival)!=tick(step.departure)) {
                ++future_validation_queries;
                if (conflicts(step.node,step.arrival,step.departure)) throw std::logic_error("future launch mask missed a node conflict");
            }
            if (i+1<path.size()) {
                ++future_validation_queries;
                if (calendar_conflicts(edge_calendars[edge_ids.at({step.node,path[i+1].node})],step.departure,add_time(step.departure,cfg.edge_entry_headway_seconds),true))
                    throw std::logic_error("future launch mask missed an edge-entry conflict");
            }
        }
        // Entire certificate exists before the first calendar mutation. Its
        // rights participate in all later checks even before physical admission.
        t.future_reserved=true;t.reservation_time=time;t.planned_admission=launch;
        t.route=std::move(path);t.route_generation=1;t.arrived_index=-1;
        t.max_certificate_depth=std::max(t.max_certificate_depth,static_cast<int>(t.route.size()));
        refresh_finish(t);
        t.planned_finish=t.finish;t.planned_cleanup=t.cleanup;
        t.admission_effective_route_excess=t.last_effective_route_excess;
        t.admission_static_remaining=gd.h[t.start];
        t.admission_route_excess=seconds(tick(t.finish)-tick(launch)-tick(gd.h[t.start]));
        t.node_reservation_ids.assign(t.route.size(),0);t.edge_reservation_ids.assign(t.route.size()-1,0);
        for (std::size_t i=0;i<t.route.size();++i) {
            const auto& step=t.route[i];
            if (tick(step.arrival)==tick(step.departure)) continue;
            const auto id=next_reservation_id++;
            auto it=calendars[step.node].emplace(step.arrival,Reservation{step.departure,task,id});
            t.node_reservation_ids[i]=id;t.reservations.push_back({step.node,it});++calendar_entries;
        }
        for (std::size_t i=0;i+1<t.route.size();++i) {
            const int edge=edge_ids.at({t.route[i].node,t.route[i+1].node});
            const auto id=next_reservation_id++;
            auto it=edge_calendars[edge].emplace(t.route[i].departure,Reservation{add_time(t.route[i].departure,cfg.edge_entry_headway_seconds),task,id});
            t.edge_reservation_ids[i]=id;t.edge_reservations.push_back({edge,it});++edge_calendar_entries;
        }
        peak_calendar_entries=std::max(peak_calendar_entries,calendar_entries);
        peak_edge_calendar_entries=std::max(peak_edge_calendar_entries,edge_calendar_entries);
        t.reserved_route=t.route;t.reserved_node_ids=t.node_reservation_ids;t.reserved_edge_ids=t.edge_reservation_ids;
        RollingRecord r;r.kind="source_reserve";r.order=next_ledger_order++;r.time=time;r.task=task;
        r.new_generation=1;r.index=-1;r.node=-1;r.finish=t.finish;r.cleanup=t.cleanup;r.planned_admission=launch;
        r.route=t.route;r.node_ids=t.node_reservation_ids;r.edge_ids=t.edge_reservation_ids;
        t.reservation_order=r.order;rolling_records.push_back(std::move(r));
        ++future_precommits;++t.generation;
        // Never trim the temporal mask or this launch event at end_time: the
        // short run must retain the same pre-horizon rights as a drain run.
        push_event(launch,5,task,t.generation);
        t.reason="source_future_reserved";
        return true;
    }
    void launch_future_source(const Event& e) {
        Task& t=tasks[e.task];
        if (e.generation!=t.generation || t.admitted) return;
        if (!t.future_reserved || !t.released || !t.activated || !is_source_head(e.task) ||
            tick(e.time)!=tick(t.planned_admission) || t.route_generation!=1 || t.arrived_index!=-1 ||
            (t.predecessor>=0 && (!tasks[t.predecessor].physically_completed || tick(tasks[t.predecessor].finish)>tick(e.time))))
            throw std::logic_error("invalid future source launch state");
        t.admitted=true;t.admission=e.time;t.arrived_index=0;t.commit_order=++next_commit;
        last_source_admission[t.start]=e.time;
        t.reason=t.finish<=cfg.end_time?"completed":"in_network_at_horizon";
        if (t.admission_effective_route_excess>cfg.max_route_excess_seconds) ++relaxed_source_admissions;
        RollingRecord r;r.kind="source_launch";r.order=next_ledger_order++;r.time=e.time;r.task=e.task;
        r.new_generation=t.route_generation;r.index=0;r.node=t.start;r.reference_reservation_order=t.reservation_order;
        rolling_records.push_back(std::move(r));++future_launches;
        if (t.route.size()==1) finish_physically(e.task,e.time);else schedule_next_arrival(e.task);
        push_event(t.cleanup,0,e.task,t.route_generation);
        advance_source(t.start,e.time);
    }

    void attempt(int task,double time) {
        Task& t=tasks[task];
        if (t.admitted || t.future_reserved || !is_source_head(task)) return;
        if (t.first_planning_attempt_time<0) t.first_planning_attempt_time=time;
        const auto started=std::chrono::steady_clock::now();
        const auto& gd=goal_data(t.goal);
        Attempt a; a.task=task; a.admission=time; a.visited.assign(nodes.size(),0);
        t.last_effective_route_excess=source_route_allowance(t,time,gd);
        if (t.last_effective_route_excess>cfg.max_route_excess_seconds) ++relaxed_source_attempts;
        if (std::isfinite(cfg.max_route_excess_seconds) && std::isfinite(gd.h[t.start]))
            a.finish_bound=add_time(add_time(time,gd.h[t.start]),t.last_effective_route_excess);
        ++t.attempts; ++planning_attempts;
        const auto before=cfg.audit_failed_calendar_hash?calendar_hash():0;
        bool success=false;
        if (std::isfinite(gd.h[t.start])) success=dfs(t.start,time,gd,a);
        t.expansions+=a.expansions; t.scoring_queries+=a.scoring_queries;
        t.safety_queries+=a.safety_queries; t.score_expansions+=a.score_expansions;
        t.backtracks+=a.backtracks;
        route_bound_prunes+=a.route_bound_prunes;
        t.max_certificate_depth=std::max(t.max_certificate_depth,a.max_depth);
        t.max_observation_depth=std::max(t.max_observation_depth,a.max_observation_depth);
        if (a.score_budget_exhausted) ++score_budget_exhaustions;
        bool preferred_future=false,skip_for_ready_successor=false;
        if (success && cfg.future_source_prefer_only_without_ready_successor) {
            ++ready_successor_checks;++t.ready_successor_checks;
            bool activation_pending=false;
            skip_for_ready_successor=source_successor_ready_now(task,time,activation_pending);
            if (skip_for_ready_successor) {
                ++ready_successor_skips;++t.ready_successor_skips;
                if (activation_pending) {++ready_successor_activation_pending_skips;++t.ready_successor_activation_pending_skips;}
            }
        }
        if (success && cfg.future_source_prefer_earlier_finish && !skip_for_ready_successor) {
            // The successful immediate DFS remains an uncommitted fallback.
            // This comparison has no forced-prefix or failure-age requirement;
            // the old failed-DFS rescue gate below remains unchanged.
            ++future_success_comparisons;++t.future_success_comparisons;
            t.compared_immediate_finish=a.path.back().arrival;
            preferred_future=reserve_future_source(task,time,gd,t.compared_immediate_finish);
            if (preferred_future) {++future_success_preferred;t.future_success_preferred=true;}
            else {
                ++future_success_kept_immediate;
                if (cfg.audit_failed_calendar_hash && calendar_hash()!=before)
                    throw std::logic_error("rejected future comparison mutated a calendar");
            }
        }
        if (success && !preferred_future) {
            t.admitted=true; t.admission=time; t.route=std::move(a.path);
            last_source_admission[t.start]=time;
            t.commit_order=++next_commit;
            t.route_generation=cfg.enable_inroute_replanning?1:0;
            t.node_reservation_ids.assign(t.route.size(),0);
            t.edge_reservation_ids.assign(t.route.size()-1,0);
            refresh_finish(t);
            t.admission_effective_route_excess=t.last_effective_route_excess;
            t.admission_static_remaining=gd.h[t.start];
            t.admission_route_excess=half_open()?seconds(tick(t.finish)-tick(time)-tick(gd.h[t.start])):
                t.finish-time-gd.h[t.start];
            if (std::isfinite(a.finish_bound) && (half_open()?tick(t.finish)>tick(a.finish_bound):t.finish>a.finish_bound))
                throw std::logic_error("source certificate exceeds its active route budget");
            if (t.admission_effective_route_excess>cfg.max_route_excess_seconds) ++relaxed_source_admissions;
            const auto& source=t.route.front();
            if (!cfg.strict_endpoint_resources && conflicts(source.node,source.arrival,source.departure)) ++source_ignored_conflicts;
            const auto& goal=t.route.back();
            if (!cfg.strict_endpoint_resources && conflicts(goal.node,goal.arrival,goal.departure)) ++goal_ignored_conflicts;
            for (std::size_t i=0;i<t.route.size();++i) {
                const auto& step=t.route[i];
                if (half_open() && tick(step.arrival)==tick(step.departure)) continue;
                const auto id=next_reservation_id++;
                auto it=calendars[step.node].emplace(step.arrival,Reservation{step.departure,task,id});
                t.node_reservation_ids[i]=id;
                t.reservations.push_back({step.node,it}); ++calendar_entries;
            }
            if (cfg.edge_entry_headway_seconds>0) {
                for (std::size_t i=0;i+1<t.route.size();++i) {
                    const auto& from=t.route[i];const auto& to=t.route[i+1];
                    const int edge=edge_ids.at({from.node,to.node});
                    auto it=edge_calendars[edge].emplace(from.departure,
                        Reservation{add_time(from.departure,cfg.edge_entry_headway_seconds),task,next_reservation_id++});
                    t.edge_reservation_ids[i]=it->second.id;
                    t.edge_reservations.push_back({edge,it});++edge_calendar_entries;
                }
                peak_edge_calendar_entries=std::max(peak_edge_calendar_entries,edge_calendar_entries);
            }
            for (std::size_t i=0;i+1<t.route.size();++i)
                ++committed_k_histogram[observation_depth(t.route[i].node,t.start,gd)];
            peak_calendar_entries=std::max(peak_calendar_entries,calendar_entries);
            record_commit(task,time,"source_commit",0);
            push_event(t.cleanup,0,task,t.route_generation);
            if (cfg.enable_inroute_replanning) {
                if (t.route.size()==1) finish_physically(task,time);
                else schedule_next_arrival(task);
            }
            if (!cfg.enable_inroute_replanning && t.dependent>=0 && tasks[t.dependent].released && !tasks[t.dependent].activated)
                push_event(std::max(time,quantize(std::max(tasks[t.dependent].release,t.finish),cfg.release_quantum)),3,t.dependent);
            advance_source(t.start,time);
        } else if (!success) {
            ++failed_attempts;
            if (cfg.audit_failed_calendar_hash) {
                ++failed_hash_checks;
                if (calendar_hash()!=before) throw std::logic_error("failed DFS mutated a calendar");
            }
            if (a.budget_exhausted) ++search_budget_failures;
            bool reserved=false;
            if (cfg.future_source_reservation_horizon_seconds>0 && a.forced_prefix_denial &&
                !a.budget_exhausted && a.route_bound_prunes==0 && t.attempts<=cfg.max_retries &&
                tick(time)-tick(t.first_planning_attempt_time)>=tick(cfg.future_source_reservation_min_wait_seconds)) {
                ++future_eligible_failures;reserved=reserve_future_source(task,time,gd);
            }
            if (reserved) { /* An actual launch event now owns the source head. */ }
            else if (!std::isfinite(gd.h[t.start])) t.reason="statically_unreachable";
            else if (t.attempts>cfg.max_retries) t.reason="retry_budget_exhausted";
            else {
                double retry=add_time(time,(cfg.retry_mode=="1s"?1.0:cfg.retry_step));
                if (cfg.retry_mode=="futurecalendar_jump" && std::isfinite(a.retry_at)) {
                    retry=a.retry_at; ++retry_jumps;
                }
                retry=quantize(retry,cfg.release_quantum);
                if (half_open()) retry=seconds(tick(retry));
                if (!(retry>time)) retry=quantize(std::nextafter(time,inf),cfg.release_quantum);
                if (!(retry>time)) throw std::logic_error("retry event failed to advance time");
                t.reason=a.budget_exhausted?"search_budget_retry":"calendar_retry";
                if (retry<=cfg.end_time) schedule_attempt(task,retry);
                else t.reason=a.budget_exhausted?"search_budget_at_horizon":"outside_at_horizon";
            }
        }
        decision_microseconds.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-started).count());
    }
    void exchange_suffix(int task,double time,Attempt& a) {
        Task& t=tasks[task];const std::size_t current=static_cast<std::size_t>(t.arrived_index);
        if (a.path.size()<=current || tick(a.path.back().arrival)>tick(t.finish))
            throw std::logic_error("replacement extends finish or loses current node");
        std::set<int> visited;
        for (std::size_t i=0;i<a.path.size();++i) {
            if (!visited.insert(a.path[i].node).second) throw std::logic_error("replacement contains a cycle");
            if (i<=current && (a.path[i].node!=t.route[i].node || a.path[i].arrival!=t.route[i].arrival || a.path[i].departure!=t.route[i].departure))
                throw std::logic_error("replacement changes executed prefix or current service");
            if (i>current && conflicts(a.path[i].node,a.path[i].arrival,a.path[i].departure,nullptr,nullptr,task))
                throw std::logic_error("replacement node validation failed");
            if (i>=current && i+1<a.path.size()) {
                const auto& step=a.path[i];const int edge=edge_ids.at({step.node,a.path[i+1].node});
                if (calendar_conflicts(edge_calendars[edge],step.departure,add_time(step.departure,cfg.edge_entry_headway_seconds),true,nullptr,nullptr,task))
                    throw std::logic_error("replacement edge validation failed");
            }
        }
        std::vector<std::uint64_t> removed,new_node_ids(a.path.size(),0),new_edge_ids(a.path.size()-1,0);
        for (std::size_t i=0;i<t.node_reservation_ids.size();++i) {
            if (i<=current) new_node_ids[i]=t.node_reservation_ids[i];
            else if (t.node_reservation_ids[i]) removed.push_back(t.node_reservation_ids[i]);
        }
        for (std::size_t i=0;i<t.edge_reservation_ids.size();++i) {
            if (i<current) new_edge_ids[i]=t.edge_reservation_ids[i];
            else removed.push_back(t.edge_reservation_ids[i]);
        }
        const std::set<std::uint64_t> removed_set(removed.begin(),removed.end());
        std::vector<std::pair<int,Calendar::iterator>> retained_nodes,retained_edges,added_nodes,added_edges;
        retained_nodes.reserve(a.path.size());retained_edges.reserve(a.path.size());
        added_nodes.reserve(a.path.size());added_edges.reserve(a.path.size());
        for (const auto& entry:t.reservations) if (!removed_set.count(entry.second->second.id)) retained_nodes.push_back(entry);
        for (const auto& entry:t.edge_reservations) if (!removed_set.count(entry.second->second.id)) retained_edges.push_back(entry);
        // Prepare all new rights while the entire fallback is still present. No
        // simulator event interleaves; on allocation failure only new rights roll back.
        try {
            for (std::size_t i=current+1;i<a.path.size();++i) {
                const auto& step=a.path[i];
                if (tick(step.arrival)==tick(step.departure)) continue;
                const auto id=next_reservation_id++;
                auto it=calendars[step.node].emplace(step.arrival,Reservation{step.departure,task,id});
                added_nodes.push_back({step.node,it});new_node_ids[i]=id;++calendar_entries;
            }
            for (std::size_t i=current;i+1<a.path.size();++i) {
                const auto& step=a.path[i];const int edge=edge_ids.at({step.node,a.path[i+1].node});
                const auto id=next_reservation_id++;
                auto it=edge_calendars[edge].emplace(step.departure,Reservation{add_time(step.departure,cfg.edge_entry_headway_seconds),task,id});
                added_edges.push_back({edge,it});new_edge_ids[i]=id;++edge_calendar_entries;
            }
        } catch (...) {
            for (const auto& e:added_nodes) {calendars[e.first].erase(e.second);--calendar_entries;}
            for (const auto& e:added_edges) {edge_calendars[e.first].erase(e.second);--edge_calendar_entries;}
            throw;
        }
        peak_calendar_entries=std::max(peak_calendar_entries,calendar_entries);
        peak_edge_calendar_entries=std::max(peak_edge_calendar_entries,edge_calendar_entries);
        for (const auto& entry:t.reservations) if (removed_set.count(entry.second->second.id)) {calendars[entry.first].erase(entry.second);--calendar_entries;}
        for (const auto& entry:t.edge_reservations) if (removed_set.count(entry.second->second.id)) {edge_calendars[entry.first].erase(entry.second);--edge_calendar_entries;}
        retained_nodes.insert(retained_nodes.end(),added_nodes.begin(),added_nodes.end());
        retained_edges.insert(retained_edges.end(),added_edges.begin(),added_edges.end());
        t.reservations.swap(retained_nodes);t.edge_reservations.swap(retained_edges);
        t.node_reservation_ids.swap(new_node_ids);t.edge_reservation_ids.swap(new_edge_ids);
        t.route=std::move(a.path);const auto old_generation=t.route_generation++;
        ++next_commit;refresh_finish(t);
        record_commit(task,time,"replace_commit",old_generation,removed);
        push_event(t.cleanup,0,task,t.route_generation);
    }
    void process_arrival(const Event& event) {
        Task& t=tasks[event.task];
        if (event.generation!=t.route_generation) {++stale_arrivals;return;}
        if (event.route_index!=t.arrived_index+1 || event.route_index>=static_cast<int>(t.route.size()) ||
            tick(event.time)!=tick(t.route[event.route_index].arrival)) throw std::logic_error("invalid physical arrival event");
        t.arrived_index=event.route_index;
        RollingRecord arrival;arrival.kind="arrival";arrival.order=next_ledger_order++;arrival.time=event.time;
        arrival.task=event.task;arrival.index=t.arrived_index;arrival.node=t.route[t.arrived_index].node;
        arrival.new_generation=t.route_generation;rolling_records.push_back(std::move(arrival));
        if (t.arrived_index+1==static_cast<int>(t.route.size())) {finish_physically(event.task,event.time);return;}
        const auto started=std::chrono::steady_clock::now();++inroute_decisions;
        const auto& gd=goal_data(t.goal);
        Attempt a;a.task=event.task;a.admission=t.admission;a.ignore_owner=event.task;a.finish_bound=t.finish;
        a.visited.assign(nodes.size(),0);
        for (int i=0;i<=t.arrived_index;++i) {a.visited[t.route[i].node]=1;a.path.push_back(t.route[i]);}
        const int current=t.route[t.arrived_index].node,old_next=t.route[t.arrived_index+1].node;
        const double departure=t.route[t.arrived_index].departure;
        const auto choices=rank_choices(current,departure,gd,a,true);
        const auto old=std::find_if(choices.begin(),choices.end(),[&](const Choice& c){return c.edge.to==old_next;});
        if (old==choices.end()) throw std::logic_error("fallback next hop missing from legal choices");
        if (choices.front().edge.to==old_next || !(choices.front().score<old->score)) ++inroute_keep;
        else {
            ++inroute_attempts;
            const auto before=cfg.audit_failed_calendar_hash?calendar_hash():0;
            const auto best=choices.front();
            if (choice_feasible(best,departure,a) && dfs(best.edge.to,best.arrival,gd,a)) {
                exchange_suffix(event.task,event.time,a);++inroute_success;
            } else {
                ++inroute_fallback;
                if (cfg.audit_failed_calendar_hash) {
                    ++failed_hash_checks;
                    if (calendar_hash()!=before) throw std::logic_error("failed in-route search mutated fallback rights");
                }
            }
        }
        inroute_expansions+=a.expansions;inroute_scoring_queries+=a.scoring_queries;inroute_safety_queries+=a.safety_queries;
        t.expansions+=a.expansions;t.scoring_queries+=a.scoring_queries;t.safety_queries+=a.safety_queries;
        t.score_expansions+=a.score_expansions;t.backtracks+=a.backtracks;route_bound_prunes+=a.route_bound_prunes;
        t.max_certificate_depth=std::max(t.max_certificate_depth,a.max_depth);
        t.max_observation_depth=std::max(t.max_observation_depth,a.max_observation_depth);
        schedule_next_arrival(event.task);
        inroute_microseconds.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-started).count());
    }
public:
    Planner(const py::sequence& node_input,const py::sequence& edge_input,
            const py::sequence& task_input,const Config& c):cfg(c) {
        for (auto value:node_input) {
            auto row=py::cast<py::sequence>(value);
            if (py::len(row)!=2) throw std::invalid_argument("nodes must contain (id, service)");
            int id=py::cast<int>(row[0]);
            double service=finite_nonnegative(py::cast<double>(row[1]),"node service");
            require_grid_value(service,"node service");
            if (index.count(id)) throw std::invalid_argument("duplicate node id");
            index[id]=static_cast<int>(nodes.size()); nodes.push_back({id,service,{},0});
        }
        if (nodes.empty()) throw std::invalid_argument("nodes must not be empty");
        reverse.resize(nodes.size()); calendars.resize(nodes.size());
        std::set<std::pair<int,int>> unique_edges;
        for (auto value:edge_input) {
            auto row=py::cast<py::sequence>(value);
            if (py::len(row)!=3) throw std::invalid_argument("edges must contain (u,v,travel)");
            int u=node_index(py::cast<int>(row[0])),v=node_index(py::cast<int>(row[1]));
            double travel=py::cast<double>(row[2]);
            if (!std::isfinite(travel) || travel<=0) throw std::invalid_argument("edge travel must be finite and positive");
            require_grid_value(travel,"edge travel");
            if (half_open() && tick(travel)<=0) throw std::invalid_argument("edge travel must be at least one microsecond");
            if (!unique_edges.insert({u,v}).second) throw std::invalid_argument("duplicate directed edge");
            const int id=static_cast<int>(edge_calendars.size());
            edge_calendars.emplace_back();edge_ids[{u,v}]=id;edge_nodes.push_back({u,v});
            nodes[u].out.push_back({v,travel,id}); ++nodes[v].indegree; reverse[v].push_back({u,travel});
        }
        for (auto& node:nodes) std::sort(node.out.begin(),node.out.end(),[&](const Edge& a,const Edge& b){return nodes[a.to].id<nodes[b.to].id;});
        std::set<std::string> ids;
        for (auto value:task_input) {
            auto row=py::cast<py::dict>(value);
            Task t;
            t.segment_id=py::cast<std::string>(row["segment_id"]);
            t.task_id=py::cast<std::int64_t>(row["task_id"]);
            t.release=finite_nonnegative(py::cast<double>(row["release"]),"task release");
            if (half_open() && t.release>1e9) throw std::invalid_argument("task release exceeds microsecond-grid range");
            t.deadline=finite_nonnegative(py::cast<double>(row["deadline"]),"task deadline");
            t.start=node_index(py::cast<int>(row["start"])); t.goal=node_index(py::cast<int>(row["goal"]));
            t.leg=row.contains("leg")?py::cast<std::string>(row["leg"]):"direct";
            if (!ids.insert(t.segment_id).second) throw std::invalid_argument("duplicate segment_id");
            tasks.push_back(std::move(t));
        }
        if (half_open()) {
            require_grid_value(cfg.end_time,"end_time");
            require_grid_value(cfg.pressure_window,"pressure_window");
            require_grid_value(cfg.future_source_reservation_min_wait_seconds,"future_source_reservation_min_wait_seconds");
            if (cfg.future_source_reservation_horizon_seconds>0)
                for (const auto& node:nodes) if (node.service!=0.0 && node.service!=2.0)
                    throw std::invalid_argument("future source reservation supports only original zero or normalized 2-second node service");
            require_grid_value(cfg.retry_step,"retry_step");
            require_grid_value(cfg.source_generation_interval,"source_generation_interval");
            require_grid_value(cfg.release_quantum,"release_quantum");
            require_grid_value(cfg.completion_quantum,"completion_quantum");
            require_grid_value(cfg.edge_entry_headway_seconds,"edge_entry_headway_seconds");
            if (std::isfinite(cfg.max_route_excess_seconds)) require_grid_value(cfg.max_route_excess_seconds,"max_route_excess_seconds");
        }
        // All insertion paths use each node service or the edge-entry
        // headway; zero node windows are omitted in half-open mode.
        fixed_two_second_calendars=half_open() && cfg.strict_endpoint_resources
            && cfg.edge_entry_headway_seconds==2.0
            && std::all_of(nodes.begin(),nodes.end(),[](const Node& n) {
                return n.service==0.0 || n.service==2.0;
            });
        if (cfg.enable_ebs_predecessor_gate) {
            std::map<std::int64_t,int> inbound,outbound;
            for (std::size_t i=0;i<tasks.size();++i) {
                auto& t=tasks[i];
                auto* table=t.leg=="storage_in"?&inbound:t.leg=="storage_out"?&outbound:nullptr;
                if (table && !table->emplace(t.task_id,static_cast<int>(i)).second)
                    throw std::invalid_argument("EBS gate requires unique storage_in/storage_out per task_id");
            }
            for (const auto& pair:outbound) {
                auto prior=inbound.find(pair.first);
                if (prior==inbound.end()) throw std::invalid_argument("storage_out missing storage_in predecessor");
                tasks[pair.second].predecessor=prior->second;
                tasks[prior->second].dependent=pair.second;
            }
        }
        const auto start=std::chrono::steady_clock::now();
        for (const auto& t:tasks) goal_data(t.goal);
        preprocessing_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        std::vector<int> release_order(tasks.size());
        std::iota(release_order.begin(),release_order.end(),0);
        std::stable_sort(release_order.begin(),release_order.end(),[&](int a,int b){return tasks[a].release<tasks[b].release;});
        if (cfg.source_fifo_order=="canonical") {
            // Match the shared Java adapter's stable Double.compare(pass_time)
            // source order. Equal nominal times retain canonical/raw row order.
            // An unreleased or EBS-blocked head owns its place in this queue.
            for (int i:release_order) {
                source_queues[tasks[i].start].push_back(i);
                source_heads.try_emplace(tasks[i].start,0);
            }
        }
        std::map<int,double> previous_generated;
        for (int i:release_order) {
            Task& t=tasks[i];
            t.generated_release=grid_release(quantize(t.release,cfg.release_quantum));
            auto previous=previous_generated.find(t.start);
            if (previous!=previous_generated.end())
                t.generated_release=std::max(t.generated_release,add_time(previous->second,cfg.source_generation_interval));
            previous_generated[t.start]=t.generated_release;
            push_event(t.generated_release,1,i);
        }
    }
    py::dict run() {
        const auto started=std::chrono::steady_clock::now(); const auto cpu_start=process_cpu_seconds();
        {
            py::gil_scoped_release release;
            while (!events.empty()) {
                Event e=events.top();
                if (e.time>cfg.end_time) break;
                if (event_count>=cfg.max_events) {event_budget_exhausted=true;break;}
                events.pop(); ++event_count; simulation_time=e.time;
                Task& t=tasks[e.task];
                if (e.kind==0) {
                    if (cfg.enable_inroute_replanning) {
                        const bool valid=e.generation==t.route_generation && !t.complete_event;
                        RollingRecord r;r.kind="cleanup";r.order=next_ledger_order++;r.time=e.time;r.task=e.task;
                        r.event_generation=e.generation;r.new_generation=t.route_generation;r.valid=valid;
                        if (valid) {
                            if (!t.physically_completed) throw std::logic_error("cleanup precedes physical goal arrival");
                            for (const auto& entry:t.reservations) r.removed.push_back(entry.second->second.id);
                            for (const auto& entry:t.edge_reservations) r.removed.push_back(entry.second->second.id);
                        }
                        rolling_records.push_back(std::move(r));
                        if (!valid) {++stale_cleanups;continue;}
                    }
                    if (t.complete_event) continue;
                    t.complete_event=true;
                    for (auto& entry:t.reservations) {calendars[entry.first].erase(entry.second);--calendar_entries;}
                    t.reservations.clear();
                    for (auto& entry:t.edge_reservations) {edge_calendars[entry.first].erase(entry.second);--edge_calendar_entries;}
                    t.edge_reservations.clear();
                } else if (e.kind==1) {
                    t.released=true;
                    if (t.predecessor<0) activate(e.task,e.time);
                    else if (!tasks[t.predecessor].admitted) t.reason="predecessor_unplanned";
                    else if (cfg.enable_inroute_replanning && !tasks[t.predecessor].physically_completed) t.reason="predecessor_in_network";
                    else {
                        const double ready=quantize(std::max(t.release,tasks[t.predecessor].finish),cfg.release_quantum);
                        if (ready<=e.time) activate(e.task,e.time);
                        else {t.reason="predecessor_in_network";push_event(ready,3,e.task,tasks[t.predecessor].route_generation);}
                    }
                } else if (e.kind==5) launch_future_source(e);
                else if (e.kind==4) process_arrival(e);
                else if (e.kind==3) {
                    if (cfg.enable_inroute_replanning && t.predecessor>=0) {
                        const auto& prior=tasks[t.predecessor];
                        if (!prior.physically_completed || e.generation!=prior.route_generation || tick(e.time)<tick(prior.finish)) continue;
                    }
                    activate(e.task,e.time);
                }
                else if (e.generation==t.generation) attempt(e.task,e.time);
            }
        }
        const double run_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
        const double cpu_seconds=process_cpu_seconds()-cpu_start;
        py::list bags;
        std::uint64_t total_exp=0,total_scoring=0,total_safety=0,total_back=0,total_score_exp=0;
        int admitted=0,completed=0,ontime=0,max_cert=0,max_k=0;
        for (const auto& t:tasks) {
            py::dict b; b["segment_id"]=t.segment_id; b["task_id"]=t.task_id; b["leg"]=t.leg;
            b["release"]=t.release; b["deadline"]=t.deadline;
            b["generated_release"]=t.generated_release;
            b["precomputed_source_eligibility"]=t.generated_release;
            b["activation_time"]=t.activation_time>=0?py::cast(t.activation_time):py::none();
            b["first_planning_attempt_time"]=t.first_planning_attempt_time>=0?py::cast(t.first_planning_attempt_time):py::none();
            b["preplanning_hold_seconds"]=t.first_planning_attempt_time>=0?py::cast(t.first_planning_attempt_time-t.activation_time):py::none();
            b["canonical_to_first_planning_seconds"]=t.first_planning_attempt_time>=0?py::cast(t.first_planning_attempt_time-t.release):py::none();
            b["planning_wait_seconds"]=t.admitted?py::cast(t.admission-t.first_planning_attempt_time):py::none();
            b["last_effective_route_excess_seconds"]=std::isfinite(t.last_effective_route_excess)?py::cast(t.last_effective_route_excess):py::none();
            b["admission_effective_route_excess_seconds"]=t.admitted&&std::isfinite(t.admission_effective_route_excess)?py::cast(t.admission_effective_route_excess):py::none();
            b["admission_static_remaining_seconds"]=t.admitted?py::cast(t.admission_static_remaining):py::none();
            b["admission_route_excess_seconds"]=t.admitted?py::cast(t.admission_route_excess):py::none();
            b["admission_route_budget_violated"]=false;
            b["start"]=nodes[t.start].id; b["goal"]=nodes[t.goal].id;
            const bool done=t.admitted && t.finish<=cfg.end_time && (!event_budget_exhausted || t.finish<=simulation_time)
                && (!cfg.enable_inroute_replanning || t.physically_completed);
            b["admitted"]=t.admitted; b["completed"]=done;
            b["admission"]=t.admitted?py::cast(t.admission):py::none();
            b["finish"]=t.admitted?py::cast(t.finish):py::none();
            b["reported_finish_epoch"]=t.admitted?py::cast(t.completion_epoch):py::none();
            b["completion_epoch"]=t.admitted?py::cast(t.completion_epoch):py::none();
            b["resource_cleanup_epoch"]=t.admitted?py::cast(t.cleanup):py::none();
            b["resource_cleanup_time"]=t.admitted?py::cast(t.cleanup):py::none();
            b["commit_order"]=t.admitted?py::cast(t.commit_order):py::none();
            b["planning_time"]=t.admitted?py::cast(t.admission):py::none();
            b["commit_time"]=t.admitted?py::cast(t.admission):py::none();
            b["route_generation"]=t.route_generation;b["actual_arrived_index"]=t.arrived_index;
            b["actual_finish"]=done?py::cast(t.finish):py::none();
            b["node_reservation_ids"]=t.future_reserved&&!t.admitted?std::vector<std::uint64_t>{}:t.node_reservation_ids;
            b["edge_reservation_ids"]=t.future_reserved&&!t.admitted?std::vector<std::uint64_t>{}:t.edge_reservation_ids;
            if (cfg.future_source_reservation_horizon_seconds>0) {
                b["future_reserved"]=t.future_reserved;b["future_pending"]=t.future_reserved&&!t.admitted;
                b["reservation_time"]=t.future_reserved?py::cast(t.reservation_time):py::none();
                b["reservation_order"]=t.future_reserved?py::cast(t.reservation_order):py::none();
                b["planned_admission"]=t.future_reserved?py::cast(t.planned_admission):py::none();
                b["planned_finish"]=t.future_reserved?py::cast(t.planned_finish):py::none();
                b["planned_resource_cleanup_epoch"]=t.future_reserved?py::cast(t.planned_cleanup):py::none();
                py::list reserved;for (const auto& step:t.reserved_route) reserved.append(py::make_tuple(nodes[step.node].id,step.arrival,step.departure));
                b["reserved_route"]=reserved;b["reserved_node_reservation_ids"]=t.reserved_node_ids;b["reserved_edge_reservation_ids"]=t.reserved_edge_ids;
                b["future_source_searches"]=t.future_searches;b["future_calendar_entries_scanned"]=t.future_calendar_entries_scanned;
            }
            if (cfg.future_source_prefer_earlier_finish) {
                b["future_success_comparisons"]=t.future_success_comparisons;
                b["future_success_preferred"]=t.future_success_preferred;
                b["selected_future_finish"]=t.future_success_preferred?py::cast(t.planned_finish):py::none();
                b["immediate_candidate_finish"]=std::isfinite(t.compared_immediate_finish)?py::cast(t.compared_immediate_finish):py::none();
                b["planned_finish_advance_vs_immediate_certificate_seconds"]=t.future_success_preferred?
                    py::cast(seconds(tick(t.compared_immediate_finish)-tick(t.planned_finish))):py::none();
            }
            if (cfg.future_source_prefer_only_without_ready_successor) {
                b["ready_successor_checks"]=t.ready_successor_checks;
                b["ready_successor_skips"]=t.ready_successor_skips;
                b["ready_successor_activation_pending_skips"]=t.ready_successor_activation_pending_skips;
            }
            b["status"]=event_budget_exhausted&&!done?"event_budget_exhausted":t.reason;
            b["attempts"]=t.attempts; b["retries"]=std::max(0,t.attempts-1);
            b["source_wait_seconds"]=t.admitted?py::cast(t.admission-t.release):py::none();
            b["outside_wait_observed_seconds"]=t.admitted?std::max(0.0,t.admission-t.release):std::max(0.0,(event_budget_exhausted?simulation_time:cfg.end_time)-t.release);
            b["junction_wait_seconds"]=0.0;
            b["search_expansions"]=t.expansions; b["score_expansions"]=t.score_expansions;
            b["local_scoring_calendar_queries"]=t.scoring_queries; b["safety_neighbor_queries"]=t.safety_queries;
            b["backtracks"]=t.backtracks; b["max_certificate_nodes"]=t.max_certificate_depth;
            b["max_observation_depth"]=t.max_observation_depth;
            py::list route,route_decisions,node_resources,edge_resources; double service=0,travel=0;
            for (std::size_t i=0;i<(t.future_reserved&&!t.admitted?0:t.route.size());++i) {
                const auto& step=t.route[i]; route.append(py::make_tuple(nodes[step.node].id,step.arrival,step.departure));
                const bool first=i==0,last=i+1==t.route.size();
                const std::string role=first&&last?"source_goal":first?"source":last?"goal":"internal";
                const bool reserved=!(half_open() && tick(step.arrival)==tick(step.departure));
                const bool checked=reserved && ((!first&&!last)||(cfg.strict_endpoint_resources && nodes[step.node].service>0));
                node_resources.append(py::make_tuple(nodes[step.node].id,step.arrival,step.departure,role,checked,reserved));
                if (!last && cfg.edge_entry_headway_seconds>0)
                    edge_resources.append(py::make_tuple(nodes[step.node].id,nodes[t.route[i+1].node].id,
                        step.departure,add_time(step.departure,cfg.edge_entry_headway_seconds)));
                if (i+1<t.route.size()) route_decisions.append(py::make_tuple(nodes[step.node].id,
                    step.requested_k,step.actual_query_depth,step.local_score_queries,step.score_budget_exhausted));
                if (i+1<t.route.size()) service+=step.departure-step.arrival;
                if (i>0) travel+=step.arrival-t.route[i-1].departure;
            }
            b["route"]=route; b["travel_seconds"]=travel; b["service_seconds"]=service;
            b["route_decisions"]=route_decisions;
            b["node_resource_intervals"]=node_resources;b["edge_resource_intervals"]=edge_resources;
            bags.append(std::move(b));
            admitted+=t.admitted?1:0; completed+=done?1:0; ontime+=done&&t.finish<=t.deadline?1:0;
            total_exp+=t.expansions;total_scoring+=t.scoring_queries;total_safety+=t.safety_queries;
            total_back+=t.backtracks;total_score_exp+=t.score_expansions;
            max_cert=std::max(max_cert,t.max_certificate_depth);max_k=std::max(max_k,t.max_observation_depth);
        }
        std::sort(decision_microseconds.begin(),decision_microseconds.end());
        auto percentile=[&](double q) {return decision_microseconds.empty()?0.0:decision_microseconds[static_cast<std::size_t>(std::ceil(q*decision_microseconds.size()))-1];};
        py::dict stats;
        stats["tasks"]=tasks.size();stats["admitted"]=admitted;stats["completed"]=completed;stats["on_time"]=ontime;
        if (cfg.future_source_reservation_horizon_seconds>0) {
            stats["future_source_eligible_failures"]=future_eligible_failures;stats["future_source_searches"]=future_searches;
            stats["future_source_precommits"]=future_precommits;stats["future_source_launches"]=future_launches;
            stats["future_source_pending_at_horizon"]=future_precommits-future_launches;
            stats["future_chain_nodes"]=future_chain_nodes;stats["future_calendar_queries"]=future_calendar_queries;
            stats["future_calendar_entries_scanned"]=future_calendar_entries_scanned;stats["future_validation_queries"]=future_validation_queries;
            stats["future_mask_empty"]=future_mask_empty;stats["future_chain_rejections"]=future_chain_rejections;
            stats["source_decision_wall_seconds"]=std::accumulate(decision_microseconds.begin(),decision_microseconds.end(),0.0)*1e-6;
            stats["inroute_decision_wall_seconds"]=std::accumulate(inroute_microseconds.begin(),inroute_microseconds.end(),0.0)*1e-6;
        }
        if (cfg.future_source_prefer_earlier_finish) {
            stats["future_success_comparisons"]=future_success_comparisons;
            stats["future_success_preferred"]=future_success_preferred;
            stats["future_success_kept_immediate"]=future_success_kept_immediate;
            stats["future_success_finish_bound_rejections"]=future_success_finish_bound_rejections;
            stats["future_success_mask_empty"]=future_success_mask_empty;
        }
        if (cfg.future_source_prefer_only_without_ready_successor) {
            stats["ready_successor_checks"]=ready_successor_checks;
            stats["ready_successor_skips"]=ready_successor_skips;
            stats["ready_successor_activation_pending_skips"]=ready_successor_activation_pending_skips;
        }
        stats["planning_attempts"]=planning_attempts;stats["failed_attempts"]=failed_attempts;
        stats["search_expansions"]=total_exp;stats["score_expansions"]=total_score_exp;stats["backtracks"]=total_back;
        stats["local_scoring_calendar_queries"]=total_scoring;stats["safety_neighbor_queries"]=total_safety;
        stats["logical_request_reply_messages"]=2*(total_scoring+total_safety+edge_safety_queries+source_resource_queries);
        stats["commit_node_messages"]=std::accumulate(tasks.begin(),tasks.end(),std::uint64_t(0),[](auto n,const Task& t){return n+t.route.size();});
        stats["max_certificate_nodes"]=max_cert;stats["max_observation_depth"]=max_k;
        stats["search_decision_k_histogram"]=search_k_histogram;
        stats["committed_route_hop_k_histogram"]=committed_k_histogram;
        stats["search_actual_calendar_query_depth_histogram"]=actual_query_depth_histogram;
        stats["local_score_budget_exhausted_decisions"]=local_score_budget_exhausted_decisions;
        stats["scored_neighbor_candidates"]=scored_neighbor_candidates;
        stats["edge_safety_queries"]=edge_safety_queries;stats["source_resource_queries"]=source_resource_queries;
        stats["goal_resource_queries"]=goal_resource_queries;stats["peak_edge_calendar_entries"]=peak_edge_calendar_entries;
        stats["skipped_single_choice_scoring"]=skipped_single_choice_scoring;
        stats["static_rank_fastpath_candidates"]=static_rank_fastpath_candidates;
        stats["source_relaxed_budget_attempts"]=relaxed_source_attempts;
        stats["source_relaxed_budget_admissions"]=relaxed_source_admissions;
        stats["source_route_budget_violations"]=0;
        stats["route_bound_prunes"]=route_bound_prunes;
        stats["inroute_decisions"]=inroute_decisions;stats["inroute_keep_certificate"]=inroute_keep;
        stats["inroute_replacement_attempts"]=inroute_attempts;stats["inroute_replacement_successes"]=inroute_success;
        stats["inroute_fallbacks"]=inroute_fallback;stats["inroute_search_expansions"]=inroute_expansions;
        stats["inroute_scoring_queries"]=inroute_scoring_queries;stats["inroute_node_safety_queries"]=inroute_safety_queries;
        stats["stale_arrivals_ignored"]=stale_arrivals;stats["stale_cleanups_ignored"]=stale_cleanups;
        py::dict diagnostics;
        auto node_counts=[&](const auto& counts){py::list rows;for(const auto& entry:counts){py::dict row;row["node"]=nodes[entry.first].id;row["conflict_queries"]=entry.second;rows.append(row);}return rows;};
        auto edge_counts=[&](const auto& counts){py::list rows;for(const auto& entry:counts){py::dict row;row["from"]=nodes[edge_nodes[entry.first].first].id;row["to"]=nodes[edge_nodes[entry.first].second].id;row["conflict_queries"]=entry.second;rows.append(row);}return rows;};
        diagnostics["source_admission_node"]=node_counts(source_node_conflicts);diagnostics["source_admission_edge"]=edge_counts(source_edge_conflicts);
        diagnostics["inroute_replacement_node"]=node_counts(inroute_node_conflicts);diagnostics["inroute_replacement_edge"]=edge_counts(inroute_edge_conflicts);
        diagnostics["interpretation"]="Repeated failed exact resource queries, not unique bags or a causal delay decomposition; local ranking probes excluded";
        stats["conflict_diagnostics"]=diagnostics;
        stats["search_budget_failures"]=search_budget_failures;stats["score_budget_exhaustions"]=score_budget_exhaustions;
        stats["source_endpoint_ignored_conflict_admissions"]=source_ignored_conflicts;
        stats["goal_endpoint_ignored_conflict_admissions"]=goal_ignored_conflicts;
        stats["failed_search_hash_checks"]=failed_hash_checks;stats["futurecalendar_retry_jumps"]=retry_jumps;
        stats["events"]=event_count;stats["event_budget_exhausted"]=event_budget_exhausted;
        stats["last_processed_event_time"]=simulation_time;stats["peak_calendar_entries"]=peak_calendar_entries;
        stats["executed_horizon"]=event_budget_exhausted?simulation_time:cfg.end_time;
        stats["peak_pending_events"]=peak_event_count;stats["cached_goal_tables"]=goal_cache.size();
        stats["preprocessing_seconds"]=preprocessing_seconds;stats["run_wall_seconds"]=run_seconds;stats["run_cpu_seconds"]=cpu_seconds;
        stats["run_cpu_measurement"]="Windows GetProcessTimes kernel+user; std::clock on non-Windows; event loop only";
        stats["decision_microseconds_p50"]=percentile(.50);stats["decision_microseconds_p95"]=percentile(.95);stats["decision_microseconds_p99"]=percentile(.99);
        std::sort(inroute_microseconds.begin(),inroute_microseconds.end());
        auto rolling_percentile=[&](double q){return inroute_microseconds.empty()?0.0:inroute_microseconds[static_cast<std::size_t>(std::ceil(q*inroute_microseconds.size()))-1];};
        stats["inroute_decision_microseconds_p50"]=rolling_percentile(.5);stats["inroute_decision_microseconds_p95"]=rolling_percentile(.95);stats["inroute_decision_microseconds_p99"]=rolling_percentile(.99);
        py::dict contract;
        contract["planner"]="local lookahead ordered neighbour DFS with atomic full continuation certificate";
        contract["runtime_dynamic_rerouting"]=cfg.enable_inroute_replanning;contract["safety_information_range"]="may extend to goal, independently of observation depth";
        contract["max_route_excess_seconds"]=std::isfinite(cfg.max_route_excess_seconds)?py::cast(cfg.max_route_excess_seconds):py::none();
        contract["route_excess_retry_relaxation_rate"]=cfg.route_excess_retry_relaxation_rate;
        contract["source_route_budget_relaxation"]="Only on actual source attempts: base excess + rate * age since immutable first planning attempt; growth floors to integer microseconds. No new wake event; an existing calendar jump may skip an earlier newly permitted detour. No earliest-feasible or monotone THT guarantee; in-route finish-nonincreasing fallback policy unchanged.";
        contract["static_rank_fastpath"]="At requested depth1 and zero congestion weight, return static H without calendar probes; logical score-budget consumption/exhaustion and choice order preserved; actual query depth/count zero.";
        contract["rolling_policy"]="at each physical internal arrival rank neighbours; a single choice or unchanged best keeps fallback; strictly better next attempts exact suffix exchange, finish cannot become later; failure retains all rights";
        contract["rolling_event_order"]="at equal time: physical arrival, resource cleanup, source release, source attempt, EBS activation; each ledger event has a unique increasing ledger_order";
        contract["rolling_ebs_gate"]="release depends on actual predecessor goal event and latest route generation, never a stale predicted completion";
        contract["timing_clocks"]="activation_time records first entry into the external source FIFO; first_planning_attempt_time records first actual head-eligible planning attempt and never resets on failure; admission is successful physical network entry";
        contract["primary_tht_clock"]="sum per original business bag of each leg actual goal arrival minus first_planning_attempt_time; source preplanning hold and canonical elapsed are mandatory companion measures";
        contract["internal_wait_actions"]=false;
        contract["interval_mode"]=cfg.interval_mode;
        contract["physical_ticks_per_second"]=half_open()?py::cast(1000000):py::none();
        contract["interval_conflict"]=half_open()?"half-open intervals on integer microsecond grid; touching endpoints allowed; zero-service points occupy no resource":"closed endpoints, exact double comparisons, including zero-service internal points";
        contract["strict_endpoint_resources"]=cfg.strict_endpoint_resources;
        contract["source_endpoint"]=cfg.strict_endpoint_resources?"positive-service source checked and reserved before external admission":"consumes service, writes reservation, initial conflict check exempt";
        contract["goal_endpoint"]=cfg.strict_endpoint_resources?"finish at arrival; positive-service goal checked and resource retained through departure":"finish at arrival; goal check exempt; optional service-length reservation until quantized completion";
        contract["edge_entry_headway_seconds"]=cfg.edge_entry_headway_seconds;
        contract["edge_resource"]= "directed-edge entry interval only, not whole-edge unit capacity; all endpoint and zero-connector flows included";
        contract["node_resource_intervals_columns"]=py::make_tuple("node","arrival","departure","role","checked","reserved");
        contract["edge_resource_intervals_columns"]=py::make_tuple("from","to","entry","protected_until");
        contract["resource_cleanup"]= "ceil_q(max(business completion epoch, strict goal reservation end, all edge entry window ends)); business finish remains goal arrival";
        contract["failed_search_transaction"]="read-only; no reservation is inserted before a complete route exists";
        contract["retry_bound_scope"]="explored prefixes only; budget truncation can skip an earlier feasible alternative";
        contract["logical_messages"]="simulation counts, no network latency or real distributed concurrency model";
        contract["global_static_preprocessing"]="one service-aware reverse Dijkstra per distinct goal; topology only";
        contract["score_budget_scope"]="max_score_expansions per current-node local ranking; max_expansions per full DFS attempt";
        contract["route_decisions_columns"]=py::make_tuple("node","requested_k","actual_calendar_query_depth","local_score_queries","score_budget_exhausted");
        contract["congestion_signal"]="exact-window blocking delay proxy plus union seconds of active reservations in the future pressure_window; ranking only, no internal waiting";
        contract["source_generation"]="precomputed eligibility uses stable nominal order and source interval; source_fifo additionally paces successful admissions by that interval; no early release; not an exact reproduction of Java generation/comparator quirks";
        contract["source_fifo_order"]=cfg.source_fifo_order;
        contract["canonical_source_order"]="when explicitly enabled: stable original nominal release order, input row order for ties; an unreleased or predecessor-blocked head blocks every later source item, activation does not append/reorder";
        if (cfg.future_source_reservation_horizon_seconds>0) {
            contract["future_source_reservation_horizon_seconds"]=cfg.future_source_reservation_horizon_seconds;
            contract["future_source_reservation_min_wait_seconds"]=cfg.future_source_reservation_min_wait_seconds;
            contract["future_source_policy"]="After failed immediate DFS before first static branch, and minimum immutable-first-attempt age: intersect integer launch mask along one static shortest chain. All positive node and directed-edge entry rights are atomically precommitted. Earliest only for this chain/current snapshot, not all paths. Window independent of observation end. Additional route allowance freezes at actual attempt, not future launch.";
            contract["future_source_lifecycle"]="source_reserve is not physical admission; source_launch consumes the same IDs at planned_admission, then advances canonical FIFO and schedules physical arrivals/cleanup. EBS remains gated by actual goal arrival. Failed immediate DFS still counts failed_attempts even if future rescue succeeds; launch is not another planning attempt.";
            contract["future_source_measurement"]="Fixed-chain construction, calendar-entry scanning and exact validation are included in existing source decision wall samples (goal-table lookup through reservation/dispatch, not pure DFS). Wall sums reuse existing samples without new clock calls. Separate queries/scanned counters expose extra work, not measured protocol messages. Future chain route_decisions requested_k=0 records no local rank query; committed_route_hop_k_histogram retains original immediate-DFS scope. No real network timing or global throughput guarantee.";
            contract["rolling_event_order"]="at equal time: physical arrival or reserved source launch by event serial, resource cleanup, source release, source attempt, EBS activation; ledger_order is global";
        }
        if (cfg.future_source_prefer_earlier_finish) {
            contract["future_source_prefer_earlier_finish"]=true;
            contract["future_source_policy"]="Failed immediate DFS keeps the existing forced-prefix and minimum-age rescue gate. Successful immediate DFS additionally compares a complete static-chain future certificate, selecting it only if its integer-us goal arrival is strictly earlier than the found immediate certificate. Both branches atomically reserve all positive-node and directed-edge entry rights, preserve canonical FIFO until actual launch, freeze route allowance at the actual attempt, and keep the temporal window independent of observation end. Earliest is only for this chain/current snapshot, not all paths.";
            contract["future_success_comparison"]="After successful immediate DFS and before any admission mutation, compare the complete static-chain future certificate. Choose only strictly earlier goal arrival on integer-us ticks; equal/later/no improving slot keeps the original immediate certificate. This success branch is independent of failure min-wait/forced-prefix; failed-DFS rescue remains unchanged. A finite finish bound removes only non-improving launch offsets, never uses observation end.";
            contract["future_success_measurement"]="Comparisons are not failed_attempts or future_eligible_failures. Existing future searches/queries/scans also include these comparisons; an empty comparison mask means no improving slot in its finish-bounded window. All work remains inside the original source decision sample. Planned advance is relative only to this attempt's found immediate certificate, not a causal individual or system THT guarantee; later rerouting and other bags may change outcomes. FIFO remains blocked until actual future launch; preplanning and fixed-window completion must be reported.";
        }
        if (cfg.future_source_prefer_only_without_ready_successor) {
            contract["future_source_prefer_only_without_ready_successor"]=true;
            contract["ready_successor_policy"]="Before successful-DFS future comparison, inspect only the canonical adjacent source item. If actually released and predecessor absent or physically completed with q1 gate time reached, retain the immediate certificate. Same-time physical completion is ready even before its activation event. Failed-DFS rescue is unchanged. No extra calendar/graph queries; map lookups O(log sources), adjacent state access O(1).";
            contract["ready_successor_boundary"]="Current business readiness is not route feasibility. Unreleased or not-yet-completed successors can become ready during source hold, so this gate does not guarantee throughput or eliminate head-of-line delay. Planning successes equal comparisons plus ready_successor_skips; skips are neither failed attempts nor unsuccessful future probes.";
        }
        stats["contract"]=contract;
        py::list ledger;
        for (const auto& r:rolling_records) {
            py::dict event;event["ledger_order"]=r.order;event["time"]=r.time;event["kind"]=r.kind;
            event["segment_id"]=tasks[r.task].segment_id;
            if (r.kind=="source_commit" || r.kind=="replace_commit" || r.kind=="source_reserve") {
                event["old_generation"]=r.old_generation;event["new_generation"]=r.new_generation;
                event["current_index"]=r.index;event["goal_arrival"]=r.finish;event["resource_cleanup_epoch"]=r.cleanup;
                event["node_reservation_ids"]=r.node_ids;event["edge_reservation_ids"]=r.edge_ids;event["removed_ids"]=r.removed;
                py::list route;for (const auto& step:r.route) route.append(py::make_tuple(nodes[step.node].id,step.arrival,step.departure));
                event["committed_route"]=route;
                if (r.kind=="source_reserve") {event["current_node"]=py::none();event["planned_admission"]=r.planned_admission;}
            } else if (r.kind=="source_launch") {
                event["generation"]=r.new_generation;event["index"]=0;event["node"]=nodes[r.node].id;
                event["reference_reservation_order"]=r.reference_reservation_order;
            } else if (r.kind=="arrival") {
                event["generation"]=r.new_generation;event["index"]=r.index;event["node"]=nodes[r.node].id;
            } else {
                event["event_generation"]=r.event_generation;event["generation"]=r.event_generation;
                event["current_generation"]=r.new_generation;event["valid"]=r.valid;event["removed_ids"]=r.removed;
            }
            ledger.append(std::move(event));
        }
        stats["rolling_ledger_records"]=rolling_records.size();
        py::dict result;result["schema"]="g31.nowait.prototype.v1";result["bags"]=bags;result["summary"]=stats;result["contract"]=contract;
        result["rolling_events"]=ledger;
        return result;
    }
};
py::dict plan(const py::sequence& nodes,const py::sequence& edges,const py::sequence& tasks,const py::dict& config) {
    Planner p(nodes,edges,tasks,parse_config(config)); return p.run();
}
} // namespace g31_nowait
PYBIND11_MODULE(g31_nowait,m) {
    m.doc()="Research no-internal-wait planner: local scoring and full continuation certificate; not legacy G31";
    m.def("plan",&g31_nowait::plan,py::arg("nodes"),py::arg("edges"),py::arg("tasks"),py::arg("config")=py::dict());
}
