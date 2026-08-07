<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ActivityMap from './ActivityMap.vue'
import ActivityMetricChart from './ActivityMetricChart.vue'

interface Activity {
  id: string
  date: string | null
  sport: string | number | null
  distance_m: number | null
  elapsed_s: number | null
  average_heart_rate: number | null
  average_pace_s_per_km: number | null
  has_gps: boolean
}
interface ChartPoint { x: number; y: number | null; distanceKm: number }
interface ZoneBand { label: string; shortLabel: string; min?: number; max?: number; color: string }
interface ReferenceLine { label: string; value: number; color: string }
interface ChartSpec { id: string; title: string; subtitle: string; unit: string; type: 'line' | 'scatter'; points: ChartPoint[]; pace?: boolean; zones?: ZoneBand[]; zoneNote?: string; referenceLine?: ReferenceLine | null; yAxisDecimals?: number }
interface SummaryMetricOption { id: string; label: string; series: string; digits: number; unit: string; transform?: (value: number) => number }
type TrackSeries = Record<string, Array<number | string | null>>
interface ActivityInsights { pace_cv_percent: number | null; heart_rate_drift_percent: number | null; stopped_ratio_percent: number | null; training_type: string }
interface AthleteProfile { running_fitness?: { threshold_pace_s_per_km?: number | null; threshold_heart_rate_bpm?: number | null } }
interface PersonalZone { id: string; label: string; shortLabel: string; color: string; paceFast: string; paceSlow: string; heartRateMin: string; heartRateMax: string }

