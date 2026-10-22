"""Record the verified source005 successor while the frozen003 run continues."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
path = root/'docs/g31_ics_circulation/RESEARCH_STATE.json'
state = json.loads(path.read_text(encoding='utf8'))
state['current_stage'] = ('P0-P4 in progress: source003 full C00/C10/TF-current closed, TF-B1-60 remains active. '
    'The stale capture/receipt/history repair is frozen as terminal_flow_runtime_005 after 462 passing pure regressions. '
    'Workflow005 registers the same finite 32 native starts and waits for exact predecessor closure and strict export-equivalence gates. '
    'Workflow004 was superseded before dispatch, with zero native starts. Observed C10 and TF-current harms reject service promotion; TEST and R1 remain locked.')
state['working_tree_identity'] = ('codex/g31-ics-v3-circulation; task anchor c7121c12b3d59a1d6fcd4919bb13bb86aa2ff91f; '
    'terminal_flow_runtime_005 source manifest 22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef; '
    'active predecessor keeps its own runtime003 identity; publication commit is separate.')
state['active_experiment'].update(status='terminal_flow_source003_last_run_active_source005_waiting',
    successor_workflow='outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/registration.json',
    successor_registration_sha256='1509684b0eaa8433795343d508142654f90927ef70553783c272f343205aa30d',
    successor_source_manifest_sha256='22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef',
    successor_native_starts_registered=32, successor_native_starts_at_registration=0,
    successor_pure_tests=462,
    capture_repair_diagnosis='outputs/experiments/g31_ics_terminal_flow_20261021/claim_capture_fix005_001/DIAGNOSIS.md')
path.write_bytes((json.dumps(state, ensure_ascii=False, indent=2)+'\n').replace('\n','\r\n').encode('utf8'))
path = root/'docs/g31_ics_circulation/README.md'
lines = path.read_text(encoding='utf8').splitlines()
lines[2] = ('> 当前执行补充（2026-10-21）：完整同源 C00/C10/TF-current 已闭合；C10、TF-current 分别出现 234、411 件已知完成方向损害，均未通过服务门槛。'
    '原 runtime003 的 TF-B1-60 保留冻结执行。旧快照/接收记录去重修复已冻结为 terminal_flow_runtime_005，462 项回归通过，'
    '相同 32 次后继对照已登记并等待前链正常闭合及严格等价门禁。004 在派发前撤销（0 次原生启动），历史证据保留。'
    '详见 [同源完整对照](TERMINAL_FLOW_FULL_SOURCE003_COMPARISON.md)。')
path.write_bytes(('\n'.join(lines)+'\n').replace('\n','\r\n').encode('utf8'))
