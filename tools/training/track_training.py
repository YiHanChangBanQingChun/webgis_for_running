"""Local, standard-library-only COROS training journal. No network or credentials.

Use build after saving COROS tool outputs into raw/YYYY-MM-DD_<kind>.json.
Imports are transactional and repeatable; COROS identifiers remain TEXT.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

if hasattr(sys.stdout,'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# The tracked copy in webgis_for_running/tools/training also targets the sibling database.
_script_dir = Path(__file__).resolve().parent
ROOT = _script_dir if (_script_dir / 'journal.json').exists() else _script_dir.parents[2] / 'training_database'
DB = ROOT / "training.sqlite3"
CN = dt.timezone(dt.timedelta(hours=8))
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activities(
 activity_id TEXT PRIMARY KEY, date_cn TEXT NOT NULL, sport_type INTEGER,
 location_label TEXT, start_timestamp INTEGER, end_timestamp INTEGER,
 distance_km REAL, duration_s REAL, pace_s_km REAL, avg_hr REAL, max_hr REAL,
 cadence REAL, power_w REAL, ascent_m REAL, descent_m REAL, calories REAL,
 training_load REAL, aerobic_te REAL, anaerobic_te REAL, coros_focus TEXT,
 coros_performance TEXT, perceived_effort TEXT, source TEXT NOT NULL,
 source_file TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS laps(
 activity_id TEXT NOT NULL REFERENCES activities(activity_id), group_type INTEGER,
 lap_index INTEGER, distance_km REAL, duration_s REAL, cumulative_s REAL,
 pace_s_km REAL, avg_hr REAL, max_hr REAL, cadence REAL, stride_m REAL,
 ground_time_ms REAL, power_w REAL, raw_json TEXT NOT NULL,
 PRIMARY KEY(activity_id,group_type,lap_index));
CREATE TABLE IF NOT EXISTS daily_metrics(
 date_cn TEXT PRIMARY KEY, short_load REAL, long_load REAL, load_ratio REAL,
 load_comment TEXT, hrv_ms REAL, hrv_baseline REAL, hrv_low REAL, hrv_high REAL,
 hrv_status TEXT, resting_hr REAL, source TEXT);
CREATE TABLE IF NOT EXISTS fitness_snapshots(
 snapshot_id TEXT PRIMARY KEY,date_cn TEXT,vo2max REAL,running_level REAL,
 threshold_pace_s_km REAL,pred_5k_s REAL,pred_10k_s REAL,pred_hm_s REAL,
 pred_marathon_s REAL,source TEXT,notes TEXT);
CREATE TABLE IF NOT EXISTS recovery_snapshots(
 snapshot_id TEXT PRIMARY KEY,observed_date_cn TEXT,recovery_pct REAL,
 full_recovery_hours REAL,level TEXT,source TEXT,
 note TEXT DEFAULT 'Point-in-time estimate, not proof of musculoskeletal recovery');
CREATE TABLE IF NOT EXISTS threshold_snapshots(
 snapshot_id TEXT PRIMARY KEY,date_cn TEXT,threshold_pace_s_km REAL,
 threshold_hr_bpm REAL,zone_pace_fast_s_km REAL,zone_pace_slow_s_km REAL,
 source TEXT,notes TEXT);
CREATE TABLE IF NOT EXISTS fit_archive(
 activity_id TEXT PRIMARY KEY,original_date TEXT,date_cn TEXT,start_time TEXT,
 timezone_confidence TEXT,distance_km REAL,duration_s REAL,pace_s_km REAL,
 avg_hr REAL,max_hr REAL,parse_status TEXT,full_data_path TEXT,track_path TEXT,
 source_file TEXT,summary_json TEXT);
CREATE TABLE IF NOT EXISTS fit_observations(
 activity_id TEXT PRIMARY KEY,date_cn TEXT,start_time TEXT,timezone_evidence TEXT,
 sport TEXT,distance_km REAL,duration_s REAL,pace_s_km REAL,avg_hr REAL,max_hr REAL,
 source TEXT NOT NULL,source_file TEXT,source_sha256 TEXT,
 include_formal INTEGER NOT NULL DEFAULT 1,exclusion_reason TEXT,raw_json TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS observed_training AS
 SELECT activity_id,date_cn,location_label,distance_km,duration_s,pace_s_km,avg_hr,
 training_load,coros_focus,source FROM activities
 UNION ALL
 SELECT activity_id,date_cn,'FIT 跑步',distance_km,duration_s,pace_s_km,avg_hr,
 NULL,NULL,source FROM fit_observations f
 WHERE include_formal=1 AND sport='running'
 AND NOT EXISTS(SELECT 1 FROM activities a WHERE a.activity_id=f.activity_id);
CREATE VIEW IF NOT EXISTS weekly_observed_training AS
 SELECT date(date_cn,'-' || ((CAST(strftime('%w',date_cn) AS INTEGER)+6)%7) || ' days') AS week_monday,
 count(*) AS activities,count(DISTINCT date_cn) AS running_days,
 round(sum(distance_km),3) AS km,round(sum(duration_s)/3600.0,3) AS hours,
 sum(training_load) AS known_load,
 sum(CASE WHEN training_load IS NULL THEN 1 ELSE 0 END) AS unknown_load_activities
 FROM observed_training GROUP BY week_monday;
CREATE TABLE IF NOT EXISTS journal(
 entry_id TEXT PRIMARY KEY,date_cn TEXT,kind TEXT,activity_id TEXT,
 source TEXT,status TEXT,title TEXT,content_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS goals(
 goal_id TEXT PRIMARY KEY,declared_date TEXT,event TEXT,target_seconds REAL,
 priority TEXT,race_window TEXT,status TEXT,source TEXT,notes TEXT);
CREATE TABLE IF NOT EXISTS calendar_days(
 date_cn TEXT PRIMARY KEY,status TEXT,source TEXT,note TEXT);
CREATE TABLE IF NOT EXISTS raw_snapshots(
 snapshot_id TEXT PRIMARY KEY,observed_date_cn TEXT,kind TEXT,path TEXT,
 sha256 TEXT,payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activities(date_cn);
CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(date_cn);
CREATE VIEW IF NOT EXISTS daily_training AS
 SELECT date_cn,count(*) AS activity_count,round(sum(distance_km),3) AS km,
 sum(duration_s) AS duration_s,sum(training_load) AS known_load
 FROM activities GROUP BY date_cn;
CREATE VIEW IF NOT EXISTS weekly_training AS
 SELECT date(date_cn,'-' || ((CAST(strftime('%w',date_cn) AS INTEGER)+6)%7) || ' days') AS week_monday,
 count(*) AS activities,count(DISTINCT date_cn) AS running_days,
 round(sum(distance_km),3) AS km,round(sum(duration_s)/3600.0,3) AS hours,
 sum(training_load) AS known_load FROM activities GROUP BY week_monday;
CREATE VIEW IF NOT EXISTS history_index AS
 SELECT a.activity_id,a.date_cn,a.distance_km,a.duration_s,a.avg_hr,'COROS_MCP' AS source
 FROM activities a UNION ALL
 SELECT f.activity_id,f.date_cn,f.distance_km,f.duration_s,f.avg_hr,'LOCAL_FIT' AS source
 FROM fit_archive f WHERE NOT EXISTS(SELECT 1 FROM activities a WHERE a.activity_id=f.activity_id);
"""


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def unwrap(payload):
    if isinstance(payload, dict) and 'content' in payload:
        if payload.get('isError'):
            raise ValueError('COROS tool returned isError')
        value = '\n'.join(b.get('text', '') for b in payload['content'] if b.get('type') == 'text')
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return payload