const props = defineProps<{ modelValue: boolean; activity: Activity | null; dark: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const fullscreen = ref(false)
const settingsOpen = ref(false)
const loading = ref(false)
const series = ref<TrackSeries>({})
const insights = ref<ActivityInsights | null>(null)
const activeDistanceKm = ref<number | null>(null)
const chartRefs = ref<Array<{ resize: () => void }>>([])
const defaultOrder = ['pace', 'heart_rate', 'altitude', 'cadence', 'power', 'step_length', 'stance_time', 'vertical_oscillation', 'vertical_ratio']
const storedOrder = localStorage.getItem('running-webgis-chart-order')
const chartOrder = ref<string[]>(storedOrder ? JSON.parse(storedOrder) : [...defaultOrder])
const storedSummaryMetrics = localStorage.getItem('running-webgis-summary-metrics')
const enabledSummaryMetrics = ref<string[]>(storedSummaryMetrics ? JSON.parse(storedSummaryMetrics) : ['cadence', 'step_length'])
const storedXAxisMode = localStorage.getItem('running-webgis-chart-x-axis')
const xAxisMode = ref<'distance' | 'time'>(storedXAxisMode === 'time' ? 'time' : 'distance')
const thresholdPaceSeconds = ref<number | null>(null)
const zoneEditorOpen = ref(false)
const defaultPersonalZones: PersonalZone[] = [
  { id: 'z1', label: '积极恢复区', shortLabel: '恢复', color: 'rgba(46, 132, 230, .20)', paceFast: '6:08', paceSlow: '', heartRateMin: '', heartRateMax: '145' },
  { id: 'z2', label: '有氧耐力区', shortLabel: '耐力', color: 'rgba(42, 190, 205, .20)', paceFast: '5:04', paceSlow: '6:08', heartRateMin: '145', heartRateMax: '163' },
  { id: 'z3', label: '有氧动力区', shortLabel: '动力', color: 'rgba(48, 190, 94, .20)', paceFast: '4:42', paceSlow: '5:03', heartRateMin: '164', heartRateMax: '172' },
  { id: 'z4', label: '乳酸阈区', shortLabel: '阈值', color: 'rgba(250, 205, 45, .20)', paceFast: '4:16', paceSlow: '4:41', heartRateMin: '173', heartRateMax: '185' },
  { id: 'z5', label: '速度耐力区', shortLabel: '速度', color: 'rgba(255, 108, 55, .20)', paceFast: '3:54', paceSlow: '4:15', heartRateMin: '186', heartRateMax: '192' },
  { id: 'z6', label: '无氧动力区', shortLabel: '无氧', color: 'rgba(241, 58, 61, .20)', paceFast: '', paceSlow: '3:54', heartRateMin: '192', heartRateMax: '' },
]
function loadPersonalZones(): PersonalZone[] {
  try {
    const saved = JSON.parse(localStorage.getItem('running-webgis-personal-zones') || 'null') as PersonalZone[] | null
    const hasUserValues = saved?.some((zone) => [zone.paceFast, zone.paceSlow, zone.heartRateMin, zone.heartRateMax].some((value) => String(value ?? '').trim()))
    return saved?.length === 6 && hasUserValues ? defaultPersonalZones.map((fallback, index) => ({ ...fallback, ...saved[index], id: fallback.id, label: fallback.label, shortLabel: fallback.shortLabel, color: fallback.color })) : defaultPersonalZones.map((zone) => ({ ...zone }))
  } catch { return defaultPersonalZones.map((zone) => ({ ...zone })) }
}
const personalZones = ref<PersonalZone[]>(loadPersonalZones())
const summaryMetricOptions: SummaryMetricOption[] = [
  { id: 'cadence', label: '平均步频', series: 'cadence', digits: 0, unit: 'spm', transform: cadenceValue },
  { id: 'step_length', label: '平均步幅', series: 'step_length', digits: 2, unit: 'm', transform: (value) => value / 1000 },
  { id: 'power', label: '平均功率', series: 'power', digits: 0, unit: 'W' },
  { id: 'stance_time', label: '平均触地时间', series: 'stance_time', digits: 0, unit: 'ms' },
  { id: 'vertical_oscillation', label: '平均垂直振幅', series: 'vertical_oscillation', digits: 1, unit: 'cm', transform: (value) => value / 10 },
  { id: 'vertical_ratio', label: '平均垂直比', series: 'vertical_ratio', digits: 1, unit: '%' },
]

function numeric(name: string): Array<number | null> { return (series.value[name] || []).map((value) => typeof value === 'number' ? value : null) }
function points(values: Array<number | null>, transform: (value: number) => number = (value) => value): ChartPoint[] {
  const distances = numeric('distance')
  const timestamps = series.value.timestamp || []
  const firstTimestamp = timestamps.find((value) => typeof value === 'string')
  const firstTime = typeof firstTimestamp === 'string' ? new Date(firstTimestamp).getTime() : Number.NaN
  const step = Math.max(1, Math.floor(values.length / 1800))
  let lastValidIndex = values.length - 1
  while (lastValidIndex > 0 && (values[lastValidIndex] == null || distances[lastValidIndex] == null)) lastValidIndex -= 1
  return values.flatMap((value, index) => {
    const isLast = index === lastValidIndex
    if ((index % step !== 0 && !isLast) || distances[index] == null) return []
    const timestamp = timestamps[index]
    const elapsedMinutes = typeof timestamp === 'string' && Number.isFinite(firstTime) ? Math.max(0, (new Date(timestamp).getTime() - firstTime) / 60000) : Number.NaN
    const distanceKm = distances[index]! / 1000
    return [{ x: xAxisMode.value === 'time' && Number.isFinite(elapsedMinutes) ? elapsedMinutes : distanceKm, distanceKm, y: value == null ? null : transform(value) }]
  })
}
function cadenceValue(value: number): number { return value < 120 ? value * 2 : value }
function parsePace(value: string): number | undefined {
  const match = value.trim().match(/^(\d{1,2}):([0-5]\d)$/)
  if (!match) return undefined
  return Number(match[1]) + Number(match[2]) / 60
}
function parseNumeric(value: string): number | undefined {
  if (!value.trim()) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}
const paceZones = computed<ZoneBand[]>(() => personalZones.value.flatMap((zone) => {
  const min = parsePace(zone.paceFast)
  const max = parsePace(zone.paceSlow)
  return (min != null || max != null) && (min == null || max == null || min < max) ? [{ label: zone.label, shortLabel: zone.shortLabel, min, max, color: zone.color }] : []
}))
const heartRateZones = computed<ZoneBand[]>(() => personalZones.value.flatMap((zone) => {
  const min = parseNumeric(zone.heartRateMin)
  const max = parseNumeric(zone.heartRateMax)
  return (min != null || max != null) && (min == null || max == null || min < max) ? [{ label: zone.label, shortLabel: zone.shortLabel, min, max, color: zone.color }] : []
}))
const dynamicsZones: Record<string, ZoneBand[]> = {
  cadence: [
    { label: '<153', shortLabel: '<153', max: 153, color: 'rgba(220,76,92,.16)' }, { label: '153–163', shortLabel: '153–163', min: 153, max: 164, color: 'rgba(244,151,61,.16)' }, { label: '164–173', shortLabel: '164–173', min: 164, max: 174, color: 'rgba(57,181,130,.16)' }, { label: '174–183', shortLabel: '174–183', min: 174, max: 184, color: 'rgba(64,139,224,.16)' }, { label: '>183', shortLabel: '>183', min: 184, color: 'rgba(139,100,210,.16)' },
  ],
  stance_time: [
    { label: '<218', shortLabel: '<218', max: 218, color: 'rgba(139,100,210,.16)' }, { label: '218–248', shortLabel: '218–248', min: 218, max: 249, color: 'rgba(64,139,224,.16)' }, { label: '249–277', shortLabel: '249–277', min: 249, max: 278, color: 'rgba(57,181,130,.16)' }, { label: '278–308', shortLabel: '278–308', min: 278, max: 309, color: 'rgba(244,151,61,.16)' }, { label: '>308', shortLabel: '>308', min: 309, color: 'rgba(220,76,92,.16)' },
  ],
  vertical_oscillation: [
    { label: '<6.7', shortLabel: '<6.7', max: 6.7, color: 'rgba(139,100,210,.16)' }, { label: '6.7–8.3', shortLabel: '6.7–8.3', min: 6.7, max: 8.4, color: 'rgba(64,139,224,.16)' }, { label: '8.4–10.0', shortLabel: '8.4–10.0', min: 8.4, max: 10.1, color: 'rgba(57,181,130,.16)' }, { label: '10.1–11.8', shortLabel: '10.1–11.8', min: 10.1, max: 11.9, color: 'rgba(244,151,61,.16)' }, { label: '>11.8', shortLabel: '>11.8', min: 11.9, color: 'rgba(220,76,92,.16)' },
  ],
  vertical_ratio: [
    { label: '<6.1', shortLabel: '<6.1', max: 6.1, color: 'rgba(139,100,210,.16)' }, { label: '6.1–7.4', shortLabel: '6.1–7.4', min: 6.1, max: 7.5, color: 'rgba(64,139,224,.16)' }, { label: '7.5–8.6', shortLabel: '7.5–8.6', min: 7.5, max: 8.7, color: 'rgba(57,181,130,.16)' }, { label: '8.7–10.1', shortLabel: '8.7–10.1', min: 8.7, max: 10.2, color: 'rgba(244,151,61,.16)' }, { label: '>10.1', shortLabel: '>10.1', min: 10.2, color: 'rgba(220,76,92,.16)' },
  ],
}
function average(values: Array<number | null>, transform: (value: number) => number = (value) => value): number | null {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value)).map(transform)
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null
}

