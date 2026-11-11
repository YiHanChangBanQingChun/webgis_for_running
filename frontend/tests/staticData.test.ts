import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { heatGrid, monthlyStats, queryActivities, rangeStats } from '../src/staticData.ts'
import type { PublicActivity, SpatialGrid } from '../src/staticData.ts'

const root = new URL('../public-demo/', import.meta.url)
const read = (path: string) => JSON.parse(readFileSync(new URL(path, root), 'utf8'))
const manifest = read('manifest.json')
const activities: PublicActivity[] = read('data/activities.json')
const grid: SpatialGrid = read('data/spatial-grid.json')

test('published dataset contains exactly the authorized interval and two races', () => {
  assert.equal(activities.length, 17)
  assert.equal(new Set(activities.map((a) => a.id)).size, 17)
  assert.equal(
    activities.filter((a) => a.date! >= '2026-09-01' && a.date! <= '2026-09-14').length,
    15,
  )
  assert.deepEqual(
    activities
      .filter((a) => a.date! > '2026-09-14')
      .map((a) => a.date)
      .sort(),
    ['2026-11-01', '2026-11-08'],
  )
  assert.equal(manifest.default_month, '2026-09')
  assert.deepEqual(manifest.default_range, { start: '2026-09-01', end: '2026-09-14' })
  assert.equal(read('data/guangzhou-buildings.geojson').features.length, 1907)
})
test('activity filters, distance sorting and pagination operate in the browser', () => {
  const result = queryActivities(
    activities,
    new URLSearchParams(
      'start=2026-11-01&end=2026-11-08&has_gps=true&min_distance_km=20&sort=distance_desc&limit=1&offset=1',
    ),
  )
  assert.equal(result.total, 2)
  assert.equal(result.items.length, 1)
  assert.equal(result.items[0]!.date, '2026-11-08')
  assert.equal(queryActivities(activities, new URLSearchParams('sport=cycling')).total, 0)
  assert.equal(monthlyStats(activities, '2026-09').activity_count, 15)
  assert.equal(monthlyStats(activities, '2026-11').activity_count, 2)
  assert.equal(monthlyStats(activities, '2026-10').activity_count, 0)
})
test('two-week load curves never invent a 28-day baseline or turn unpublished gaps into zero load', () => {
  const result = rangeStats(activities, '2026-09-01', '2026-09-14', manifest.continuous_ranges)
  assert.equal(result.daily.length, 14)
  assert.equal(result.summary.activity_count, 15)
  assert(result.daily.slice(0, 6).every((p) => p.load_7d === null))
  assert(result.daily.slice(6).some((p) => p.load_7d != null && p.load_7d > 0))
  assert(result.daily.every((p) => p.load_28d === null && p.load_ratio === null))
  const gap = rangeStats(activities, '2026-11-07', '2026-11-08', manifest.continuous_ranges)
  assert.equal(gap.daily[0]!.relative_load, null)
  assert.equal(gap.daily[1]!.load_7d, null)
  assert.equal(gap.summary.load_ratio, null)
  assert.throws(() => rangeStats(activities, '2026-11-08', '2026-09-01', []))
})
test('heat grid supports date/visit filters and contains only published activities', () => {
  const ids = new Set(manifest.activity_ids)
  assert(grid.cells.every((c) => c.activities.every((a) => ids.has(a.id))))
  const repeated = heatGrid(
    grid,
    new URLSearchParams('start=2026-09-01&end=2026-09-14&min_visits=3'),
  )
  assert(repeated.features.length > 0)
  assert(
    repeated.features.every(
      (f) => f.properties.visits >= 3 && f.properties.last_date! <= '2026-09-14',
    ),
  )
  assert.equal(
    heatGrid(grid, new URLSearchParams('start=2026-10-01&end=2026-10-31')).feature_count,
    0,
  )
})
test('all published tracks preserve GPS/sensor alignment and exclude local source and health metadata', () => {
  const ids = new Set(manifest.activity_ids)
  const trackDir = fileURLToPath(new URL('data/tracks/', root))
  assert.equal(readdirSync(trackDir).length, 17)
  for (const name of readdirSync(trackDir)) {
    assert(ids.has(name.replace('.geojson', '')))
    const feature = read(`data/tracks/${name}`).features[0]
    assert(feature.geometry.coordinates.length > 100)
    for (const values of Object.values(feature.properties.series))
      assert.equal((values as unknown[]).length, feature.geometry.coordinates.length)
    assert(feature.properties.series.timestamp.every((t: string) => /Z$|[+-]\d\d:\d\d$/.test(t)))
  }
  const serialized = JSON.stringify({
    activities,
    manifest,
    report: read('data/quality-report.json'),
    profile: read('data/athlete-profile.json'),
  })
  assert(
    !/\/Users\/|source_file|source_directory|birthday|hrv|resting_hr|perceived_effort/.test(
      serialized,
    ),
  )
})
