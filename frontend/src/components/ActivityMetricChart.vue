<script setup lang="ts">
// 单项运动指标图表：支持配速、心率、步频等曲线，以及缩放和地图位置联动。
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface Point {
  x: number
  y: number | null
  distanceKm: number
}
interface ZoneBand {
  label: string
  shortLabel: string
  min?: number
  max?: number
  color: string
}
interface ReferenceLine {
  label: string
  value: number
  color: string
}

const props = defineProps<{
  title: string
  subtitle: string
  unit: string
  points: Point[]
  chartType: 'line' | 'scatter'
  dark: boolean
  pace?: boolean
  cursorDistanceKm?: number | null
  xAxisMode: 'distance' | 'time'
  zones?: ZoneBand[]
  zoneNote?: string
  referenceLine?: ReferenceLine | null
  yAxisDecimals?: number
}>()
const emit = defineEmits<{ seek: [distanceKm: number] }>()
const container = ref<HTMLElement>()
let chart: echarts.ECharts | undefined
let renderedPoints: Point[] = []
let renderedAxisMaximum = 0

const legendItems = computed(() => {
  // 将区间背景和参考线整理为图例，供模板显示。
  const items = props.zones?.map((zone) => ({ label: zone.shortLabel, color: zone.color })) ?? []
  if (props.referenceLine)
    items.push({ label: props.referenceLine.label, color: props.referenceLine.color })
  return items
})

function paceLabel(decimalMinutes: number): string {
  let minutes = Math.floor(decimalMinutes)
  let seconds = Math.round((decimalMinutes - minutes) * 60)
  if (seconds === 60) {
    minutes += 1
    seconds = 0
  }
  return `${minutes}′${String(seconds).padStart(2, '0')}″`
}
function timeLabel(minutes: number): string {
  const totalSeconds = Math.max(0, Math.round(minutes * 60))
  const hours = Math.floor(totalSeconds / 3600)
  const minutePart = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return hours
    ? `${hours}:${String(minutePart).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${minutePart}:${String(seconds).padStart(2, '0')}`
}
function horizontalLabel(value: number): string {
  return props.xAxisMode === 'time' ? timeLabel(value) : `${value.toFixed(2)} km`
}

function yAxisBounds(points: Point[]): { min: number; max: number } | null {
  const values = points
    .map((point) => point.y)
    .filter((value): value is number => value != null && Number.isFinite(value))
  if (!values.length) return null
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const padding = Math.max((maximum - minimum) * 0.08, props.pace ? 0.08 : 0.5)
  return { min: minimum - padding, max: maximum + padding }
}

function updateYAxisForZoom(startPercent = 0, endPercent = 100): void {
  if (!chart || !renderedPoints.length || !renderedAxisMaximum) return
  const startValue = (renderedAxisMaximum * startPercent) / 100
  const endValue = (renderedAxisMaximum * endPercent) / 100
  // 缩放横轴后，用当前可见点重新计算纵轴范围，避免曲线被压扁。
  const visible = renderedPoints.filter((point) => point.x >= startValue && point.x <= endValue)
  const bounds = yAxisBounds(visible)
  if (bounds)
    chart.setOption({ yAxis: { min: bounds.min, max: bounds.max, inverse: Boolean(props.pace) } })
}