def seconds(value):
    parts = [float(x) for x in str(value).split(':')]
    return sum(x * 60 ** i for i, x in enumerate(reversed(parts)))


def fmt_value(value):
    return f"{value:.0f}" if value is not None else "—"


def fmt_pace(value):
    if value is None:
        return '—'
    n = round(value)
    return f'{n // 60}:{n % 60:02d}'


def numeric(text, label):
    match = re.search(r'^' + re.escape(label) + r': ([\d.]+)', text, re.M)
    return float(match[1]) if match else None


def text_field(text, label):
    match = re.search(r'^' + re.escape(label) + r': (.+)$', text, re.M)
    return match[1] if match else None


def put(connection, table, row, key):
    columns = list(row)
    # table/column names are internal constants, not CLI input.
    sql = f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})"
    sql += f" ON CONFLICT({key}) DO UPDATE SET " + ','.join(f'{c}=excluded.{c}' for c in columns if c != key)
    connection.execute(sql, [row[c] for c in columns])


def import_records(connection, payload, path):
    text = unwrap(payload)
    blocks = re.split(r'\n(?=\d+\. )', text)[1:]
    imported = 0
    for block in blocks:
        match = re.search(r'LabelId: (\d+) \| SportType: (\d+)', block)
        if not match:
            raise ValueError(f'Unparsed activity in {path}')
        activity_id, sport_type = match.groups()
        day = re.search(r'— (\d{4}-\d{2}-\d{2})', block)[1]
        distance, unit = re.search(r'Distance: ([\d.]+) (km|m)', block).groups()
        window = re.search(r'startTimestamp=(\d+) \| endTimestamp=(\d+)', block)
        start = int(window[1]) if window else None
        end = int(window[2]) if window else None
        if start and dt.datetime.fromtimestamp(start, CN).date().isoformat() != day:
            raise ValueError(f'Timestamp/date mismatch for {activity_id}')
        put(connection, 'activities', dict(
            activity_id=activity_id, date_cn=day, sport_type=int(sport_type),
            location_label=re.search(r'Location: (.+)', block)[1],
            start_timestamp=start, end_timestamp=end,
            distance_km=float(distance) / (1000 if unit == 'm' else 1),
            duration_s=seconds(re.search(r'Duration: ([\d:]+)', block)[1]),
            pace_s_km=seconds(re.search(r'Average Pace: ([\d:]+)', block)[1]),
            avg_hr=float(re.search(r'Avg HR: ([\d.]+)', block)[1]),
            calories=float(re.search(r'Calories: ([\d.]+)', block)[1]),
            source='COROS_MCP', source_file=str(path), updated_at=now()), 'activity_id')
        imported += 1
    declared = re.search(r'\((\d+) records\)', text)
    if declared and int(declared[1]) != imported:
        raise ValueError(f'Record count mismatch: declared {declared[1]}, parsed {imported}')


