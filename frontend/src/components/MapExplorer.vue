<script setup lang="ts">
import L from 'leaflet'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface HeatProperties {
  cell_id: string
  visits: number
  distance_m: number
  first_date: string
  last_date: string
}
type HeatCollection = GeoJSON.FeatureCollection<GeoJSON.Point, HeatProperties> & {
  cell_size_m: number
  feature_count: number
}
const props = defineProps<{ dark: boolean; startDate?: string | null; endDate?: string | null }>()
const container = ref<HTMLElement>()
const loading = ref(false)
const data = ref<HeatCollection | null>(null)
const dates = ref<[string, string] | null>(null)
const minVisits = ref(1)
// Leaflet 图层由其自身管理，不放入 Vue 响应式状态，销毁时统一清理。
let map: L.Map | undefined
let heatLayer: L.LayerGroup | undefined

const totalDistance = computed(
  () => data.value?.features.reduce((sum, item) => sum + item.properties.distance_m, 0) || 0,
)
const repeatedCells = computed(
  () => data.value?.features.filter((item) => item.properties.visits >= 5).length || 0,
)
const maxVisits = computed(() =>
  Math.max(1, ...(data.value?.features.map((item) => item.properties.visits) || [1])),
)

function formatKm(value: number): string {
  return `${(value / 1000).toFixed(value >= 100_000 ? 0 : 1)} km`
}
function initializeMap(): void {
  if (!container.value || map) return
  map = L.map(container.value, {
    zoomControl: true,
    attributionControl: true,
    preferCanvas: true,
  }).setView([30, 110], 4)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)
  heatLayer = L.layerGroup().addTo(map)
}
function color(visits: number): string {
  const ratio = Math.log1p(visits) / Math.log1p(maxVisits.value)
  return ratio > 0.72 ? '#ff4f38' : ratio > 0.45 ? '#ff7a45' : ratio > 0.22 ? '#ffad66' : '#ffd2a8'
}
function renderGrid(): void {
  if (!map || !heatLayer || !data.value) return
  // 仅清除会随筛选变化的网格圆点，底图和图层容器保持复用。
  heatLayer.clearLayers()
  for (const feature of data.value.features) {
    const [longitude, latitude] = feature.geometry.coordinates
    const info = feature.properties
    const ratio = Math.sqrt(info.visits / maxVisits.value)
    const marker = L.circleMarker([latitude, longitude], {
      radius: 3 + ratio * 13,
      weight: 1,
      color: 'rgba(255,255,255,.75)',
      fillColor: color(info.visits),
      fillOpacity: 0.38 + ratio * 0.5,
    })
    marker.bindPopup(
      `<div class="explore-popup"><strong>${info.visits} 次经过</strong><span>${formatKm(info.distance_m)} · ${info.first_date} 至 ${info.last_date}</span><small>${data.value.cell_size_m} m 探索网格</small></div>`,
    )
    marker.addTo(heatLayer)
  }
  // 每次新数据加载后先聚焦高频区域，让地图首次打开就有可读的视野。
  focusPopular()
  nextTick(() => map?.invalidateSize({ animate: false }))
}
function featureBounds(features: HeatCollection['features']): L.LatLngBounds {
  return L.latLngBounds(
    features.map(
      (feature) =>
        [feature.geometry.coordinates[1], feature.geometry.coordinates[0]] as L.LatLngTuple,
    ),
  )
}
function focusPopular(): void {
  if (!map || !data.value?.features.length) return
  const threshold = Math.max(3, Math.ceil(maxVisits.value * 0.05))
  const popular = data.value.features.filter((feature) => feature.properties.visits >= threshold)
  const bounds = featureBounds(popular.length ? popular : data.value.features)
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [36, 36], maxZoom: 14 })
}
function fitAll(): void {
  if (!map || !data.value?.features.length) return
  const bounds = featureBounds(data.value.features)
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [28, 28], maxZoom: 14 })
}
async function load(): Promise<void> {
  loading.value = true
  try {
    const query = new URLSearchParams({ min_visits: String(minVisits.value) })
    if (dates.value) {
      query.set('start', dates.value[0])
      query.set('end', dates.value[1])
    }
    const response = await fetch(`/api/map/heat-grid?${query}`)
    if (!response.ok) throw new Error('spatial grid unavailable')
    data.value = (await response.json()) as HeatCollection
    renderGrid()
  } catch {
    ElMessage.error('空间网格尚未就绪，请先生成 spatial-grid.json。')
  } finally {
    loading.value = false
  }
}
function setRecentYear(): void {
  if (!props.endDate) return
  const end = new Date(`${props.endDate}T00:00:00Z`)
  const start = new Date(end)
  start.setUTCFullYear(start.getUTCFullYear() - 1)
  start.setUTCDate(start.getUTCDate() + 1)
  dates.value = [start.toISOString().slice(0, 10), props.endDate]
  load()
}
function clearDates(): void {
  dates.value = null
  load()
}

