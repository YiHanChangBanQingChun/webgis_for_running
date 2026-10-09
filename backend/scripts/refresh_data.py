"""Rebuild a complete FIT export in staging, preserving the previous dataset."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.paths import DEFAULT_FIT_SOURCE, PROJECT_DIR, PROCESSED_DIR
from app.fit_archive import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_FIT_SOURCE)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    files = sorted(source.glob('*.fit'))
    if not files:
        parser.error(f'No FIT files in {source}; pass the extracted export directory.')
    target = PROCESSED_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.parent / '.import-lock'
    try:
        lock.mkdir()
    except FileExistsError:
        parser.error(f'An import is already running (lock: {lock}).')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    stage = target.parent / ('.import-' + stamp)
    backup = target.parent / ('processed-backup-' + stamp)
    env = dict(os.environ, RUNNING_WEBGIS_DATA_DIR=str(stage))
    try:
        (stage / 'activities').mkdir(parents=True)
        reused = 0
        for fit in files:
            old = target / 'activities' / (fit.stem + '.full.json')
            if not old.exists():
                continue
            archive = json.loads(old.read_text(encoding='utf-8'))
            if archive.get('source', {}).get('sha256') == sha256_file(fit):
                shutil.copy2(old, stage / 'activities' / old.name)
                reused += 1
        print(f'Export: {len(files)} activities; reusing {reused} matching SHA-256 archives.', flush=True)
        profile = target / 'athlete-profile.json'
        if profile.exists():
            shutil.copy2(profile, stage / profile.name)
        for script in [('import_fit.py', '--source', str(source), '--repair-partial'),
                       ('build_derived.py',), ('build_spatial_grid.py',),
                       ('build_quality_report.py', '--source', str(source))]:
            subprocess.run([sys.executable, str(Path(__file__).parent / script[0]), *script[1:]],
                           cwd=PROJECT_DIR, env=env, check=True)
        report = json.loads((stage / 'import-report.json').read_text(encoding='utf-8'))
        if not report['readiness']['api_ready']:
            raise RuntimeError(f'Quality gate failed; previous dataset preserved. Inspect {stage}')
        if target.exists():
            target.rename(backup)
        try:
            stage.rename(target)
        except BaseException:
            if backup.exists():
                backup.rename(target)
            raise
        print(f'Data ready: {target}\nPrevious data: {backup}\nRestart API servers to reload cached data.')
    finally:
        lock.rmdir()


if __name__ == '__main__':
    main()