def import_details(connection, payload):
    for activity_id, output in payload.items():
        if not connection.execute('SELECT 1 FROM activities WHERE activity_id=?', (activity_id,)).fetchone():
            raise ValueError(f'Detail without activity record: {activity_id}')
        detail = unwrap(output['detail'])
        fields = dict(max_hr=None, cadence=numeric(detail, 'Average Cadence'),
            power_w=numeric(detail, 'Average Power'), training_load=numeric(detail, 'Training Load'),
            aerobic_te=numeric(detail, 'Aerobic TE'), anaerobic_te=numeric(detail, 'Anaerobic TE'),
            coros_focus=text_field(detail, 'Training Focus'),
            coros_performance=text_field(detail, 'Performance'),
            perceived_effort=text_field(detail, 'Perceived Effort'))
        elevation = re.search(r'Elevation Gain / Loss: ([\d.]+) m / ([\d.]+) m', detail)
        if elevation:
            fields.update(ascent_m=float(elevation[1]), descent_m=float(elevation[2]))
        lap_payload = unwrap(output['lap'])
        groups = lap_payload.get('lapGroups', [])
        if not groups:
            raise ValueError(f'No laps: {activity_id}')
        fields['max_hr'] = max((l.get('maxHr', 0) for g in groups for l in g.get('laps', [])), default=None)
        connection.execute('UPDATE activities SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE activity_id=?',
                           list(fields.values()) + [activity_id])
        connection.execute('DELETE FROM laps WHERE activity_id=?', (activity_id,))
        for group in groups:
            for lap in group.get('laps', []):
                distance = lap.get('distance', 0) / 100000.0
                row = dict(activity_id=activity_id, group_type=group['type'], lap_index=lap['lapIndex'],
                    distance_km=distance, duration_s=lap.get('time'), cumulative_s=lap.get('totalLength'),
                    pace_s_km=lap.get('avgPace') if distance > 0 else None,
                    avg_hr=lap.get('avgHr'), max_hr=lap.get('maxHr'), cadence=lap.get('avgCadence'),
                    stride_m=lap.get('avgStrideLength', 0) / 100.0,
                    ground_time_ms=lap.get('groundTime'), power_w=lap.get('avgPower'),
                    raw_json=json.dumps(lap, ensure_ascii=False))
                columns=list(row)
                connection.execute(f"INSERT INTO laps({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", list(row.values()))


