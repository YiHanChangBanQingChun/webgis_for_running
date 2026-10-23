import assert from 'node:assert/strict'
import test from 'node:test'
import {
  filterNearbyBuildings,
  prepareBuildings,
  prepareTrack,
  sampleTrack,
  simplifyForDisplay,
} from '../src/features/region/geometry.ts'
import type { BuildingCollection, TrackCollection } from '../src/features/region/types.ts'

function makeTrack(
  series: TrackCollection['features'][number]['properties']['series'] = {},
): TrackCollection {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [
            [113, 23],
            [113.01, 23],
          ],
        },
        properties: { series },
      },
    ],
  }
}

test('不均匀时间间隔：按记录时间插值，保留停顿，距离单位为米', () => {
  const track = prepareTrack(
    makeTrack({
      timestamp: ['2026-10-07T00:00:00Z', '2026-10-07T00:00:10Z'],
      distance: [20, 1020],
      heart_rate: [140, 160],
      enhanced_speed: [4, 3],
    }),
  )
  const point = sampleTrack(track, 5)
  assert.equal(track.durationSeconds, 10)
  assert.equal(track.distanceMeters, 1000)
  assert.equal(track.usedTimeFallback, false)
  assert.equal(point.distanceMeters, 500)
  assert.ok(Math.abs(point.longitude - 113.005) < 1e-8)
  assert.equal(point.paceSeconds, 250)
  assert.equal(point.heartRate, 140)
  assert.equal(sampleTrack(track, -10).distanceMeters, 0)
  assert.equal(sampleTrack(track, 100).distanceMeters, 1000)
})

test('缺少时间、距离和指标时采用明确的回退，不产生 NaN', () => {
  const track = prepareTrack(makeTrack())
  assert.equal(track.durationSeconds, 1)
  assert.equal(track.usedTimeFallback, true)
  assert.ok(track.distanceMeters > 1000 && track.distanceMeters < 1050)
  assert.equal(sampleTrack(track, 0.5).heartRate, null)
  assert.equal(sampleTrack(track, 0.5).paceSeconds, null)
})

test('倒退的累计距离和时间戳不会让回放倒走', () => {
  const track = prepareTrack(
    makeTrack({
      timestamp: ['2026-10-07T00:00:10Z', '2026-10-07T00:00:00Z'],
      distance: [100, 0],
    }),
  )
  assert.equal(track.usedTimeFallback, true)
  assert.equal(track.durationSeconds, 1)
  assert.ok(track.distanceMeters > 1000)
})

test('拒绝没有线或有效坐标不足的轨迹', () => {
  assert.throws(() => prepareTrack({ type: 'FeatureCollection', features: [] }), /LineString/)
  const data = makeTrack()
  data.features[0]!.geometry.coordinates = [
    [NaN, 23],
    [113, 23],
  ]
  assert.throws(() => prepareTrack(data), /两个有效坐标/)
})

function makeBuildings(): BuildingCollection {
  return {
    type: 'FeatureCollection',
    features: [0.0005, 0.003].map((offset, index) => ({
      type: 'Feature',
      properties: { name: `楼 ${index}`, height_m: index ? null : 60 },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [113.0049, 23 + offset],
            [113.0051, 23 + offset],
            [113.005, 23.0001 + offset],
            [113.0049, 23 + offset],
          ],
        ],
      },
    })),
  }
}

test('建筑按线段距离筛选：即使两个 GPS 点都很远，位于中间的建筑仍可命中', () => {
  const track = prepareTrack(makeTrack())
  const buildings = prepareBuildings(makeBuildings())
  const nearby = filterNearbyBuildings(buildings, track, 100)
  assert.equal(nearby.length, 1)
  assert.equal(nearby[0]!.feature.properties.name, '楼 0')
  assert.equal(filterNearbyBuildings(buildings, track, 500).length, 2)
  assert.equal(filterNearbyBuildings(buildings, track, 10).length, 0)
})

test('支持 MultiPolygon，楼高缺失回退 10 米且不改写源数据', () => {
  const data = makeBuildings()
  const first = data.features[0]!
  if (first.geometry.type !== 'Polygon') throw new Error('测试数据错误')
  first.geometry = { type: 'MultiPolygon', coordinates: [first.geometry.coordinates] }
  const snapshot = JSON.stringify(data)
  const buildings = prepareBuildings(data)
  assert.equal(buildings.length, 2)
  assert.equal(buildings[1]!.height, 10)
  assert.equal(JSON.stringify(data), snapshot)
})

test('绘图抽样始终保留首尾；原始轨迹不会被修改', () => {
  const point = prepareTrack(makeTrack()).points[0]!
  const points = Array.from({ length: 10000 }, (_, index) => ({ ...point, distanceMeters: index }))
  const sampled = simplifyForDisplay(points, 160)
  assert.ok(sampled.length <= 160)
  assert.equal(sampled[0]!.distanceMeters, 0)
  assert.equal(sampled.at(-1)!.distanceMeters, 9999)
  assert.equal(points.length, 10000)
})