const chartMap = computed<Record<string, ChartSpec>>(() => ({
  pace: { id: 'pace', title: '配速', subtitle: '沿途节奏变化', unit: '/km', type: 'line', pace: true, points: points(numeric('enhanced_speed').length ? numeric('enhanced_speed') : numeric('speed'), (speed) => speed > .25 ? 1000 / speed / 60 : Number.NaN), zones: paceZones.value, zoneNote: paceZones.value.length ? '个人 COROS 六区间；在设置中维护，保存在当前浏览器。' : '尚未填写个人配速区间。', referenceLine: thresholdPaceSeconds.value ? { label: `COROS 阈值 ${formatPace(thresholdPaceSeconds.value)}`, value: thresholdPaceSeconds.value / 60, color: '#ff9a3d' } : null },
  heart_rate: { id: 'heart_rate', title: '心率', subtitle: '训练强度响应', unit: 'bpm', type: 'line', yAxisDecimals: 0, points: points(numeric('heart_rate')), zones: heartRateZones.value, zoneNote: heartRateZones.value.length ? '个人 COROS 六区间；在设置中维护，保存在当前浏览器。' : 'COROS MCP 未返回阈值心率，请在设置中填写。' },
  altitude: { id: 'altitude', title: '海拔', subtitle: '路线高程剖面', unit: 'm', type: 'line', yAxisDecimals: 0, points: points(numeric('enhanced_altitude').length ? numeric('enhanced_altitude') : numeric('altitude')) },
  cadence: { id: 'cadence', title: '步频', subtitle: '落脚节奏分布', unit: 'spm', type: 'scatter', yAxisDecimals: 0, points: points(numeric('cadence'), cadenceValue), zones: dynamicsZones.cadence, zoneNote: '通用跑者百分位参考，不是个人训练目标。配速、身高和地形都会影响结果。' },
  power: { id: 'power', title: '跑步功率', subtitle: '即时输出变化', unit: 'W', type: 'line', yAxisDecimals: 0, points: points(numeric('power')) },
  step_length: { id: 'step_length', title: '步幅', subtitle: '每一步的推进距离', unit: 'm', type: 'scatter', yAxisDecimals: 2, points: points(numeric('step_length'), (value) => value / 1000) },
  stance_time: { id: 'stance_time', title: '触地时间', subtitle: '支撑阶段时长', unit: 'ms', type: 'scatter', yAxisDecimals: 0, points: points(numeric('stance_time')), zones: dynamicsZones.stance_time, zoneNote: '通用跑者百分位参考，不代表绝对优劣。' },
  vertical_oscillation: { id: 'vertical_oscillation', title: '垂直振幅', subtitle: '身体上下波动', unit: 'cm', type: 'line', yAxisDecimals: 1, points: points(numeric('vertical_oscillation'), (value) => value / 10), zones: dynamicsZones.vertical_oscillation, zoneNote: '通用跑者百分位参考；传感器位置与身高会影响数值。' },
  vertical_ratio: { id: 'vertical_ratio', title: '垂直比', subtitle: '垂直振幅与步幅之比', unit: '%', type: 'line', yAxisDecimals: 1, points: points(numeric('vertical_ratio')), zones: dynamicsZones.vertical_ratio, zoneNote: '通用跑者百分位参考；传感器位置会影响数值。' },
}))
const orderedCharts = computed(() => chartOrder.value.map((id) => chartMap.value[id]).filter((chart) => chart?.points.some((point) => point.y != null)))
const summaryMetrics = computed(() => summaryMetricOptions.map((option) => ({
  ...option,
  value: average(numeric(option.series), option.transform),
})))
const visibleSummaryMetrics = computed(() => summaryMetrics.value.filter((metric) => enabledSummaryMetrics.value.includes(metric.id) && metric.value != null))
function metricAvailable(id: string): boolean { return summaryMetrics.value.find((metric) => metric.id === id)?.value != null }
const summaryPanelWidth = computed(() => {
  const responsiveWidths = [
    'clamp(15rem, 20vw, 19rem)',
    'clamp(18rem, 23vw, 23rem)',
    'clamp(21rem, 27vw, 27rem)',
    'clamp(24rem, 30vw, 31rem)',
  ]
  return responsiveWidths[Math.min(visibleSummaryMetrics.value.length, responsiveWidths.length - 1)]
})