def update_daily(connection, day, fields):
    put(connection, 'daily_metrics', dict(date_cn=day, source='COROS_MCP', **fields), 'date_cn')


def import_load(connection, payload):
    for block in re.split(r'\n\n(?=\d{4}-)', unwrap(payload))[1:]:
        day = re.match(r'(\d{4}-\d{2}-\d{2})', block)[1]
        update_daily(connection, day, dict(short_load=numeric(block, 'Short-Term Load'),
            long_load=numeric(block, 'Long-Term Load'), load_ratio=numeric(block, 'Load Ratio'),
            load_comment=text_field(block, 'Comment')))


def import_hrv(connection, payload):
    # Only use COROS official assessments; never average the raw time series.
    text = unwrap(payload).split('Sleep HRV Time Series')[0]
    for day, mean, status, low, high, baseline in re.findall(
        r'(\d{4}-\d{2}-\d{2}):\s+HRV Avg: ([\d.]+) ms — ([^\n]+)\s+Normal Range: ([\d.]+) - ([\d.]+) ms\s+Baseline: ([\d.]+) ms', text):
        update_daily(connection, day, dict(hrv_ms=float(mean), hrv_status=status,
            hrv_low=float(low), hrv_high=float(high), hrv_baseline=float(baseline)))


def import_fitness(connection, payload, day, snapshot_id):
    text = unwrap(payload)
    row=dict(snapshot_id=snapshot_id,date_cn=day,vo2max=numeric(text,'VO2max'),
        running_level=numeric(text,'Running Level'),source='COROS_MCP',notes='Watch estimates, not laboratory measurements')
    for label, field in [('Threshold Pace','threshold_pace_s_km'),('5 km Prediction','pred_5k_s'),
                         ('10 km Prediction','pred_10k_s'),('Half Marathon Prediction','pred_hm_s'),
                         ('Marathon Prediction','pred_marathon_s')]:
        value=text_field(text,label)
        row[field]=seconds(value.split(' /')[0]) if value else None
    put(connection,'fitness_snapshots',row,'snapshot_id')


