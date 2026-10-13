<script setup lang="ts">
import L from 'leaflet'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface TrackSeries {
  timestamp?: Array<string | null>
  distance?: Array<number | null>
  heart_rate?: Array<number | null>
  enhanced_speed?: Array<number | null>
  speed?: Array<number | null>
}
interface TrackProperties {
  series?: TrackSeries
}

const props = defineProps<{ activityId: string; dark: boolean; focusDistanceKm?: number | null }>()
const emit = defineEmits<{ progress: [distanceKm: number] }>()
const container = ref<HTMLElement>()
const loading = ref(false)
const unavailable = ref(false)
const sliderIndex = ref(0)
const routeLength = ref(0)
const playing = ref(false)
const trackSeries = ref<TrackSeries>({})
// Leaflet 实例不需要参与 Vue 渲染，使用普通变量并在组件卸载时手动释放。
let map: L.Map | undefined
let movingMarker: L.CircleMarker | undefined
let routePoints: L.LatLng[] = []
let playbackTimer: number | undefined

const sliderMax = computed(() => Math.max(0, routeLength.value - 1))
const currentMetrics = computed(() => {
  const index = Math.min(sliderIndex.value, sliderMax.value)
  const distance = trackSeries.value.distance?.[index]
  const heartRate = trackSeries.value.heart_rate?.[index]
  const speed = trackSeries.value.enhanced_speed?.[index] ?? trackSeries.value.speed?.[index]
  const timestamp = trackSeries.value.timestamp?.[index]
  return {
    distance: typeof distance === 'number' ? `${(distance / 1000).toFixed(2)} km` : '—',
    heartRate: typeof heartRate === 'number' ? `${heartRate} bpm` : '—',
    pace: typeof speed === 'number' && speed > 0.25 ? formatPace(1000 / speed) : '—',
    time: timestamp
      ? new Date(timestamp).toLocaleTimeString('zh-CN', {
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      : '—',
  }
})

const sizeObserver = new ResizeObserver(() =>
  window.setTimeout(() => map?.invalidateSize({ animate: false }), 30),
)

function formatPace(seconds: number): string {
  return `${Math.floor(seconds / 60)}′${String(Math.round(seconds % 60)).padStart(2, '0')}″/km`
}
function stopPlayback(): void {
  if (playbackTimer !== undefined) window.clearInterval(playbackTimer)
  playbackTimer = undefined
  playing.value = false
}
function togglePlayback(): void {
  if (playing.value) {
    stopPlayback()
    return
  }
  if (sliderIndex.value >= sliderMax.value) sliderIndex.value = 0
  playing.value = true
  const step = Math.max(1, Math.floor(routeLength.value / 260))
  playbackTimer = window.setInterval(() => {
    if (sliderIndex.value + step >= sliderMax.value) {
      sliderIndex.value = sliderMax.value
      stopPlayback()
    } else sliderIndex.value += step
  }, 80)
}
function updateMovingMarker(index: number): void {
  const point = routePoints[Math.min(index, routePoints.length - 1)]
  if (!point || !movingMarker) return
  movingMarker.setLatLng(point)
  map?.panInside(point, { padding: [28, 28], animate: false })
}
function seekToDistance(distanceKm: number | null | undefined): void {
  if (distanceKm == null) return
  const distances = trackSeries.value.distance || []
  if (!distances.length) return
  // 轨迹距离按递增顺序排列，用二分查找定位图表光标对应的最近采样点。
  const target = distanceKm * 1000
  let low = 0
  let high = distances.length - 1
  while (low < high) {
    const middle = Math.floor((low + high) / 2)
    if ((distances[middle] || 0) < target) low = middle + 1
    else high = middle
  }
  if (Math.abs(sliderIndex.value - low) > 1) sliderIndex.value = low
}
function addKilometerMarkers(distances: Array<number | null>): void {
  if (!map || !distances.length) return
  const totalKm = Math.floor((distances.at(-1) || 0) / 1000)
  let index = 0
  for (let kilometer = 1; kilometer <= totalKm; kilometer += 1) {
    const target = kilometer * 1000
    while (index < distances.length - 1 && (distances[index] || 0) < target) index += 1
    const point = routePoints[index]
    if (!point) continue
    const markerIndex = index
    const icon = L.divIcon({
      className: 'km-marker-host',
      html: `<span>${kilometer}</span>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    })
    L.marker(point, { icon, keyboard: true, title: `${kilometer} km` })
      .addTo(map)
      .on('click', () => {
        sliderIndex.value = markerIndex
      })
  }
}

async function renderTrack(): Promise<void> {
  if (!container.value) return
  stopPlayback()
  loading.value = true
  unavailable.value = false
  sliderIndex.value = 0
  try {
    const response = await fetch(`/api/activities/${props.activityId}/track`)
    if (!response.ok) throw new Error('track unavailable')
    const geojson = (await response.json()) as GeoJSON.FeatureCollection<
      GeoJSON.LineString,
      TrackProperties
    >
    const feature = geojson.features[0]
    const coordinates = feature?.geometry.coordinates || []
    if (coordinates.length < 2) throw new Error('empty track')
    trackSeries.value = feature.properties?.series || {}
    routeLength.value = coordinates.length
    map?.remove()
    map = L.map(container.value, { zoomControl: true, attributionControl: true })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 19,
    }).addTo(map)
    routePoints = coordinates.map(([longitude, latitude]) => L.latLng(latitude, longitude))
    const line = L.polyline(routePoints, { color: '#ff6b35', weight: 4, opacity: 0.92 }).addTo(map)
    L.circleMarker(routePoints[0], {
      radius: 6,
      color: '#fff',
      weight: 2,
      fillColor: '#38b879',
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip('起点')
    L.circleMarker(routePoints.at(-1)!, {
      radius: 6,
      color: '#fff',
      weight: 2,
      fillColor: '#ff5f57',
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip('终点')
    movingMarker = L.circleMarker(routePoints[0], {
      radius: 7,
      color: '#fff',
      weight: 3,
      fillColor: '#3478f6',
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip('当前位置')
    addKilometerMarkers(trackSeries.value.distance || [])
    map.fitBounds(line.getBounds(), { padding: [28, 28] })
    await nextTick()
    map.invalidateSize()
  } catch {
    unavailable.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  renderTrack()
  if (container.value) sizeObserver.observe(container.value)
})
watch(() => props.activityId, renderTrack)
watch(sliderIndex, (index) => {
  updateMovingMarker(index)
  const distance = trackSeries.value.distance?.[index]
  if (typeof distance === 'number') emit('progress', distance / 1000)
})
watch(() => props.focusDistanceKm, seekToDistance)
onBeforeUnmount(() => {
  // 停止定时器并销毁 Leaflet，避免关闭弹窗后仍占用事件监听与 DOM。
  stopPlayback()
  sizeObserver.disconnect()
  map?.remove()
})
</script>

<template>
  <div class="map-frame" :class="{ 'map-dark': dark }" v-loading="loading">
    <div ref="container" class="leaflet-map"></div>
    <div v-if="!unavailable && routeLength" class="playback-panel">
      <button
        class="play-button"
        :aria-label="playing ? '暂停回放' : '开始回放'"
        @click="togglePlayback"
      >
        {{ playing ? 'Ⅱ' : '▶' }}
      </button>
      <el-slider v-model="sliderIndex" :min="0" :max="sliderMax" :show-tooltip="false" />
      <div class="playback-values">
        <span>
          <small>距离</small>
          {{ currentMetrics.distance }}
        </span>
        <span>
          <small>时间</small>
          {{ currentMetrics.time }}
        </span>
        <span>
          <small>心率</small>
          {{ currentMetrics.heartRate }}
        </span>
        <span>
          <small>配速</small>
          {{ currentMetrics.pace }}
        </span>
      </div>
    </div>
    <div v-if="unavailable" class="map-empty">该活动没有可用 GPS 轨迹</div>
  </div>
</template>

<style scoped>
.map-frame {
  position: relative;
  height: 270px;
  border-radius: 15px;
  overflow: hidden;
  background: #dfe6ed;
}
.leaflet-map {
  height: 100%;
  width: 100%;
}
.map-dark .leaflet-map :deep(.leaflet-tile-pane) {
  filter: brightness(0.68) saturate(0.72) contrast(1.08);
}
.map-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #778397;
  background: rgba(238, 242, 247, 0.9);
  font-size: 12px;
}
.playback-panel {
  position: absolute;
  z-index: 1100;
  left: 10px;
  right: 10px;
  bottom: 10px;
  min-width: 0;
  display: grid;
  grid-template-columns: 30px minmax(80px, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px 11px;
  border: 1px solid rgba(255, 255, 255, 0.68);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 9px 30px rgba(25, 39, 58, 0.18);
  backdrop-filter: blur(18px) saturate(145%);
  -webkit-backdrop-filter: blur(18px) saturate(145%);
}
.map-dark .playback-panel {
  color: #f3f6fa;
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(20, 29, 43, 0.8);
}
.play-button {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: #fff;
  background: #ff6b35;
  cursor: pointer;
  font-size: 10px;
}
.playback-panel :deep(.el-slider) {
  --el-slider-main-bg-color: #ff6b35;
  --el-slider-runway-bg-color: rgba(112, 127, 149, 0.24);
  --el-slider-button-size: 12px;
}
.playback-values {
  display: flex;
  gap: 11px;
}
.playback-values span,
.playback-values small {
  display: block;
  white-space: nowrap;
}
.playback-values span {
  font-size: 9px;
  font-weight: 700;
}
.playback-values small {
  margin-bottom: 2px;
  color: #78859a;
  font-size: 7px;
  font-weight: 500;
}
.map-dark .playback-values small {
  color: #95a3b7;
}
:global(.km-marker-host) {
  background: transparent !important;
  border: 0 !important;
}
:global(.km-marker-host span) {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border: 2px solid #fff;
  border-radius: 50%;
  color: #fff;
  background: #ff6b35;
  box-shadow: 0 3px 9px rgba(20, 31, 47, 0.25);
  font:
    700 8px Manrope,
    sans-serif;
}
@media (max-width: 700px) {
  .playback-panel {
    grid-template-columns: 30px 1fr;
  }
  .playback-values {
    grid-column: 1/-1;
    justify-content: space-between;
  }
  .playback-values span:nth-child(2) {
    display: none;
  }
}
</style>
