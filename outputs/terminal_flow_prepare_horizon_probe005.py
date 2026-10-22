"""Prepare a distinct bounded wrapper; never modifies frozen existing wrappers."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'outputs/terminal_flow_bins600_offline005.py'
target=ROOT/'outputs/terminal_flow_horizon_probe_offline005.py'
assert not target.exists()
text=source.read_text(encoding='utf8')
old="HELPERS = {'bins600': ROOTDATA/'bins600_science_005.py'}"
new="HELPERS = {'horizon_probe': ROOTDATA/'projection_horizon_probe_005.py'}"
assert text.count(old)==1;text=text.replace(old,new)
old="need(len(tasks) == 1 and tasks[0]['kind'] == 'bins600' and tasks[0]['id'] == 'bins600', 'single_bins600_science_task')"
new="need(len(tasks) == 1 and tasks[0]['kind'] == 'horizon_probe' and tasks[0]['id'] == 'horizon_probe', 'single_horizon_probe_task')"
assert text.count(old)==1;text=text.replace(old,new)
target.write_text(text,encoding='utf8')
print(target)