def import_fit_index(connection):
    path = ROOT.parent / 'webgis_for_running/data/processed/activities.json'
    if not path.exists():
        return
    for item in json.loads(path.read_text(encoding='utf-8-sig')):
        start=item.get('start_time')
        day=item.get('date')
        confidence='unknown_timezone_retained_original'
        if start:
            parsed=dt.datetime.fromisoformat(start.replace('Z','+00:00'))
            if parsed.tzinfo:
                day=parsed.astimezone(CN).date().isoformat()
                confidence='explicit_offset_converted_Asia_Shanghai'
        def resolved(field):
            value=item.get(field)
            return str((path.parent/value).resolve()) if value else None
        put(connection,'fit_archive',dict(activity_id=str(item['id']),original_date=item.get('date'),
            date_cn=day,start_time=start,timezone_confidence=confidence,
            distance_km=item['distance_m']/1000 if item.get('distance_m') is not None else None,
            duration_s=item.get('timer_s'),
            pace_s_km=item.get('average_pace_s_per_km'),avg_hr=item.get('average_heart_rate'),
            max_hr=item.get('max_heart_rate'),parse_status=item.get('parse_status'),
            full_data_path=resolved('full_data_path'),track_path=resolved('track_path'),
            source_file=item.get('source_file'),summary_json=json.dumps(item,ensure_ascii=False)), 'activity_id')


def import_fit_observations(connection, payload):
    for observation in payload['observations']:
        item = observation['summary']
        put(connection, 'fit_observations', dict(
            activity_id=str(item['id']), date_cn=item['date'],start_time=item['start_time'],
            timezone_evidence=item.get('timezone_evidence'),sport=str(item.get('sport')),
            distance_km=item['distance_m']/1000 if item.get('distance_m') is not None else None,
            duration_s=item.get('timer_s'),pace_s_km=item.get('average_pace_s_per_km'),
            avg_hr=item.get('average_heart_rate'),max_hr=item.get('max_heart_rate'),
            source='LOCAL_FIT',source_file=observation['source_file'],source_sha256=observation['source_sha256'],
            include_formal=observation['include_formal'],exclusion_reason=observation.get('exclusion_reason'),
            raw_json=json.dumps(observation,ensure_ascii=False)), 'activity_id')


def import_journal(connection):
    data=json.loads((ROOT/'journal.json').read_text(encoding='utf-8'))
    for goal in data.get('goals',[]):
        put(connection,'goals',goal,'goal_id')
    for entry in data.get('entries',[]):
        row={k:entry.get(k) for k in ['entry_id','date_cn','kind','activity_id','source','status','title']}
        row['content_json']=json.dumps(entry['content'],ensure_ascii=False)
        put(connection,'journal',row,'entry_id')
    for row in data.get('fitness_snapshots',[]):
        put(connection,'fitness_snapshots',row,'snapshot_id')
    for row in data.get('threshold_snapshots',[]):
        put(connection,'threshold_snapshots',row,'snapshot_id')
    for row in data.get('calendar',[]):
        put(connection,'calendar_days',row,'date_cn')