async function loadTrack(): Promise<void> {
  if (!props.activity?.id || !props.modelValue) return
  loading.value = true; series.value = {}; insights.value = null; activeDistanceKm.value = null
  try {
    const [response, insightsResponse, profileResponse] = await Promise.all([fetch(`/api/activities/${props.activity.id}/track`), fetch(`/api/activities/${props.activity.id}/insights`), fetch('/api/athlete-profile')])
    if (!response.ok) throw new Error('track unavailable')
    const data = await response.json() as { features: Array<{ properties: { series: TrackSeries } }> }
    series.value = data.features[0]?.properties.series || {}
    if (insightsResponse.ok) insights.value = await insightsResponse.json() as ActivityInsights
    if (profileResponse.ok) {
      const profile = await profileResponse.json() as AthleteProfile
      thresholdPaceSeconds.value = profile.running_fitness?.threshold_pace_s_per_km ?? null
    }
  } catch {
    series.value = {}
  } finally { loading.value = false }
}
function close(): void { fullscreen.value = false; settingsOpen.value = false; emit('update:modelValue', false) }
async function resizeChartsAfterLayout(): Promise<void> {
  await nextTick()
  chartRefs.value.forEach((item) => item.resize())
  window.setTimeout(() => chartRefs.value.forEach((item) => item.resize()), 320)
}
function toggleFullscreen(): void {
  fullscreen.value = !fullscreen.value
  settingsOpen.value = false
  resizeChartsAfterLayout()
}
function moveChart(index: number, direction: -1 | 1): void {
  const target = index + direction
  if (target < 0 || target >= chartOrder.value.length) return
  const order = [...chartOrder.value]; [order[index], order[target]] = [order[target], order[index]]; chartOrder.value = order
  localStorage.setItem('running-webgis-chart-order', JSON.stringify(order))
}
function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !props.modelValue) return
  if (fullscreen.value) {
    fullscreen.value = false
    settingsOpen.value = false
    resizeChartsAfterLayout()
  } else close()
}
function formatKm(value: number | null): string { return value == null ? '—' : `${(value / 1000).toFixed(2)} km` }
function formatPace(value: number | null): string { if (!value) return '—'; return `${Math.floor(value / 60)}′${String(Math.round(value % 60)).padStart(2, '0')}″` }