const observer = new ResizeObserver(() => map?.invalidateSize({ animate: false }))
onMounted(() => {
  initializeMap()
  if (container.value) observer.observe(container.value)
  load()
})
watch(
  () => props.dark,
  () => nextTick(() => map?.invalidateSize({ animate: false })),
)
onBeforeUnmount(() => {
  observer.disconnect()
  map?.remove()
})
</script>

<template>
  <section class="map-explorer-page">
    <aside class="map-inspector glass-card">
      <div>
        <p class="eyebrow">SPATIAL MEMORY</p>
        <h2>地图探索</h2>
        <span>把重复路线与新到达区域放回地图中观察</span>
      </div>
      <div class="map-filter">
        <label>日期范围</label>
        <el-date-picker
          v-model="dates"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="—"
          start-placeholder="开始"
          end-placeholder="结束"
          :clearable="false"
          @change="load"
        />
        <div class="quick-filter">
          <el-button @click="setRecentYear">最近一年</el-button>
          <el-button @click="clearDates">全部时间</el-button>
        </div>
        <label>
          最少经过次数
          <strong>{{ minVisits }}</strong>
        </label>
        <el-slider v-model="minVisits" :min="1" :max="20" :show-tooltip="false" @change="load" />
      </div>
      <div class="map-metrics">
        <article>
          <span>探索网格</span>
          <strong>{{ data?.feature_count || 0 }}</strong>
          <small>{{ data?.cell_size_m || 250 }} m CELLS</small>
        </article>
        <article>
          <span>重复区域</span>
          <strong>{{ repeatedCells }}</strong>
          <small>VISITS ≥ 5</small>
        </article>
        <article>
          <span>网格内里程</span>
          <strong>{{ formatKm(totalDistance) }}</strong>
          <small>AGGREGATED</small>
        </article>
        <article>
          <span>最高频次</span>
          <strong>{{ maxVisits }}</strong>
          <small>MAX VISITS</small>
        </article>
      </div>
      <div class="map-focus-actions">
        <button @click="focusPopular">聚焦高频区</button>
        <button @click="fitAll">查看全部范围</button>
      </div>
      <div class="density-legend">
        <span>偶尔经过</span>
        <div>
          <i></i>
          <i></i>
          <i></i>
          <i></i>
        </div>
        <span>高频路线</span>
      </div>
      <p class="map-note">
        圆点表示 250
        米网格中心，大小和颜色由经过该网格的活动次数决定。点击圆点可查看时间范围与累计里程。
      </p>
    </aside>
    <div class="exploration-map glass-card" :class="{ 'map-dark': dark }" v-loading="loading">
      <div ref="container" class="exploration-map-canvas"></div>
      <div class="map-watermark">
        <span>RUNNING TERRITORY</span>
        <strong>你的城市，由脚步逐格点亮</strong>
      </div>
    </div>
  </section>
</template>