def build(connection):
    paths=sorted((ROOT/'raw').glob('*.json'))
    with connection:
        put(connection,'metadata',dict(key='schema_version',value='2'),'key')
        put(connection,'metadata',dict(key='last_build_utc',value=now()),'key')
        # Records must exist before foreign-key-constrained details.
        for path in paths:
            if path.stem[11:].split('__',1)[0] in ('sport_records','race_records'):
                import_records(connection,json.loads(path.read_text(encoding='utf-8')),path)
        for path in paths:
            payload=json.loads(path.read_text(encoding='utf-8'))
            day=path.name[:10]
            kind=path.stem[11:].split('__',1)[0]
            if kind=='fit_observations': import_fit_observations(connection,payload)
            elif kind=='activity_details': import_details(connection,payload)
            elif kind=='load': import_load(connection,payload)
            elif kind=='sleep_hrv': import_hrv(connection,payload)
            elif kind=='resting_hr':
                for date, value in re.findall(r'(\d{4}-\d{2}-\d{2}): ([\d.]+) bpm',unwrap(payload)):
                    update_daily(connection,date,dict(resting_hr=float(value)))
            elif kind=='fitness': import_fitness(connection,payload,day,path.stem)
            elif kind=='recovery':
                text=unwrap(payload)
                hours=text_field(text,'Estimated Full Recovery')
                put(connection,'recovery_snapshots',dict(snapshot_id=path.stem,observed_date_cn=day,
                    recovery_pct=numeric(text,'Recovery'),full_recovery_hours=float(hours.rstrip('h')) if hours else None,
                    level=text_field(text,'Level'),source='COROS_MCP'),'snapshot_id')
            put(connection,'raw_snapshots',dict(snapshot_id=path.stem,observed_date_cn=day,kind=kind,
                path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                payload_json=json.dumps(payload,ensure_ascii=False)),'snapshot_id')
        import_fit_index(connection)
        import_journal(connection)
        day=dt.date(2026,7,1)
        last=max(connection.execute("SELECT max(date_cn) FROM daily_metrics").fetchone()[0] or '2026-09-14',
                 connection.execute("SELECT max(date_cn) FROM observed_training").fetchone()[0] or '2026-09-14',
                 '2026-09-14')
        end=dt.date.fromisoformat(last)
        while day<=end:
            key=day.isoformat()
            activity=connection.execute('SELECT 1 FROM observed_training WHERE date_cn=?',(key,)).fetchone()
            existing=connection.execute('SELECT status FROM calendar_days WHERE date_cn=?',(key,)).fetchone()
            if activity:
                put(connection,'calendar_days',dict(date_cn=key,status='training',source='COROS_MCP_OR_LOCAL_FIT',note='One or more formal running observations'),'date_cn')
            elif not existing:
                put(connection,'calendar_days',dict(date_cn=key,status='no_record',source='COROS_MCP',note='No running record; NOT confirmed rest or no other exercise'),'date_cn')
            day+=dt.timedelta(days=1)
    summary(connection,write=True)
    verify(connection)


def summary(connection,write=False):
    stats={t:connection.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ['activities','laps','fit_archive','fit_observations','journal','goals','daily_metrics','threshold_snapshots','raw_snapshots']}
    health_date=connection.execute('SELECT max(date_cn) FROM daily_metrics').fetchone()[0] or '未知'
    lines=['# 训练数据库摘要','','日期统一以Asia/Shanghai理解；FIT缺失时区记录保留不确定性。',
           '未执行计划不会算作完成；无跑步记录不等于休息。',
           f'COROS 与 FIT 按活动 ID 去重合并；FIT 原始观测单独保存。未知负荷显示 —，不当作零；排除 9/16 休闲跑及 10/2 骑车混入记录。健康指标截至 {health_date}。','',f'表记录数：{json.dumps(stats,ensure_ascii=False)}','',
           '## 周跑量（周一至周日，COROS＋明确时区 FIT，边界周可能不完整）','',
           '| 周一 | 跑步日 | 跑量km | 时间h | 已知负荷 |','|---|---:|---:|---:|---:|']
    for r in connection.execute('SELECT * FROM weekly_observed_training ORDER BY week_monday DESC'):
        load = fmt_value(r[5]) + (f'（另 {r[6]} 场未知）' if r[6] else '')
        lines.append(f'| {r[0]} | {r[2]} | {r[3]:.2f} | {r[4]:.2f} | {load} |')
    lines+=['','## 最近训练','', '| 日期 | 项目 | km | 配速 | 均HR | 负荷 | COROS重点 |','|---|---|---:|---:|---:|---:|---|']
    for r in connection.execute('SELECT * FROM observed_training ORDER BY date_cn DESC,activity_id DESC LIMIT 20'):
        lines.append(f"| {r['date_cn']} | {r['location_label']} | {r['distance_km']:.2f} | {fmt_pace(r['pace_s_km'])} | {fmt_value(r['avg_hr'])} | {fmt_value(r['training_load'])} | {r['coros_focus'] or r['source']} |")
    lines+=['','## 最新恢复/能力观测','']
    for table,order in [('fitness_snapshots','date_cn'),('daily_metrics','date_cn'),('recovery_snapshots','observed_date_cn')]:
        tie_order=', snapshot_id DESC' if table.endswith('_snapshots') else ''
        row=connection.execute(f'SELECT * FROM {table} ORDER BY {order} DESC{tie_order} LIMIT 1').fetchone()
        if row: lines.append(f'- {table}: {json.dumps(dict(row),ensure_ascii=False)}')
    text='\n'.join(lines)+'\n'
    if write:
        (ROOT/'SUMMARY.md').write_text(text,encoding='utf-8')
    else:
        print(text)


