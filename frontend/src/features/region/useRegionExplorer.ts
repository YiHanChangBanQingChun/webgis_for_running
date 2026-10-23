import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import type { Ref } from 'vue'
import { fetchAllActivities } from '../../activityApi'
import { filterNearbyBuildings, prepareBuildings, prepareTrack, sampleTrack } from './geometry'
import { RegionScene } from './RegionScene'
import { ROUTE_LEGENDS } from './types'
import type {
  BuildingCollection,
  BuildingRecord,
  BuildingSelection,
  PreparedTrack,
  RouteColorMode,
  RunningActivity,
  TrackCollection,
} from './types'

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function formatPace(seconds: number | null): string {
  if (seconds == null) return '—'
  const rounded = Math.round(seconds)
  return `${Math.floor(rounded / 60)}′${String(rounded % 60).padStart(2, '0')}″ /km`
}

/**
 * 数据流：活动列表 → 轨迹标准化 → 附近建筑筛选 → RegionScene → Vue 控件。
 * 使用 shallowRef 保存只读的大数组，避免为数千个坐标创建深层响应式代理。
 */
export function useRegionExplorer(container: Ref<HTMLDivElement | undefined>) {
  const activities = shallowRef<RunningActivity[]>([])
  const track = shallowRef<PreparedTrack | null>(null)
  const nearbyBuildings = shallowRef<BuildingRecord[]>([])
  const selectedActivityId = ref('')
  const selectedBuilding = ref<BuildingSelection | null>(null)
  const radius = ref(500)
  const heightScale = ref(1)
  const showBuildings = ref(true)
  const onlineBasemap = ref(false)
  const colorMode = ref<RouteColorMode>('pace')
  const elapsed = ref(0)
  const speed = ref(30)
  const playing = ref(false)
  const following = ref(false)
  const loadingActivities = ref(false)
  const loadingTrack = ref(false)
  const loadingBuildings = ref(false)
  const sceneError = ref('')
  const activityError = ref('')
  const trackError = ref('')
  const buildingError = ref('')
  const basemapError = ref('')
  const totalBuildings = ref(0)

  let scene: RegionScene | undefined
  let allBuildings: BuildingRecord[] = []
  let disposed = false
  let animationFrame = 0
  let previousFrame = 0
  let corridorVersion = 0
  let trackRequest: AbortController | undefined
  const lifetime = new AbortController()

  const currentPoint = computed(() =>
    track.value ? sampleTrack(track.value, elapsed.value) : null,
  )
  const selectedActivity = computed(() =>
    activities.value.find((item) => item.id === selectedActivityId.value),
  )
  const legend = computed(() => ROUTE_LEGENDS[colorMode.value])
  const buildingStats = computed(() => {
    const heights = nearbyBuildings.value.map((building) => building.height)
    return {
      count: heights.length,
      maximum: heights.length ? Math.max(...heights) : 0,
      average: heights.length
        ? heights.reduce((sum, height) => sum + height, 0) / heights.length
        : 0,
    }
  })

  function pause(): void {
    playing.value = false
    cancelAnimationFrame(animationFrame)
    previousFrame = 0
  }

  function animate(now: number): void {
    if (!playing.value || !track.value || disposed) return
    if (!previousFrame) previousFrame = now
    const delta = (now - previousFrame) / 1000
    // 限制为约 30 次/秒的状态更新，使用真实帧间隔，回放速度不依赖屏幕刷新率。
    if (delta >= 1 / 30) {
      previousFrame = now
      elapsed.value = Math.min(track.value.durationSeconds, elapsed.value + delta * speed.value)
      if (elapsed.value >= track.value.durationSeconds) {
        pause()
        return
      }
    }
    animationFrame = requestAnimationFrame(animate)
  }

  function togglePlayback(): void {
    if (playing.value) return pause()
    if (!track.value) return
    if (elapsed.value >= track.value.durationSeconds) elapsed.value = 0
    playing.value = true
    animationFrame = requestAnimationFrame(animate)
  }

  function seek(event: Event): void {
    if (!track.value) return
    const value = Number((event.target as HTMLInputElement).value)
    elapsed.value = Math.max(0, Math.min(value, track.value.durationSeconds))
  }

  function overview(): void {
    following.value = false
    scene?.overview()
  }

  async function updateCorridor(): Promise<void> {
    const version = ++corridorVersion
    if (!track.value || !scene) return
    nearbyBuildings.value = filterNearbyBuildings(allBuildings, track.value, radius.value)
    loadingBuildings.value = true
    try {
      await scene.setBuildings(nearbyBuildings.value, heightScale.value, showBuildings.value)
      if (!disposed && version === corridorVersion) {
        scene.updateBuildingStyle(heightScale.value, showBuildings.value)
      }
    } catch (error) {
      if (!disposed && version === corridorVersion) {
        console.error(error)
        buildingError.value = '沿线建筑渲染失败，可重新加载建筑；轨迹回放仍可使用。'
      }
    } finally {
      if (!disposed && version === corridorVersion) loadingBuildings.value = false
    }
  }

  async function loadTrack(id: string): Promise<void> {
    pause()
    trackRequest?.abort()
    trackRequest = new AbortController()
    const request = trackRequest
    corridorVersion += 1
    scene?.clearRoute()
    scene?.clearBuildings()
    track.value = null
    nearbyBuildings.value = []
    selectedBuilding.value = null
    following.value = false
    elapsed.value = 0
    trackError.value = ''
    loadingTrack.value = true
    loadingBuildings.value = false

    try {
      const response = await fetch(`/api/activities/${encodeURIComponent(id)}/track`, {
        signal: request.signal,
      })
      if (!response.ok) throw new Error(`轨迹接口返回 ${response.status}`)
      const data = (await response.json()) as TrackCollection
      if (disposed || request.signal.aborted) return
      track.value = prepareTrack(data)
      scene?.setRoute(track.value, colorMode.value)
      scene?.updateRunner(track.value.points[0]!, false)
      overview()
      void updateCorridor()
    } catch (error) {
      if (!disposed && !request.signal.aborted) {
        console.error(error)
        trackError.value = '这次活动的 GPS 轨迹不可用，请选择其他活动。'
      }
    } finally {
      if (!disposed && !request.signal.aborted) loadingTrack.value = false
    }
  }

  async function loadActivities(): Promise<void> {
    loadingActivities.value = true
    activityError.value = ''
    try {
      const rows = await fetchAllActivities<RunningActivity>(
        { has_gps: 'true', sport: 'running', sort: 'date_desc' },
        lifetime.signal,
      )
      if (disposed) return
      activities.value = rows.filter((item) => !item.training_excluded)
      if (!activities.value.length) {
        activityError.value = '当前没有含 GPS 的正式跑步活动。'
      } else if (!activities.value.some((item) => item.id === selectedActivityId.value)) {
        selectedActivityId.value = activities.value[0]!.id
      }
    } catch (error) {
      if (!disposed) {
        console.error(error)
        activityError.value = '活动列表读取失败，请确认后端服务已启动。'
      }
    } finally {
      if (!disposed) loadingActivities.value = false
    }
  }

  async function loadBuildings(): Promise<void> {
    buildingError.value = ''
    loadingBuildings.value = true
    try {
      const response = await fetch('/cesium-data/guangzhou-buildings.geojson', {
        signal: lifetime.signal,
      })
      if (!response.ok) throw new Error(`建筑文件返回 ${response.status}`)
      const data = (await response.json()) as BuildingCollection
      if (disposed) return
      allBuildings = prepareBuildings(data)
      totalBuildings.value = allBuildings.length
      await updateCorridor()
    } catch (error) {
      if (!disposed) {
        console.error(error)
        buildingError.value = '广州建筑文件读取失败，请检查 public/cesium-data；轨迹回放仍可使用。'
      }
    } finally {
      if (!disposed) loadingBuildings.value = false
    }
  }

  watch(selectedActivityId, (id) => {
    if (id) void loadTrack(id)
  })
  watch(radius, () => {
    void updateCorridor()
  })
  watch([heightScale, showBuildings], () =>
    scene?.updateBuildingStyle(heightScale.value, showBuildings.value),
  )
  watch(currentPoint, (point) => {
    if (point) scene?.updateRunner(point, following.value)
  })
  watch(following, (value) => {
    scene?.setFollowing(value)
    if (currentPoint.value) scene?.updateRunner(currentPoint.value, value)
  })
  watch(colorMode, () => {
    if (!track.value) return
    scene?.setRoute(track.value, colorMode.value)
    if (currentPoint.value) scene?.updateRunner(currentPoint.value, following.value)
  })
  watch(onlineBasemap, (enabled) => {
    if (enabled) basemapError.value = ''
    scene?.setBasemap(enabled, () => {
      onlineBasemap.value = false
      basemapError.value = '在线底图不可用，已返回本地纯色地球。'
    })
  })

  const observer = new ResizeObserver(() => scene?.resize())
  const pauseWhenHidden = () => {
    if (document.hidden) pause()
  }
  onMounted(() => {
    if (!container.value) return
    try {
      scene = new RegionScene(
        container.value,
        (building) => {
          selectedBuilding.value = building
        },
        (message) => {
          sceneError.value = message
          pause()
        },
      )
      observer.observe(container.value)
      document.addEventListener('visibilitychange', pauseWhenHidden)
      void loadActivities()
      void loadBuildings()
    } catch (error) {
      console.error(error)
      sceneError.value = 'Cesium 初始化失败，请检查浏览器 WebGL 支持及 Cesium 静态资源。'
    }
  })

  onBeforeUnmount(() => {
    disposed = true
    corridorVersion += 1
    pause()
    trackRequest?.abort()
    lifetime.abort()
    observer.disconnect()
    document.removeEventListener('visibilitychange', pauseWhenHidden)
    scene?.destroy()
    scene = undefined
  })

  return {
    activities,
    track,
    selectedActivityId,
    selectedActivity,
    selectedBuilding,
    radius,
    heightScale,
    showBuildings,
    onlineBasemap,
    colorMode,
    legend,
    elapsed,
    speed,
    playing,
    following,
    currentPoint,
    buildingStats,
    totalBuildings,
    loadingActivities,
    loadingTrack,
    loadingBuildings,
    sceneError,
    activityError,
    trackError,
    buildingError,
    basemapError,
    togglePlayback,
    seek,
    overview,
    loadActivities,
    loadBuildings,
  }
}
