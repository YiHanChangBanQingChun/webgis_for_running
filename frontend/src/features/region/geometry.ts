// 区域探索的纯数据处理函数：不依赖 Vue 或 Cesium，便于单独测试和复用。
import type {
  BuildingCollection,
  BuildingRecord,
  PreparedTrack,
  RoutePoint,
  TrackCollection,
} from './types'

const EARTH_RADIUS = 6_371_008.8
const RADIANS = Math.PI / 180

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function distanceMeters(a: RoutePoint, b: RoutePoint): number {
  // 使用 Haversine 公式计算两经纬度点之间的球面距离。
  const deltaLatitude = (b.latitude - a.latitude) * RADIANS
  const deltaLongitude = (b.longitude - a.longitude) * RADIANS
  const h =
    Math.sin(deltaLatitude / 2) ** 2 +
    Math.cos(a.latitude * RADIANS) *
      Math.cos(b.latitude * RADIANS) *
      Math.sin(deltaLongitude / 2) ** 2
  return 2 * EARTH_RADIUS * Math.asin(Math.sqrt(Math.min(1, h)))
}

/**
 * 将 GeoJSON 坐标与同索引的采样数组合并，给动画提供统一的时间、距离和指标。
 * 不采用设备海拔：建筑与路线统一放在椭球面附近，避免未经校正的海拔使路线悬空。
 */
export function prepareTrack(collection: TrackCollection): PreparedTrack {
  // 将 GeoJSON 轨迹整理为带有连续时间、距离和运动指标的标准点数组。
  const feature = collection.features.find((item) => item.geometry?.type === 'LineString')
  if (!feature) throw new Error('轨迹中没有 LineString。')

  const series = feature.properties?.series ?? {}
  const points: RoutePoint[] = []
  let previousTimestamp: number | null = null
  let previousDistance: number | null = null
  let usedTimeFallback = false

  for (const [index, coordinate] of feature.geometry.coordinates.entries()) {
    const [longitude, latitude] = coordinate
    if (
      !finite(longitude) ||
      !finite(latitude) ||
      Math.abs(longitude) > 180 ||
      Math.abs(latitude) > 90
    ) {
      continue
    }

    const timestamp = Date.parse(series.timestamp?.[index] ?? '')
    const rawDistance = series.distance?.[index]
    const speed = series.enhanced_speed?.[index] ?? series.speed?.[index]
    const heartRate = series.heart_rate?.[index]
    const previous = points.at(-1)
    const point: RoutePoint = {
      longitude,
      latitude,
      elapsedSeconds: 0,
      distanceMeters: 0,
      heartRate: finite(heartRate) && heartRate > 0 ? heartRate : null,
      paceSeconds: finite(speed) && speed > 0.25 ? 1000 / speed : null,
    }

    if (previous) {
      const delta = previousTimestamp == null ? NaN : (timestamp - previousTimestamp) / 1000
      // 缺失或倒退的时间戳按 1 秒/点回退，并在界面说明，不能伪称为真实时间。
      const validTime = Number.isFinite(delta) && delta > 0
      usedTimeFallback ||= !validTime
      point.elapsedSeconds = previous.elapsedSeconds + (validTime ? delta : 1)
      const distanceDelta =
        finite(rawDistance) && previousDistance != null ? rawDistance - previousDistance : NaN
      point.distanceMeters =
        previous.distanceMeters +
        (Number.isFinite(distanceDelta) && distanceDelta >= 0
          ? distanceDelta
          : distanceMeters(previous, point))
    }

    points.push(point)
    previousTimestamp = Number.isFinite(timestamp) ? timestamp : null
    previousDistance = finite(rawDistance) ? rawDistance : null
  }

  if (points.length < 2) throw new Error('轨迹至少需要两个有效坐标。')
  const last = points.at(-1)!
  return {
    points,
    durationSeconds: last.elapsedSeconds,
    distanceMeters: last.distanceMeters,
    usedTimeFallback,
  }
}

/** 二分查找当前时刻，再在相邻点间插值；GPS 采样不均匀时也能平滑回放。 */
export function sampleTrack(track: PreparedTrack, seconds: number): RoutePoint {
  // 找到当前时间所在的两个采样点，并在它们之间做线性插值。
  const { points } = track
  const time = Math.max(0, Math.min(seconds, track.durationSeconds))
  let low = 0
  let high = points.length - 1

  while (low < high) {
    const middle = Math.ceil((low + high) / 2)
    if (points[middle]!.elapsedSeconds <= time) low = middle
    else high = middle - 1
  }

  const start = points[low]!
  const end = points[Math.min(low + 1, points.length - 1)]!
  const duration = end.elapsedSeconds - start.elapsedSeconds
  const ratio = duration > 0 ? (time - start.elapsedSeconds) / duration : 0
  return {
    ...start,
    elapsedSeconds: time,
    longitude: start.longitude + (end.longitude - start.longitude) * ratio,
    latitude: start.latitude + (end.latitude - start.latitude) * ratio,
    distanceMeters: start.distanceMeters + (end.distanceMeters - start.distanceMeters) * ratio,
  }
}

