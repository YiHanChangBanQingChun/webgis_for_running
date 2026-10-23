// 区域探索共享类型：明确接口数据、轨迹点、建筑和图例的结构。
/** 只声明区域探索实际使用的字段；与现有活动、轨迹接口保持一致。 */
export interface RunningActivity {
  id: string
  date: string | null
  distance_m: number | null
  elapsed_s: number | null
  training_excluded?: boolean
}

export interface TrackSeries {
  // 各数组按采样点下标对应，缺失值使用 null 或 undefined 表示。
  timestamp?: Array<string | null>
  distance?: Array<number | null>
  heart_rate?: Array<number | null>
  enhanced_speed?: Array<number | null>
  speed?: Array<number | null>
}

export type TrackCollection = GeoJSON.FeatureCollection<
  GeoJSON.LineString,
  { series?: TrackSeries }
>

export interface RoutePoint {
  longitude: number
  latitude: number
  elapsedSeconds: number
  distanceMeters: number
  heartRate: number | null
  paceSeconds: number | null
}

export interface PreparedTrack {
  points: RoutePoint[]
  durationSeconds: number
  distanceMeters: number
  usedTimeFallback: boolean
}

export interface BuildingProperties {
  name?: string | null
  height_m?: number | null
  osm_id?: string | null
}

export type BuildingFeature = GeoJSON.Feature<
  GeoJSON.Polygon | GeoJSON.MultiPolygon,
  BuildingProperties
>

export type BuildingCollection = GeoJSON.FeatureCollection<
  GeoJSON.Polygon | GeoJSON.MultiPolygon,
  BuildingProperties
>

export interface BuildingRecord {
  feature: BuildingFeature
  longitude: number
  latitude: number
  height: number
}

export interface BuildingSelection {
  name: string
  height: number
}

export type RouteColorMode = 'pace' | 'heartRate' | 'plain'

// 图例颜色与轨迹分段规则共用同一份配置。
export const ROUTE_LEGENDS: Record<RouteColorMode, Array<{ label: string; color: string }>> = {
  pace: [
    { label: '< 4′30″', color: '#ff7870' },
    { label: '4′30″–6′00″', color: '#ffc66d' },
    { label: '≥ 6′00″', color: '#58dec5' },
    { label: '无有效配速', color: '#a2adbf' },
  ],
  heartRate: [
    { label: '< 145 bpm', color: '#58dec5' },
    { label: '145–169 bpm', color: '#ffc66d' },
    { label: '≥ 170 bpm', color: '#ff7870' },
    { label: '无心率', color: '#a2adbf' },
  ],
  plain: [{ label: '跑步轨迹', color: '#58dec5' }],
}
