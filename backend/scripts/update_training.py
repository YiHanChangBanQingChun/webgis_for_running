"""Save reproducible FIT observations and rebuild the sibling training database."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.paths import PROJECT_DIR, PROCESSED_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', default='2026-07-01')
    args = parser.parse_args()
    root = PROJECT_DIR.parent / 'training_database'
    tracker = PROJECT_DIR / 'tools/training/track_training.py'
    if not (root / 'journal.json').exists():
        parser.error(f'Missing training journal: {root}')
    subprocess.run([sys.executable, str(tracker), 'backup'], check=True)
    observations = []
    override_path = PROJECT_DIR / 'data/activity-overrides.json'
    overrides = json.loads(override_path.read_text()) if override_path.exists() else {}
    for summary in json.loads((PROCESSED_DIR / 'activities.json').read_text()):
        if not summary.get('date') or summary['date'] < args.since:
            continue
        archive_path = PROCESSED_DIR / summary['full_data_path']
        archive = json.loads(archive_path.read_text())
        override = overrides.get(str(summary['id']), {})
        reason = override.get('user_note') if override.get('training_excluded') else None
        if summary['sport'] != 'running':
            reason = '非跑步或 FIT 未识别运动类型；单独保留，不计跑量'
        if summary.get('timezone_evidence') not in ('explicit_offset', 'fit_date_time_UTC'):
            reason = '时区证据不足，不用于精确中国训练日汇总'
        observations.append(dict(summary=summary, source_file=str(archive_path),
            source_sha256=archive['source']['sha256'], include_formal=int(reason is None),
            exclusion_reason=reason,
            session=[m for m in archive['messages'] if m['message_type']=='session'],
            laps=[m for m in archive['messages'] if m['message_type']=='lap']))
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_fit_observations__%H%M%S%f')
    raw = root / 'raw' / (stamp + '.json')
    raw.write_text(json.dumps(dict(observations=observations), ensure_ascii=False, indent=2), encoding='utf-8')
    subprocess.run([sys.executable, str(tracker), 'build'], check=True)
    subprocess.run([sys.executable, str(tracker), 'verify'], check=True)
    print(f'Saved {len(observations)} FIT observations: {raw}')


if __name__ == '__main__':
    main()