/** 保留首尾点的绘图抽样；空间筛选与回放仍使用完整轨迹。 */
export function simplifyForDisplay(points: RoutePoint[], limit = 1200): RoutePoint[] {
  const step = Math.max(1, Math.ceil((points.length - 1) / (limit - 1)))
  return points.filter((_, index) => index % step === 0 || index === points.length - 1)
}

export function prepareBuildings(collection: BuildingCollection): BuildingRecord[] {
  // 从建筑 GeoJSON 提取包围盒中心和可用高度，供附近筛选和三维挤出使用。
  return collection.features.flatMap((feature) => {
    if (!['Polygon', 'MultiPolygon'].includes(feature.geometry?.type)) return []
    const polygons =
      feature.geometry.type === 'Polygon'
        ? [feature.geometry.coordinates]
        : feature.geometry.coordinates
    const coordinates = polygons.flatMap((polygon) => polygon[0] ?? [])
    if (!coordinates.length) return []

    const longitudes = coordinates.map((point) => point[0]!).filter(finite)
    const latitudes = coordinates.map((point) => point[1]!).filter(finite)
    if (!longitudes.length || !latitudes.length) return []
    const rawHeight = feature.properties?.height_m
    return [
      {
        feature,
        longitude: (Math.min(...longitudes) + Math.max(...longitudes)) / 2,
        latitude: (Math.min(...latitudes) + Math.max(...latitudes)) / 2,
        height: finite(rawHeight) && rawHeight > 0 ? rawHeight : 10,
      },
    ]
  })
}

interface Point2D {
  x: number
  y: number
}

function distanceToSegment(point: Point2D, start: Point2D, end: Point2D): number {
  const dx = end.x - start.x
  const dy = end.y - start.y
  const squaredLength = dx * dx + dy * dy
  const ratio = squaredLength
    ? Math.max(
        0,
        Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / squaredLength),
      )
    : 0
  return Math.hypot(point.x - start.x - ratio * dx, point.y - start.y - ratio * dy)
}

/**
 * 广州市域的小范围近似：经纬度投影为米，再计算建筑包围盒中心到轨迹线段的距离。
 * 网格索引只缩小候选集合，不抽样轨迹；这不是建筑轮廓与道路的精确缓冲区分析。
 */
export function filterNearbyBuildings(
  buildings: BuildingRecord[],
  track: PreparedTrack,
  radius: number,
): BuildingRecord[] {
  // 先按网格建立候选线段索引，再进行精确的点到线段距离判断。
  const origin = track.points[0]!
  const scaleX = EARTH_RADIUS * RADIANS * Math.cos(origin.latitude * RADIANS)
  const scaleY = EARTH_RADIUS * RADIANS
  const project = (point: { longitude: number; latitude: number }): Point2D => ({
    x: (point.longitude - origin.longitude) * scaleX,
    y: (point.latitude - origin.latitude) * scaleY,
  })
  const points = track.points.map(project)
  const cellSize = 1000
  const grid = new Map<string, number[]>()
  const longSegments: number[] = []

  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1]!
    const end = points[index]!
    const minX = Math.floor((Math.min(start.x, end.x) - radius) / cellSize)
    const maxX = Math.floor((Math.max(start.x, end.x) + radius) / cellSize)
    const minY = Math.floor((Math.min(start.y, end.y) - radius) / cellSize)
    const maxY = Math.floor((Math.max(start.y, end.y) + radius) / cellSize)
    // 异常 GPS 跨越很远时，不展开成大量网格，改为逐个候选检查该线段。
    if ((maxX - minX + 1) * (maxY - minY + 1) > 100) {
      longSegments.push(index)
      continue
    }
    for (let x = minX; x <= maxX; x += 1) {
      for (let y = minY; y <= maxY; y += 1) {
        const key = `${x},${y}`
        const entries = grid.get(key) ?? []
        entries.push(index)
        grid.set(key, entries)
      }
    }
  }

  return buildings.filter((building) => {
    const point = project(building)
    const key = `${Math.floor(point.x / cellSize)},${Math.floor(point.y / cellSize)}`
    const candidates = [...(grid.get(key) ?? []), ...longSegments]
    return candidates.some(
      (index) => distanceToSegment(point, points[index - 1]!, points[index]!) <= radius,
    )
  })
}
