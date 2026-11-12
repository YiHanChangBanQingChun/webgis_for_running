// Pure queries for the small, explicitly published dataset. No private history is loaded.
export interface PublicActivity {
  id: string
  date: string | null
  start_time: string | null
  sport: string | number | null
  distance_m: number | null
  elapsed_s: number | null
  average_heart_rate: number | null
  total_ascent_m?: number | null
  calories?: number | null
  has_gps: boolean
  training_excluded?: boolean
}
export interface PublishedRange {
  start: string
  end: string
}
export interface SpatialGrid {
  cell_size_m: number
  cells: Array<{
    cell_id: string
    longitude: number
    latitude: number
    activities: Array<{ id: string; date: string; distance_m: number }>
  }>
}
const round = (value: number) => Math.round(value * 100) / 100
const sum = (
  rows: PublicActivity[],
  field: 'distance_m' | 'elapsed_s' | 'total_ascent_m' | 'calories',
) => rows.reduce((total, row) => total + (row[field] || 0), 0)
export function shiftDate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
export function queryActivities(source: PublicActivity[], query: URLSearchParams) {
  let rows = source.filter(
    (a) =>
      (!query.get('start') || (a.date != null && a.date >= query.get('start')!)) &&
      (!query.get('end') || (a.date != null && a.date <= query.get('end')!)) &&
      (!query.get('sport') || String(a.sport) === query.get('sport')) &&
      (!query.has('has_gps') || a.has_gps === (query.get('has_gps') === 'true')) &&
      (!query.has('min_distance_km') ||
        (a.distance_m || 0) >= Number(query.get('min_distance_km')) * 1000) &&
      (!query.has('max_distance_km') ||
        (a.distance_m || 0) <= Number(query.get('max_distance_km')) * 1000),
  )
  const sort = query.get('sort') || 'date_desc'
  rows = [...rows].sort((a, b) => {
    const comparison = sort.startsWith('distance')
      ? (a.distance_m || 0) - (b.distance_m || 0)
      : (a.start_time || a.date || '').localeCompare(b.start_time || b.date || '')
    return sort.endsWith('desc') ? -comparison : comparison
  })
  const offset = Math.max(0, Number(query.get('offset') || 0))
  const limit = Math.max(1, Number(query.get('limit') || 100))
  return { total: rows.length, items: rows.slice(offset, offset + limit) }
}
export function monthlyStats(source: PublicActivity[], month: string) {
  const rows = source.filter((a) => a.date?.startsWith(month) && !a.training_excluded)
  const distance = sum(rows, 'distance_m'),
    elapsed = sum(rows, 'elapsed_s')
  const days = new Set(rows.map((a) => a.date)).size
  return {
    month,
    activity_count: rows.length,
    active_days: days,
    total_distance_m: round(distance),
    total_elapsed_s: round(elapsed),
    average_distance_m: days ? round(distance / days) : null,
    average_pace_s_per_km: distance ? round((elapsed / distance) * 1000) : null,
    total_ascent_m: round(sum(rows, 'total_ascent_m')),
    activities_with_gps: rows.filter((a) => a.has_gps).length,
  }
}
export function rangeStats(
  source: PublicActivity[],
  start: string,
  end: string,
  coverage: PublishedRange[],
) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(start) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(end) ||
    !Number.isFinite(Date.parse(start)) ||
    !Number.isFinite(Date.parse(end)) ||
    start > end ||
    (Date.parse(end) - Date.parse(start)) / 86400000 > 1095
  )
    throw new Error('请选择有效的三年以内日期范围。')
  const running = source.filter((a) => a.sport === 'running' && !a.training_excluded)
  const knownDate = (day: string) => coverage.some((r) => r.start <= day && day <= r.end)
  const daily = []
  for (let day = start; day <= end; day = shiftDate(day, 1)) {
    const rows = running.filter((a) => a.date === day)
    const window = running.filter((a) => a.date && a.date >= shiftDate(day, -27) && a.date <= day)
    const load = (a: PublicActivity) =>
      a.average_heart_rate ? ((a.elapsed_s || 0) / 60) * (a.average_heart_rate / 150) ** 2 : null
    const dayLoad = rows.every((a) => load(a) != null)
      ? round(rows.reduce((s, a) => s + load(a)!, 0))
      : null
    const complete = (days: number) =>
      Array.from({ length: days }, (_, i) => shiftDate(day, -i)).every(knownDate) &&
      window.filter((a) => a.date! >= shiftDate(day, -(days - 1))).every((a) => load(a) != null)
    const totalLoad = (days: number) =>
      round(
        window
          .filter((a) => a.date! >= shiftDate(day, -(days - 1)))
          .reduce((s, a) => s + (load(a) || 0), 0),
      )
    const load7 = complete(7) ? totalLoad(7) : null
    const load28 = complete(28) ? totalLoad(28) : null
    daily.push({
      date: day,
      activity_count: rows.length,
      distance_m: round(sum(rows, 'distance_m')),
      elapsed_s: round(sum(rows, 'elapsed_s')),
      relative_load: rows.length || knownDate(day) ? dayLoad : null,
      load_7d: load7,
      load_28d: load28,
      load_ratio: load7 != null && load28 ? round(load7 / (load28 / 4)) : null,
    })
  }
  const weekly = new Map<
    string,
    {
      week: string
      activity_count: number
      distance_m: number
      elapsed_s: number
      relative_load: number
    }
  >()
  for (const point of daily) {
    const weekday = (new Date(`${point.date}T00:00:00Z`).getUTCDay() + 6) % 7
    const key = shiftDate(point.date, -weekday)
    const bucket = weekly.get(key) || {
      week: key,
      activity_count: 0,
      distance_m: 0,
      elapsed_s: 0,
      relative_load: 0,
    }
    bucket.activity_count += point.activity_count
    bucket.distance_m += point.distance_m
    bucket.elapsed_s += point.elapsed_s
    bucket.relative_load += point.relative_load || 0
    weekly.set(key, bucket)
  }
  const rows = running.filter((a) => a.date && start <= a.date && a.date <= end)
  const distance = sum(rows, 'distance_m'),
    elapsed = sum(rows, 'elapsed_s'),
    days = new Set(rows.map((a) => a.date)).size
  return {
    start,
    end,
    summary: {
      activity_count: rows.length,
      active_days: days,
      total_distance_m: round(distance),
      total_elapsed_s: round(elapsed),
      total_ascent_m: round(sum(rows, 'total_ascent_m')),
      calories: round(sum(rows, 'calories')),
      average_pace_s_per_km: distance ? round((elapsed / distance) * 1000) : null,
      average_distance_m: days ? round(distance / days) : null,
      load_ratio: null,
      load_status: 'insufficient',
    },
    daily,
    weekly: [...weekly.values()],
    load_note:
      '仅统计公开的正式跑步。相对负荷按时长与平均心率计算，并非 COROS 官方负荷。连续样本仅两周，28 日基线与负荷比留空；未公开日期不按零负荷或休息处理。',
  }
}
export function heatGrid(grid: SpatialGrid, query: URLSearchParams) {
  const features = grid.cells.flatMap((cell) => {
    const rows = cell.activities.filter(
      (a) =>
        (!query.get('start') || a.date >= query.get('start')!) &&
        (!query.get('end') || a.date <= query.get('end')!),
    )
    if (rows.length < Number(query.get('min_visits') || 1)) return []
    return [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [cell.longitude, cell.latitude] },
        properties: {
          cell_id: cell.cell_id,
          visits: rows.length,
          distance_m: round(rows.reduce((s, a) => s + a.distance_m, 0)),
          first_date: rows.map((a) => a.date).sort()[0],
          last_date: rows
            .map((a) => a.date)
            .sort()
            .at(-1),
        },
      },
    ]
  })
  return {
    type: 'FeatureCollection',
    cell_size_m: grid.cell_size_m,
    feature_count: features.length,
    features,
  }
}