function render(): void {
  // 根据当前指标、主题和区间配置生成 ECharts 选项。
  if (!container.value) return
  chart ??= echarts.init(container.value)
  const valid = props.points.filter((point) => point.y != null && Number.isFinite(point.y))
  const axisMaximum = valid.at(-1)?.x
  renderedPoints = valid
  renderedAxisMaximum = axisMaximum ?? 0
  const values = valid.map((point) => point.y as number)
  const dataMin = Math.min(...values)
  const dataMax = Math.max(...values)
  const zoneBounds = (props.zones ?? [])
    .flatMap((zone) => [zone.min, zone.max])
    .filter((value): value is number => value != null)
  const visibleMin = Math.min(dataMin, ...zoneBounds)
  const visibleMax = Math.max(dataMax, ...zoneBounds)
  const padding = Math.max((visibleMax - visibleMin) * 0.06, 0.5)
  const markArea = props.zones?.length
    ? {
        silent: true,
        label: { show: false },
        data: props.zones.map((zone) => [
          {
            name: zone.label,
            yAxis: zone.min ?? visibleMin - padding,
            itemStyle: { color: zone.color },
          },
          { yAxis: zone.max ?? visibleMax + padding },
        ]),
      }
    : undefined
  const markLine = props.referenceLine
    ? {
        silent: true,
        symbol: 'none',
        label: {
          show: true,
          position: 'insideEndTop',
          formatter: props.referenceLine.label,
          color: props.dark ? '#eef3fb' : '#354052',
          fontSize: 8,
        },
        lineStyle: { color: props.referenceLine.color, width: 1.4, type: 'dashed' },
        data: [{ yAxis: props.referenceLine.value }],
      }
    : undefined
  const metricSeries = {
    type: props.chartType,
    data: valid.map((point) => [point.x, point.y, point.distanceKm]),
    showSymbol: props.chartType === 'scatter',
    symbolSize: props.chartType === 'scatter' ? 3 : 0,
    sampling: props.chartType === 'line' ? 'lttb' : undefined,
    lineStyle: { color: '#ff6b35', width: 2 },
    itemStyle: { color: '#ff6b35', opacity: props.chartType === 'scatter' ? 0.5 : 1 },
    ...(props.chartType === 'line'
      ? { areaStyle: { color: props.dark ? 'rgba(255,107,53,.10)' : 'rgba(255,107,53,.07)' } }
      : {}),
    ...(markArea ? { markArea } : {}),
    ...(markLine ? { markLine } : {}),
  }

  chart.setOption(
    {
      animationDuration: 420,
      grid: {
        left: 8,
        right: 14,
        top: props.referenceLine ? 25 : 18,
        bottom: 28,
        containLabel: true,
      },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: props.dark ? 'rgba(18,27,41,.88)' : 'rgba(255,255,255,.82)',
        borderColor: props.dark ? 'rgba(255,255,255,.14)' : 'rgba(255,255,255,.86)',
        borderWidth: 1,
        textStyle: { color: props.dark ? '#f4f7fb' : '#182033', fontSize: 10 },
        extraCssText:
          'backdrop-filter:blur(16px) saturate(145%);-webkit-backdrop-filter:blur(16px) saturate(145%);border-radius:10px;box-shadow:0 10px 30px rgba(15,25,40,.18);',
        formatter: (items: Array<{ value: [number, number, number] }>) => {
          const item = items[0]
          return item
            ? `${horizontalLabel(item.value[0])}<br><b>${props.pace ? paceLabel(item.value[1]) : item.value[1].toFixed(props.yAxisDecimals ?? 1)} ${props.unit}</b>`
            : ''
        },
      },
      xAxis: {
        type: 'value',
        min: 0,
        max: axisMaximum,
        name: props.xAxisMode === 'time' ? '时间' : 'km',
        nameTextStyle: { color: props.dark ? '#8491a6' : '#8b96a8', fontSize: 8 },
        axisLabel: {
          color: props.dark ? '#8491a6' : '#8b96a8',
          fontSize: 8,
          formatter: (value: number) =>
            props.xAxisMode === 'time' ? timeLabel(value) : `${+value.toFixed(1)}`,
        },
        axisPointer: {
          label: { formatter: (params: { value: number }) => horizontalLabel(params.value) },
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: 0,
          filterMode: 'none',
          zoomOnMouseWheel: true,
          moveOnMouseMove: true,
          moveOnMouseWheel: false,
        },
        {
          type: 'slider',
          xAxisIndex: 0,
          filterMode: 'none',
          height: 11,
          bottom: 2,
          borderColor: 'transparent',
          backgroundColor: props.dark ? 'rgba(255,255,255,.055)' : 'rgba(63,78,102,.07)',
          fillerColor: props.dark ? 'rgba(255,107,53,.20)' : 'rgba(255,107,53,.16)',
          dataBackground: {
            lineStyle: {
              color: props.dark ? 'rgba(171,183,201,.30)' : 'rgba(90,105,128,.28)',
              width: 0.7,
            },
            areaStyle: { color: props.dark ? 'rgba(171,183,201,.08)' : 'rgba(90,105,128,.07)' },
          },
          selectedDataBackground: {
            lineStyle: { color: 'rgba(255,107,53,.65)', width: 0.8 },
            areaStyle: { color: 'rgba(255,107,53,.10)' },
          },
          handleSize: '145%',
          handleStyle: {
            color: props.dark ? '#c8d0dc' : '#ffffff',
            borderColor: props.dark ? 'rgba(255,255,255,.26)' : 'rgba(72,88,112,.22)',
            borderWidth: 1,
            shadowBlur: 4,
            shadowColor: 'rgba(16,24,38,.18)',
          },
          moveHandleSize: 0,
          showDetail: false,
          brushSelect: false,
        },
      ],
      yAxis: {
        type: 'value',
        scale: true,
        inverse: Boolean(props.pace),
        min: null,
        max: null,
        axisLabel: {
          color: props.dark ? '#8491a6' : '#8b96a8',
          fontSize: 8,
          formatter: (value: number) =>
            props.pace ? paceLabel(value) : value.toFixed(props.yAxisDecimals ?? 0),
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: {
          lineStyle: { color: props.dark ? 'rgba(255,255,255,.07)' : 'rgba(70,88,114,.10)' },
        },
      },
      series: [metricSeries],
    },
    true,
  )
  // render 会多次执行；先解绑再绑定，防止 ECharts 事件处理器重复累加。
  chart.off('updateAxisPointer')
  chart.off('datazoom')
  chart.on('datazoom', (event: unknown) => {
    const payload = event as {
      start?: number
      end?: number
      batch?: Array<{ start?: number; end?: number }>
    }
    const range = payload.batch?.[0] ?? payload
    updateYAxisForZoom(range.start ?? 0, range.end ?? 100)
  })
  chart.on('updateAxisPointer', (event: unknown) => {
    const payload = event as { axesInfo?: Array<{ value?: number }> }
    const value = payload.axesInfo?.[0]?.value
    if (typeof value === 'number' && Number.isFinite(value)) {
      let nearest = valid[0]
      for (const point of valid)
        if (!nearest || Math.abs(point.x - value) < Math.abs(nearest.x - value)) nearest = point
      if (nearest) emit('seek', nearest.distanceKm)
    }
  })
  updateCursor()
}