watch([() => props.modelValue, () => props.activity?.id], ([open]) => { if (open) loadTrack() })
watch(enabledSummaryMetrics, (value) => localStorage.setItem('running-webgis-summary-metrics', JSON.stringify(value)), { deep: true })
watch(xAxisMode, (value) => localStorage.setItem('running-webgis-chart-x-axis', value))
watch(personalZones, (value) => localStorage.setItem('running-webgis-personal-zones', JSON.stringify(value)), { deep: true })
onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="detail-fade">
      <div v-if="modelValue" class="detail-overlay" @mousedown.self="close">
        <section class="detail-modal" :class="{ fullscreen }">
          <header class="detail-toolbar">
            <div class="traffic-lights">
              <button class="traffic close" title="关闭" aria-label="关闭" @click="close">×</button>
              <button class="traffic settings" title="调整图表顺序" aria-label="设置" @click="settingsOpen = !settingsOpen">⚙</button>
              <button class="traffic expand" :title="fullscreen ? '退出全屏' : '全屏'" aria-label="全屏" @click="toggleFullscreen">↗</button>
            </div>
            <div class="detail-identity"><span>{{ activity?.date }}</span><strong>{{ activity?.sport || '运动记录' }}</strong></div>
            <div v-if="settingsOpen" class="chart-settings glass-card">
              <div class="settings-section axis-settings"><strong>图表横轴</strong><span>所有运动图表统一使用距离或运动时间</span><el-segmented v-model="xAxisMode" :options="[{ label: '距离', value: 'distance' }, { label: '时间', value: 'time' }]" /></div>
              <div class="settings-section zone-settings">
                <button class="zone-editor-toggle" @click="zoneEditorOpen = !zoneEditorOpen"><span><strong>COROS 强度区间</strong><small>手动填写并自动保存在本浏览器</small></span><b>{{ zoneEditorOpen ? '收起' : '编辑' }}</b></button>
                <div v-if="zoneEditorOpen" class="zone-editor">
                  <div class="zone-editor-head"><span>区间</span><span>配速 快–慢</span><span>心率 低–高</span></div>
                  <div v-for="zone in personalZones" :key="zone.id" class="zone-row">
                    <span><i :style="{ background: zone.color }"></i>{{ zone.label }}</span>
                    <label><el-input v-model="zone.paceFast" placeholder="4:10" /><em>–</em><el-input v-model="zone.paceSlow" placeholder="4:35" /></label>
                    <label><el-input v-model="zone.heartRateMin" inputmode="numeric" placeholder="160" /><em>–</em><el-input v-model="zone.heartRateMax" inputmode="numeric" placeholder="175" /></label>
                  </div>
                  <p>配速格式为 m:ss/km；首尾区间允许留空表示无上限或无下限。默认值来自 2026-08-06 COROS 截图，用户填写后以本地值优先。</p>
                </div>
              </div>
              <div class="settings-section"><strong>概览指标</strong><span>距离、平均配速、平均心率固定显示；无数据的指标不可选</span><el-checkbox-group v-model="enabledSummaryMetrics"><el-checkbox v-for="option in summaryMetricOptions" :key="option.id" :value="option.id" :disabled="!metricAvailable(option.id)">{{ option.label }}</el-checkbox></el-checkbox-group></div>
              <div class="settings-section chart-order-title"><strong>图表顺序</strong><span>调整下方分析图表的显示顺序</span></div>
              <ul><li v-for="(id, index) in chartOrder" :key="id"><span>{{ chartMap[id]?.title }}</span><div><button :disabled="index === 0" @click="moveChart(index, -1)">↑</button><button :disabled="index === chartOrder.length - 1" @click="moveChart(index, 1)">↓</button></div></li></ul>
            </div>
          </header>

          <div class="detail-content" v-loading="loading">
            <section class="fixed-overview" :class="{ 'metrics-expanded': visibleSummaryMetrics.length > 2 }" :style="{ '--summary-width': summaryPanelWidth }">
              <div class="fixed-stats">
                <p class="eyebrow">ACTIVITY SUMMARY</p><h2>{{ activity?.date }}<br><em>{{ activity?.sport || 'Training' }}</em></h2>
                <div class="primary-metric"><strong>{{ formatKm(activity?.distance_m ?? null) }}</strong><span>距离</span></div>
                <div class="secondary-metrics"><div><strong>{{ formatPace(activity?.average_pace_s_per_km ?? null) }}</strong><span>平均配速</span></div><div><strong>{{ activity?.average_heart_rate ? `${activity.average_heart_rate} bpm` : '—' }}</strong><span>平均心率</span></div><div v-for="metric in visibleSummaryMetrics" :key="metric.id"><strong>{{ metric.value!.toFixed(metric.digits) }} {{ metric.unit }}</strong><span>{{ metric.label }}</span></div></div>
              </div>
              <div class="detail-map"><ActivityMap v-if="activity?.has_gps" :activity-id="activity.id" :dark="dark" :focus-distance-km="activeDistanceKm" @progress="activeDistanceKm = $event" /><el-empty v-else description="该活动没有 GPS 轨迹" :image-size="55" /></div>
            </section>
            <section v-if="insights" class="activity-insights">
              <article class="glass-card"><span>自动训练类型</span><strong>{{ insights.training_type }}</strong><small>依据配速波动与停顿特征推测</small></article>
              <article class="glass-card"><span>配速稳定性</span><strong>{{ insights.pace_cv_percent == null ? '—' : `CV ${insights.pace_cv_percent.toFixed(1)}%` }}</strong><small>{{ insights.pace_cv_percent != null && insights.pace_cv_percent < 6 ? '整体节奏较稳定' : '沿途节奏存在明显变化' }}</small></article>
              <article class="glass-card"><span>心率漂移</span><strong>{{ insights.heart_rate_drift_percent == null ? '—' : `${insights.heart_rate_drift_percent > 0 ? '+' : ''}${insights.heart_rate_drift_percent.toFixed(1)}%` }}</strong><small>前后半程速度 / 心率效率变化</small></article>
              <article class="glass-card"><span>低速占比</span><strong>{{ insights.stopped_ratio_percent == null ? '—' : `${insights.stopped_ratio_percent.toFixed(1)}%` }}</strong><small>用于辅助识别停顿与间歇特征</small></article>
            </section>
            <section class="metric-list">
              <article v-for="chart in orderedCharts" :key="chart.id" class="metric-box glass-card"><ActivityMetricChart ref="chartRefs" :title="chart.title" :subtitle="chart.subtitle" :unit="chart.unit" :points="chart.points" :chart-type="chart.type" :pace="chart.pace" :dark="dark" :x-axis-mode="xAxisMode" :cursor-distance-km="activeDistanceKm" :zones="chart.zones" :zone-note="chart.zoneNote" :reference-line="chart.referenceLine" :y-axis-decimals="chart.yAxisDecimals" @seek="activeDistanceKm = $event" /></article>
            </section>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.detail-overlay{position:fixed;inset:0;z-index:2200;display:grid;place-items:center;background:rgba(14,22,34,.32);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}.detail-modal{width:min(1180px,78vw);height:84vh;overflow:hidden;border:1px solid var(--border);border-radius:22px;background:var(--glass-strong);box-shadow:0 30px 90px rgba(21,32,49,.30),inset 0 1px rgba(255,255,255,.5);backdrop-filter:saturate(150%) blur(28px);transition:width .28s,height .28s,border-radius .28s}.detail-modal.fullscreen{width:calc(100vw - 20px);height:calc(100vh - 20px);border-radius:18px}.detail-toolbar{position:relative;height:48px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:0 16px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.12)}.traffic-lights{display:flex;gap:8px}.traffic{width:14px;height:14px;padding:0;border:0;border-radius:50%;display:grid;place-items:center;color:transparent;cursor:pointer;font-size:9px;line-height:1}.traffic:hover{color:rgba(0,0,0,.58)}.traffic.close{background:#ff5f57}.traffic.settings{background:#febc2e}.traffic.expand{background:#28c840}.detail-identity{text-align:center}.detail-identity span,.detail-identity strong{display:block}.detail-identity span{color:var(--muted);font-size:8px}.detail-identity strong{font-size:11px}.chart-settings{position:absolute;left:15px;top:40px;z-index:9;width:300px;padding:14px;border-radius:15px}.settings-section>strong,.settings-section>span{display:block}.settings-section>strong{font-size:11px}.settings-section>span{margin-top:3px;color:var(--muted);font-size:8px}.settings-section .el-checkbox-group{display:flex;gap:14px;margin-top:9px}.settings-section .el-checkbox{margin-right:0;font-size:9px}.chart-order-title{margin-top:13px;padding-top:11px;border-top:1px solid var(--line)}.chart-settings ul{max-height:300px;margin:8px 0 0;padding:0;overflow:auto;list-style:none}.chart-settings li{display:flex;align-items:center;justify-content:space-between;padding:6px 2px;border-top:1px solid var(--line);font-size:9px}.chart-settings li button{width:25px;height:22px;margin-left:3px;border:1px solid var(--line);border-radius:7px;color:var(--text);background:rgba(127,142,164,.08);cursor:pointer}.chart-settings li button:disabled{opacity:.25}.detail-content{height:calc(100% - 48px);padding:12px 14px 18px;overflow-y:auto;scroll-behavior:smooth}.fixed-overview{height:330px;display:grid;grid-template-columns:var(--summary-width,250px) minmax(0,1fr);gap:10px;margin-bottom:10px;transition:grid-template-columns .24s ease}.fixed-stats,.detail-map{min-width:0;border:1px solid var(--border);border-radius:17px;background:var(--glass);box-shadow:var(--shadow);overflow:hidden}.fixed-stats{padding:23px}.fixed-stats .eyebrow{margin:0 0 8px;color:var(--accent)}.fixed-stats h2{margin:0;font-size:21px}.fixed-stats h2 em{color:var(--accent);font-family:"Playfair Display",serif}.primary-metric{margin:24px 0 14px}.primary-metric strong,.primary-metric span,.secondary-metrics strong,.secondary-metrics span{display:block}.primary-metric strong{font-size:26px;letter-spacing:-1.4px}.primary-metric span,.secondary-metrics span{margin-top:4px;color:var(--muted);font-size:8px}.secondary-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.secondary-metrics>div{min-width:0;padding:10px;border-radius:10px;background:rgba(var(--accent-rgb),.07)}.secondary-metrics strong{font-size:12px;white-space:nowrap}.detail-map :deep(.map-frame){height:100%;border-radius:0}.metric-list{min-width:0;display:grid;gap:10px}.metric-box{width:100%;min-width:0;height:320px;padding:16px 18px;border-radius:17px;overflow:hidden}.fullscreen .detail-content{overflow:hidden;display:grid;grid-template-rows:clamp(260px,38vh,360px) minmax(0,1fr);gap:8px;padding:9px}.fullscreen .fixed-overview{height:auto;min-width:0;min-height:0;margin:0;grid-template-columns:var(--summary-width,220px) minmax(0,1fr)}.fullscreen .fixed-stats{padding:16px}.fullscreen .fixed-stats h2{font-size:17px}.fullscreen .primary-metric{margin:12px 0 9px}.fullscreen .metric-list{width:100%;min-width:0;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:repeat(3,minmax(0,1fr));grid-auto-flow:row;gap:7px;overflow:hidden}.fullscreen .metric-box{width:100%;height:auto;min-width:0;min-height:0;padding:9px 10px;border-radius:12px;overflow:hidden}.detail-fade-enter-active,.detail-fade-leave-active{transition:opacity .2s}.detail-fade-enter-active .detail-modal,.detail-fade-leave-active .detail-modal{transition:transform .2s,opacity .2s}.detail-fade-enter-from,.detail-fade-leave-to{opacity:0}.detail-fade-enter-from .detail-modal,.detail-fade-leave-to .detail-modal{transform:scale(.97);opacity:0}@media(max-width:850px){.detail-modal{width:94vw;height:90vh}.fixed-overview{grid-template-columns:1fr!important;height:auto}.fixed-stats{min-height:230px}.detail-map{height:290px}.fullscreen .metric-list{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:none;overflow:auto}.fullscreen .detail-content{overflow:auto;display:block}.fullscreen .fixed-overview{height:auto;margin-bottom:8px}}
/* Fullscreen is an analysis workspace: a compact overview followed by readable,
   scrollable charts. Relative units keep the composition balanced across screens. */
.fullscreen .detail-content{
  display:block;
  overflow-y:auto;
  padding:clamp(.55rem,1vw,.9rem);
  scrollbar-gutter:stable;
}
.fullscreen .fixed-overview,
.fullscreen .metric-list{
  width:min(100%,140rem);
  margin-inline:auto;
}
.fullscreen .fixed-overview{
  height:clamp(17rem,32vh,21rem);
  min-width:0;
  min-height:0;
  margin-bottom:clamp(.55rem,1vw,.9rem);
  grid-template-columns:var(--summary-width,clamp(15rem,20vw,19rem)) minmax(0,1fr);
}
.activity-insights{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:clamp(.5rem,.8vw,.75rem);margin:0 0 clamp(.55rem,1vw,.9rem)}.activity-insights article{min-width:0;padding:.8rem 1rem;border-radius:.9rem}.activity-insights span,.activity-insights strong,.activity-insights small{display:block}.activity-insights span{color:var(--muted);font-size:.52rem}.activity-insights strong{margin:.25rem 0;font-size:.9rem}.activity-insights small{color:var(--muted);font-size:.48rem}.fullscreen .activity-insights{width:min(100%,140rem);margin-inline:auto;margin-bottom:clamp(.55rem,1vw,.9rem)}
.fullscreen .fixed-stats{padding:clamp(1rem,1.4vw,1.45rem)}
.fullscreen .fixed-stats h2{font-size:clamp(1.05rem,1.15vw,1.3rem)}
.fullscreen .primary-metric{margin:clamp(.75rem,1.3vh,1rem) 0 clamp(.55rem,1vh,.8rem)}
.fullscreen .metric-list{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  grid-template-rows:none;
  gap:clamp(.55rem,1vw,.9rem);
  overflow:visible;
}
.fullscreen .metric-box{
  width:100%;
  height:clamp(18rem,34vh,23rem);
  min-width:0;
  min-height:0;
  padding:clamp(.75rem,1vw,1.1rem);
  border-radius:clamp(.75rem,1vw,1.05rem);
  overflow:hidden;
}
.fullscreen .metric-box:last-child:nth-child(odd){grid-column:1/-1}

@media(max-width:850px){
  .fixed-stats{min-height:14rem}
  .detail-map{height:18rem}
  .fullscreen .fixed-overview{height:auto;margin-bottom:.6rem}
  .fullscreen .metric-list{grid-template-columns:1fr;overflow:visible}
  .fullscreen .metric-box:last-child:nth-child(odd){grid-column:auto}
  .activity-insights{grid-template-columns:1fr 1fr}
}

.settings-section .el-checkbox-group{flex-wrap:wrap;gap:.4rem 1rem}
.axis-settings{margin-bottom:.8rem;padding-bottom:.8rem;border-bottom:1px solid var(--line)}.axis-settings .el-segmented{width:100%;margin-top:.55rem;--el-segmented-bg-color:rgba(127,142,164,.1);--el-segmented-item-selected-bg-color:rgba(var(--accent-rgb),.14);--el-segmented-item-selected-color:var(--text)}
.zone-settings{margin-bottom:.8rem;padding-bottom:.8rem;border-bottom:1px solid var(--line)}.zone-editor-toggle{width:100%;display:flex;align-items:center;justify-content:space-between;padding:0;border:0;color:var(--text);background:none;text-align:left;cursor:pointer}.zone-editor-toggle span strong,.zone-editor-toggle span small{display:block}.zone-editor-toggle span strong{font-size:.68rem}.zone-editor-toggle span small{margin-top:.18rem;color:var(--muted);font-size:.5rem;font-weight:400}.zone-editor-toggle b{color:var(--accent);font-size:.55rem}.zone-editor{margin-top:.65rem}.zone-editor-head,.zone-row{display:grid;grid-template-columns:5.2rem minmax(0,1fr) minmax(0,1fr);align-items:center;gap:.35rem}.zone-editor-head{padding:0 .15rem .25rem;color:var(--muted);font-size:.46rem}.zone-row{padding:.28rem .15rem;border-top:1px solid var(--line)}.zone-row>span{display:flex;align-items:center;gap:.28rem;font-size:.5rem;white-space:nowrap}.zone-row>span i{width:.48rem;height:.48rem;border-radius:50%}.zone-row label{display:flex;align-items:center;gap:.16rem;min-width:0}.zone-row label em{color:var(--muted);font-size:.5rem;font-style:normal}.zone-row :deep(.el-input__wrapper){min-width:0;padding:0 .3rem;border-radius:.4rem;background:rgba(127,142,164,.08);box-shadow:0 0 0 1px var(--line) inset}.zone-row :deep(.el-input__inner){height:1.45rem;font-size:.5rem}.zone-editor>p{margin:.4rem .15rem 0;color:var(--muted);font-size:.46rem;line-height:1.5}
.chart-settings{width:min(24rem,calc(100vw - 3rem))}
.chart-settings{max-height:calc(100vh - 5.5rem);overflow-y:auto;scrollbar-gutter:stable}.chart-settings ul{max-height:11.25rem}
.fixed-stats{overflow-y:auto}
.fixed-overview.metrics-expanded .secondary-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}
.fixed-overview.metrics-expanded .secondary-metrics strong{font-size:clamp(.68rem,.85vw,.82rem)}
.fullscreen .fixed-overview{
  height:clamp(32rem,64vh,42rem);
}
@media(max-width:850px){
  .fixed-overview.metrics-expanded .secondary-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
  .fullscreen .fixed-overview{height:auto}
}
</style>