<style scoped>
.map-explorer-page {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: clamp(17rem, 24vw, 22rem) minmax(0, 1fr);
  gap: 0.7rem;
}
.map-inspector {
  min-height: 0;
  padding: 1.25rem;
  border-radius: 1.1rem;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.map-inspector .eyebrow {
  margin: 0 0 0.35rem;
  color: var(--accent);
}
.map-inspector h2 {
  margin: 0;
  font-size: 1.4rem;
}
.map-inspector > div > span {
  display: block;
  margin-top: 0.35rem;
  color: var(--muted);
  font-size: 0.62rem;
  line-height: 1.55;
}
.map-filter {
  display: grid;
  gap: 0.55rem;
  margin-top: 1.3rem;
  padding: 1rem 0;
  border-block: 1px solid var(--line);
}
.map-filter label {
  color: var(--muted);
  font-size: 0.58rem;
}
.map-filter label strong {
  float: right;
  color: var(--text);
}
.map-filter .el-date-editor {
  width: 100%;
}
.quick-filter {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.4rem;
}
.quick-filter .el-button {
  margin: 0;
}
.map-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
  margin-top: 1rem;
}
.map-metrics article {
  padding: 0.75rem;
  border-radius: 0.8rem;
  background: rgba(var(--accent-rgb), 0.07);
}
.map-metrics span,
.map-metrics strong,
.map-metrics small {
  display: block;
}
.map-metrics span {
  color: var(--muted);
  font-size: 0.55rem;
}
.map-metrics strong {
  margin: 0.2rem 0;
  font-size: 1rem;
}
.map-metrics small {
  color: var(--accent);
  font-family: 'DM Mono', monospace;
  font-size: 0.42rem;
}
.density-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 1rem;
  color: var(--muted);
  font-size: 0.5rem;
}
.density-legend div {
  display: flex;
  gap: 0.25rem;
}
.density-legend i {
  width: 1.1rem;
  height: 0.35rem;
  border-radius: 1rem;
  background: #ffd2a8;
}
.density-legend i:nth-child(2) {
  background: #ffad66;
}
.density-legend i:nth-child(3) {
  background: #ff7a45;
}
.density-legend i:nth-child(4) {
  background: #ff4f38;
}
.map-note {
  margin: 0.6rem 0 0;
  color: var(--muted);
  font-size: 0.5rem;
  line-height: 1.55;
}
.exploration-map {
  position: relative;
  min-width: 0;
  min-height: 0;
  padding: 0.45rem;
  border-radius: 1.1rem;
  overflow: hidden;
}
.exploration-map-canvas {
  width: 100%;
  height: 100%;
  border-radius: 0.8rem;
}
.map-dark .exploration-map-canvas :deep(.leaflet-tile-pane) {
  filter: brightness(0.66) saturate(0.7) contrast(1.08);
}
.map-watermark {
  position: absolute;
  z-index: 500;
  left: 1.2rem;
  top: 1.2rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: 0.8rem;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 0.7rem 2rem rgba(20, 32, 48, 0.14);
  backdrop-filter: blur(16px);
}
.map-dark .map-watermark {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(20, 29, 43, 0.78);
  color: #f3f6fa;
}
.map-watermark span,
.map-watermark strong {
  display: block;
}
.map-watermark span {
  color: #ff6b35;
  font-family: 'DM Mono', monospace;
  font-size: 0.45rem;
  letter-spacing: 0.12em;
}
.map-watermark strong {
  margin-top: 0.25rem;
  font-size: 0.7rem;
}
:global(.explore-popup strong),
:global(.explore-popup span),
:global(.explore-popup small) {
  display: block;
}
:global(.explore-popup strong) {
  font-size: 0.75rem;
}
:global(.explore-popup span) {
  margin-top: 0.25rem;
  font-size: 0.62rem;
}
:global(.explore-popup small) {
  margin-top: 0.2rem;
  color: #7a8799;
  font-size: 0.5rem;
}
@media (max-width: 900px) {
  .map-explorer-page {
    grid-template-columns: 15rem minmax(0, 1fr);
  }
  .map-inspector > div > span,
  .map-note {
    display: none;
  }
}
@media (max-width: 760px) {
  .map-explorer-page {
    height: 48rem;
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(28rem, 1fr);
  }
  .map-inspector {
    overflow: visible;
  }
  .map-metrics {
    grid-template-columns: repeat(4, 1fr);
  }
  .density-legend {
    display: none;
  }
}
.map-inspector {
  overflow-x: hidden;
}
.map-filter :deep(.el-date-editor) {
  width: 100%;
  min-width: 0;
}
.quick-filter .el-button {
  min-width: 0;
  padding-inline: 0.4rem;
  font-size: 0.6rem;
}
.map-focus-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.4rem;
  margin-top: 0.8rem;
}
.map-focus-actions button {
  padding: 0.55rem 0.35rem;
  border: 1px solid var(--line);
  border-radius: 0.65rem;
  color: var(--text);
  background: rgba(127, 142, 164, 0.07);
  cursor: pointer;
  font-size: 0.55rem;
}
.map-focus-actions button:hover {
  border-color: rgba(var(--accent-rgb), 0.5);
  background: rgba(var(--accent-rgb), 0.08);
}
</style>