def verify(connection):
    integrity=connection.execute('PRAGMA integrity_check').fetchone()[0]
    foreign=list(connection.execute('PRAGMA foreign_key_check'))
    ids=connection.execute('SELECT count(*) FROM activities WHERE typeof(activity_id)!=\'text\'').fetchone()[0]
    missing=connection.execute('SELECT count(*) FROM activities a WHERE NOT EXISTS(SELECT 1 FROM laps l WHERE l.activity_id=a.activity_id)').fetchone()[0]
    fit_ids=connection.execute("SELECT count(*) FROM fit_observations WHERE typeof(activity_id)!='text'").fetchone()[0]
    invalid_formal=connection.execute("SELECT count(*) FROM fit_observations WHERE include_formal=1 AND (sport!='running' OR timezone_evidence IS NULL OR timezone_evidence NOT IN ('explicit_offset','fit_date_time_UTC'))").fetchone()[0]
    if integrity!='ok' or foreign or ids or missing or fit_ids or invalid_formal:
        raise RuntimeError(dict(integrity=integrity,foreign_keys=foreign,nontext_ids=ids,missing_laps=missing,fit_nontext_ids=fit_ids,invalid_formal_fit=invalid_formal))
    print(json.dumps(dict(integrity=integrity,foreign_keys='ok',activity_count=connection.execute('SELECT count(*) FROM activities').fetchone()[0],
        lap_count=connection.execute('SELECT count(*) FROM laps').fetchone()[0],missing_laps=missing,
        fit_observation_count=connection.execute('SELECT count(*) FROM fit_observations').fetchone()[0],formal_running_count=connection.execute('SELECT count(*) FROM observed_training').fetchone()[0]),ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','summary','verify','day','activity','backup'])
    parser.add_argument('value',nargs='?')
    args=parser.parse_args()
    if args.command!='build' and not DB.exists(): parser.error('Run build first')
    connection=sqlite3.connect(DB)
    connection.row_factory=sqlite3.Row
    if args.command!='backup':
        connection.executescript(SCHEMA)
    try:
        if args.command=='build': build(connection)
        elif args.command=='summary': summary(connection)
        elif args.command=='backup':
            directory=ROOT/'backups'
            directory.mkdir(exist_ok=True)
            path=directory/('training_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
            target=sqlite3.connect(path)
            try: connection.backup(target)
            finally: target.close()
            print(path)
        elif args.command=='verify': verify(connection)
        elif args.command=='day':
            if not args.value: parser.error('Provide YYYY-MM-DD')
            for table in ['calendar_days','activities','daily_metrics','journal']:
                rows=[dict(r) for r in connection.execute(f'SELECT * FROM {table} WHERE date_cn=?',(args.value,))]
                print(json.dumps({table:rows},ensure_ascii=False,indent=2))
        elif args.command=='activity':
            if not args.value: parser.error('Provide COROS labelId')
            row=connection.execute('SELECT * FROM activities WHERE activity_id=?',(args.value,)).fetchone()
            laps=[dict(r) for r in connection.execute('SELECT * FROM laps WHERE activity_id=? AND group_type=2 ORDER BY lap_index',(args.value,))]
            print(json.dumps(dict(activity=dict(row) if row else None,laps=laps),ensure_ascii=False,indent=2))
    finally:
        connection.close()


if __name__=='__main__':
    main()
