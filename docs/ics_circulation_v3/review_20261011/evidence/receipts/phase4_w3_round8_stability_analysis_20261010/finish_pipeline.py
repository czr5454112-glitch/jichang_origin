"""Finish this running experiment after its immutable full manifest is sealed.

No new simulations, scheduling service, or policy changes. Wait time overlaps
the already running physical experiment and must not be added to its wall time.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import process_time, perf_counter, sleep

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'phase4_w3_same_zone_stability_20261010'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def main():
    cpu, wall = process_time(), perf_counter()
    output = HERE / 'pipeline'
    output.mkdir(exist_ok=False)
    programs = ('analyse_results.py', 'paired_statistics.py', 'plot_results.py', 'report_results.py')
    before = {name: sha(HERE / name) for name in programs}
    write(output / 'before.json', before)
    rows, failure = [], None
    try:
        print('Waiting for sealed full-stage manifest; no physical branch is launched.', flush=True)
        while True:
            try:
                path = SOURCE / 'full/manifest.json'
                manifest = json.loads(path.read_bytes())
                summary_path = SOURCE / 'full/summary.json'
                summary = json.loads(summary_path.read_bytes())
                if sha(summary_path) == manifest[str(Path('full/summary.json'))] and len(summary['rows']) == summary['planned_unique_physical']:
                    break
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                pass
            sleep(15)
        assert before == {name: sha(HERE / name) for name in programs}, 'analysis program changed while waiting'
        print('Full stage sealed; starting read-only final extraction and analysis.', flush=True)
        commands = [
            ['analyse_results.py', 'extract', '--output', str(HERE / 'extraction_final.json')],
            ['analyse_results.py', 'analyse', '--output', str(HERE / 'results')],
            ['plot_results.py'], ['report_results.py']]
        for index, command in enumerate(commands):
            start = perf_counter()
            value = subprocess.run([sys.executable, str(HERE / command[0]), *command[1:]],
                cwd=HERE.parents[3], capture_output=True, text=True, encoding='utf-8', errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            (output / f'{index:02d}.stdout.txt').write_text(value.stdout, encoding='utf-8')
            (output / f'{index:02d}.stderr.txt').write_text(value.stderr, encoding='utf-8')
            rows.append({'command': command, 'returncode': value.returncode, 'wall_seconds': perf_counter() - start,
                         'child_cpu_scope': 'Counted by the separate command receipt; this row is nested wall only, not additional CPU.'})
            print(command[0], value.returncode, flush=True)
            if value.returncode:
                raise RuntimeError('postprocessing failed; original stdout/stderr retained')
        assert before == {name: sha(HERE / name) for name in programs}
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    write(output / 'resource.json', {'parent_cpu_seconds': process_time() - cpu,
        'wall_including_overlapping_wait_seconds': perf_counter() - wall,
        'physical_simulations': 0, 'rows': rows, 'failure': failure,
        'scope': 'One local finish pipeline for the currently running experiment. Parent CPU only; wait and child wall overlap existing stages and are never added to global wall. Child stage CPU is separately billed; subprocess startup imports remain outside those stage timers.'})
    if failure:
        raise RuntimeError(failure)


if __name__ == '__main__':
    main()
