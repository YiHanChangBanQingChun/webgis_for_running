#!/usr/bin/env python3
"""生成迁移演示数据：合成活动/轨迹 + 少量已有建筑；不读取个人活动。"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER = 'running-webgis-synthetic-migration-demo-v1'


def points(value):
    if isinstance(value, list) and len(value) >= 2 and all(isinstance(n, (int, float)) for n in value[:2]):
        yield value[:2]
    elif isinstance(value, list):
        for part in value:
            yield from points(part)


def center(feature):
    xy = list(points(feature.get('geometry', {}).get('coordinates', [])))
    if not xy:
        return None
    return ((min(p[0] for p in xy) + max(p[0] for p in xy)) / 2,
            (min(p[1] for p in xy) + max(p[1] for p in xy)) / 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent/'sample')
    parser.add_argument('--force', action='store_true', help='仅重写本工具已生成的演示目录')
    args = parser.parse_args()
    target = args.output.resolve()
    marker = target/'sample-manifest.json'
    if target.exists():
        if not args.force or not marker.is_file() or json.loads(marker.read_text()).get('generated_by') != MARKER:
            raise SystemExit('输出目录已存在，已保留。仅对本工具的既有演示目录使用 --force。')

    source = ROOT/'frontend/public/cesium-data/guangzhou-buildings.geojson'
    collection = json.loads(source.read_text())
    usable = [(feature, center(feature)) for feature in collection['features']
              if feature.get('geometry', {}).get('type') in ['Polygon', 'MultiPolygon']]
    usable = [(f, c) for f, c in usable if c is not None]
    if not usable:
        raise SystemExit('源建筑数据中没有可用面要素')
    lon, lat = usable[0][1]
    usable.sort(key=lambda fc: (fc[1][0]-lon)**2*math.cos(math.radians(lat))**2+(fc[1][1]-lat)**2)
    buildings = {'type': 'FeatureCollection', 'features': [f for f, _ in usable[:200]]}

    activities, tracks, grouped = [], {}, defaultdict(list)
    for day in range(5):
        activity_id = f'demo-{day+1:03d}'
        start = datetime(2026, 11, 1, 7, tzinfo=timezone(timedelta(hours=8))) + timedelta(days=day)
        n, duration, distance = 241, 1200+day*120, 3000+day*300
        coordinates = [[round(lon+0.0025*math.cos(i/(n-1)*2*math.pi), 7),
                        round(lat+0.0025*math.sin(i/(n-1)*2*math.pi), 7)] for i in range(n)]
        series = {
            'timestamp': [(start+timedelta(seconds=i*duration/(n-1))).isoformat() for i in range(n)],
            'distance': [round(i*distance/(n-1), 2) for i in range(n)],
            'heart_rate': [145+i%12 for i in range(n)],
            'enhanced_speed': [round(distance/duration, 3)]*n,
            'speed': [round(distance/duration, 3)]*n,
            'altitude': [10]*n, 'enhanced_altitude': [10]*n,
            'cadence': [170]*n, 'power': [220]*n,
        }
        row = dict(id=activity_id, date=start.date().isoformat(), start_time=start.isoformat(),
                   sport='running', sub_sport='generic', distance_m=distance, elapsed_s=duration,
                   timer_s=duration, calories=200+day*20, average_heart_rate=150, max_heart_rate=160,
                   average_speed_mps=distance/duration, average_pace_s_per_km=duration/distance*1000,
                   total_ascent_m=10, total_descent_m=10, record_count=n, has_gps=True,
                   include_in_running_stats=True, training_excluded=False,
                   parse_status='synthetic_demo', source_file='synthetic-demo-not-a-fit-file')
        activities.append(row)
        grouped[row['date']].append(row)
        tracks[activity_id] = {'type': 'FeatureCollection', 'features': [{
            'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': coordinates},
            'properties': {'activity_id': activity_id, 'date': row['date'], 'sport': 'running',
                           'series': series, 'synthetic_demo': True}}]}
    calendar = [dict(date=day, activity_count=len(rows), distance_m=sum(r['distance_m'] for r in rows),
                     elapsed_s=sum(r['elapsed_s'] for r in rows), calories=sum(r['calories'] for r in rows),
                     activity_ids=[r['id'] for r in rows]) for day, rows in sorted(grouped.items())]
    report = {'schema_version': 1, 'source': 'synthetic demonstration, not real training data',
              'readiness': {'api_ready': True},
              'data_coverage': {'activities_with_gps': 5,
                                'date_range': {'start': activities[0]['date'], 'end': activities[-1]['date']}}}
    grid = {'cell_size_m': 250, 'track_count': 5, 'cell_count': 1,
            'cells': [{'cell_id': 'demo-cell', 'longitude': lon, 'latitude': lat,
                       'activities': [{'id': r['id'], 'date': r['date'], 'distance_m': r['distance_m']}
                                      for r in activities]}]}
    outputs = {'processed/activities.json': activities, 'processed/calendar.json': calendar,
               'processed/import-report.json': report, 'processed/spatial-grid.json': grid,
               'processed/athlete-profile.json': {'source': 'synthetic-demo', 'running_fitness': {}},
               'cesium-data/guangzhou-buildings.geojson': buildings,
               'sample-manifest.json': {'generated_by': MARKER, 'activities': 5,
                                        'buildings': len(buildings['features']),
                                        'notice': '活动和圆形轨迹全部合成，不对应个人真实运动。建筑从本项目既有 GeoJSON 文件抽取；本工具不判断其授权。'}}
    outputs.update({f'processed/tracks/{key}.geojson': value for key, value in tracks.items()})
    for relative, value in outputs.items():
        path = target/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n')
    size = sum((target/name).stat().st_size for name in outputs)
    print(f'已生成演示数据：5 个合成活动、{len(buildings["features"])} 个建筑，约 {size/1024:.1f} KiB')
    print('输出：', target)


if __name__ == '__main__':
    main()
