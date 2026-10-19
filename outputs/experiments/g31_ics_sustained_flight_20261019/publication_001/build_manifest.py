"""Freeze an explicitly reviewed list; does not discover files, stage, or push."""
from pathlib import Path
import argparse
import json
import subprocess
import time
from verify_publication import sha, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    selected = sorted(set(args.files.read_text(encoding='utf-8').splitlines()))
    rows = []
    for relative in selected:
        assert relative and not Path(relative).is_absolute()
        target = (root / relative).resolve()
        assert target.is_relative_to(root) and target.is_file()
        rows.append({'path': target.relative_to(root).as_posix(),
                     'executed_worktree_sha256': sha(target),
                     'expected_committed_content_sha256': sha(target), 'bytes': target.stat().st_size,
                     'publication_transform': 'none; selected evidence and source use exact-byte Git attributes'})
    git = lambda *a: subprocess.check_output(['git', *a], cwd=root, text=True).strip()
    manifest = {'schema': 'g31.sustained_flight.selected_publication.v1',
                'created_utc_epoch': time.time(), 'base_commit': git('rev-parse', 'HEAD'),
                'branch': git('branch', '--show-current'), 'files': rows,
                'published_commit': 'Recorded separately after commit; no self-referential hash',
                'historical_current_source_equality_required': False,
                'historical_executed_archives_required': True,
                'committed_content_identity': 'Must be verified against the actual Git index/export after staging; expected values here do not by themselves assert a successful commit',
                'scope': 'Selected new stage source/evidence and original publication repair; no claim of rerunning historical experiments',
                'external_runtime_dependencies': 'Saved plans bind Windows native binaries, interpreter and existing repository data. Hash-only export verification does not execute or rebuild them.'}
    result = verify(root, manifest)
    assert result['status'] == 'passed', result['failures'][:10]
    output = Path(__file__).with_name('MANIFEST.json')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'manifest': str(output), 'sha256': sha(output), **result}, ensure_ascii=False))


if __name__ == '__main__':
    raise SystemExit(main())
