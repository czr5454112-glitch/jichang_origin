"""Prepare the isolated fixed-2s calendar index candidate; never build or run it."""
from pathlib import Path
import difflib, hashlib, json, shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PARENT=ROOT/'build/g31_no_wait_010c/source'
EXPECTED='01e3289e7934ae164fd0014c34878657027cff7811186384080cf885d68523e3'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v): Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')

def main():
    assert sha(PARENT/'core.cpp')==EXPECTED
    out=HERE/'source'
    if out.exists(): raise FileExistsError(out)
    old=(PARENT/'core.cpp').read_text(encoding='utf-8'); new=old
    replacements=[
      ('    double preprocessing_seconds = 0;\n',
       '    double preprocessing_seconds = 0;\n    bool fixed_two_second_calendars = false;\n'),
      ('        auto it = c.begin();\n        for (; it != c.end() && it->first <= departure; ++it) {',
       '        // Every stored window is at most 2s under this validated tuple.\n'
       '        // S < A-2s implies E < A, so these entries cannot contribute to\n'
       '        // overlap, latest_end, or earliest_cleanup. Keep the original\n'
       '        // upper loop and all exact tests; legacy/mixed durations fall back.\n'
       '        auto it = use_half_open && fixed_two_second_calendars\n'
       '            ? c.lower_bound(seconds(std::max<std::int64_t>(0,tick(arrival)-2000000LL)))\n'
       '            : c.begin();\n'
       '        for (; it != c.end() && it->first <= departure; ++it) {'),
      ('            for (const auto& entry:calendar) {\n                if (tick(entry.first)>=upper+hi) break;',
       '            // For all candidate launches R>=lower, an old window ending\n'
       '            // before lower+lo cannot clear any mask bit. Integer ticks\n'
       '            // avoid subtracting rounded doubles or skipping equal keys.\n'
       '            auto it=fixed_two_second_calendars\n'
       '                ? calendar.lower_bound(seconds(std::max<std::int64_t>(0,lower+lo-2000000LL)))\n'
       '                : calendar.begin();\n'
       '            for (;it!=calendar.end();++it) {\n'
       '                const auto& entry=*it;\n'
       '                if (tick(entry.first)>=upper+hi) break;'),
      ('        if (cfg.enable_ebs_predecessor_gate) {\n            std::map<std::int64_t,int> inbound,outbound;',
       '        // All insertion paths use each node service or the edge-entry\n'
       '        // headway; zero node windows are omitted in half-open mode.\n'
       '        fixed_two_second_calendars=half_open() && cfg.strict_endpoint_resources\n'
       '            && cfg.edge_entry_headway_seconds==2.0\n'
       '            && std::all_of(nodes.begin(),nodes.end(),[](const Node& n) {\n'
       '                return n.service==0.0 || n.service==2.0;\n'
       '            });\n'
       '        if (cfg.enable_ebs_predecessor_gate) {\n            std::map<std::int64_t,int> inbound,outbound;')]
    for a,b in replacements:
        assert new.count(a)==1,a
        new=new.replace(a,b)
    out.mkdir()
    (out/'core.cpp').write_text(new,encoding='utf-8')
    shutil.copyfile(PARENT/'CMakeLists.txt',out/'CMakeLists.txt')
    (HERE/'calendar_index_only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='frozen010c/core.cpp',tofile='candidate011/core.cpp')),encoding='utf-8')
    build=(HERE.parent/'candidate010/build_isolated.py').read_text(encoding='utf-8').replace('isolated010','isolated011').replace("default='010'","default='011'")
    (HERE/'build_isolated.py').write_text(build,encoding='utf-8')
    save(HERE/'PREDECLARED_PLAN.json',dict(schema='g31.candidate011.calendar_index.v1',status='prepared_before_build_or_native',
      parent_source=dict(path=str(PARENT/'core.cpp'),sha256=EXPECTED),source_sha256=sha(out/'core.cpp'),
      only_change='Start two calendar scans at a proven lower_bound. No policy, scoring, event, resource, retry, arithmetic, or pressure changes.',
      predicate='global half_open AND strict endpoint resources AND edge headway exactly 2 AND every node service exactly 0 or 2; otherwise original full scan',
      proof=['Stored nonempty node/edge windows have duration 2000000 ticks; all start keys are canonical seconds(integer ticks).',
        'For overlap query [A,B), skipped S<A-D gives E=S+D<A. lower_bound includes every duplicate key at its boundary.',
        'For launch mask R in [L,U] and resource offset [lo,hi), skipped S<L+lo-D gives E<L+lo<=R+lo.',
        'max(0,lower tick) is safe because all stored starts are nonnegative. Original upper stopping conditions and overlap tests remain.',
        'Do not erase past prefixes or pending future rights; retrieval is by the queried interval, never by simulation now.',
        'Keep ignore_owner, full overlap iteration, max end and min cleanup, so raw and quantized retries remain exact.'],
      allowed_output_differences=['existing timing fields','summary.future_calendar_entries_scanned','bags[*].future_calendar_entries_scanned'],
      exact_outputs='Every other bag field, summary field, contract field, route, clock, retry, query/expansion count, reservation ID and rolling ledger entry',
      validation=['12 existing default-off differential fixtures','8 existing 010 physical/lifecycle fixtures with unchanged independent auditors',
        'Targeted 2s touch, 1us overlap, negative lower tick, ignore-own rolling replacement, retained old prefixes, pending future rights, mixed duration and closed legacy fallback'],
      performance_boundary='No speed claim before sequential full-run exact parity and measured timing. Scanned-entry counters report actual reduced work. No source/endpoint/edge safety relaxation.',
      full_run_controls='Unmodified frozen010c minwait2/horizon60 controls on both maps, not the minwait30 ablation'))
    print(json.dumps(dict(source_sha256=sha(out/'core.cpp'),patch=str(HERE/'calendar_index_only.patch')),indent=2))

if __name__=='__main__': main()