function updateCursor(): void {
  if (!chart || props.cursorDistanceKm == null || !props.points.length) return
  // 地图回放和多张指标图共享距离光标，因此按距离找最近的有效数据点。
  const valid = props.points.filter((point) => point.y != null && Number.isFinite(point.y))
  let nearestIndex = 0
  let difference = Number.POSITIVE_INFINITY
  valid.forEach((point, index) => {
    const nextDifference = Math.abs(point.distanceKm - props.cursorDistanceKm!)
    if (nextDifference < difference) {
      difference = nextDifference
      nearestIndex = index
    }
  })
  chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: nearestIndex })
}

const observer = new ResizeObserver(() => chart?.resize())
// 首次挂载后初始化图表，并观察容器尺寸变化。
onMounted(async () => {
  await nextTick()
  render()
  if (container.value) observer.observe(container.value)
})
watch(
  () => [
    props.points,
    props.dark,
    props.chartType,
    props.xAxisMode,
    props.zones,
    props.referenceLine,
  ],
  render,
  { deep: true },
)
watch(() => props.cursorDistanceKm, updateCursor)
// 离开详情弹窗时释放图表和尺寸监听器。
onBeforeUnmount(() => {
  observer.disconnect()
  chart?.dispose()
})
defineExpose({ resize: () => chart?.resize() })
</script>

<template>
  <div class="metric-chart-shell" :class="{ 'has-zone-legend': legendItems.length > 0 }">
    <div class="metric-title">
      <div>
        <strong>{{ title }}</strong>
        <span>{{ subtitle }}</span>
      </div>
      <small>{{ unit }}</small>
    </div>
    <div v-if="legendItems.length" class="zone-legend" :title="zoneNote">
      <span v-for="item in legendItems" :key="item.label">
        <i :style="{ background: item.color }"></i>
        {{ item.label }}
      </span>
      <em v-if="zoneNote">ⓘ</em>
    </div>
    <div ref="container" class="metric-chart"></div>
  </div>
</template>

<style scoped>
.metric-chart-shell {
  width: 100%;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}
.metric-chart-shell.has-zone-legend {
  grid-template-rows: auto auto minmax(0, 1fr);
}
.metric-title {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.metric-title strong,
.metric-title span {
  display: block;
}
.metric-title strong {
  font-size: 12px;
}
.metric-title span,
.metric-title small {
  margin-top: 3px;
  color: var(--muted);
  font-size: 8px;
}
.zone-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.18rem 0.48rem;
  min-height: 1.15rem;
  padding-top: 0.2rem;
  color: var(--muted);
  font-size: 0.46rem;
}
.zone-legend span {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  white-space: nowrap;
}
.zone-legend i {
  width: 0.48rem;
  height: 0.28rem;
  border-radius: 0.15rem;
  border: 1px solid rgba(127, 142, 164, 0.16);
}
.zone-legend em {
  font-style: normal;
  opacity: 0.7;
  cursor: help;
}
.metric-chart {
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>
