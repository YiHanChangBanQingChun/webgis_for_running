<script setup lang="ts">
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface DailyPoint { date: string; distance_m: number; relative_load: number; load_7d: number; load_28d: number }
interface WeeklyPoint { week: string; distance_m: number; relative_load: number }
const props = defineProps<{ daily: DailyPoint[]; weekly: WeeklyPoint[]; dark: boolean; mode: 'volume' | 'load' }>()
const container = ref<HTMLElement>()
let chart: echarts.ECharts | undefined

function palette() {
  return { text: props.dark ? '#9ca9bd' : '#738096', line: props.dark ? '#2c3648' : '#e4e9f0', tooltip: props.dark ? 'rgba(20,29,43,.92)' : 'rgba(255,255,255,.92)' }
}
function render(): void {
  if (!container.value) return
  chart ??= echarts.init(container.value)
  const colors = palette()
  const base = {
    animationDuration: 450,
    grid: { left: 12, right: 14, top: 34, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: colors.tooltip, borderColor: props.dark ? '#3a465a' : '#fff', textStyle: { color: props.dark ? '#f4f7fb' : '#182033', fontSize: 10 }, extraCssText: 'backdrop-filter:blur(14px);border-radius:10px;box-shadow:0 10px 30px rgba(15,25,40,.18)' },
    legend: { top: 0, right: 4, textStyle: { color: colors.text, fontSize: 9 }, itemWidth: 14, itemHeight: 6 },
  }
  if (props.mode === 'volume') {
    chart.setOption({ ...base,
      xAxis: { type: 'category', data: props.weekly.map((item) => item.week.slice(5)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: colors.text, fontSize: 9 } },
      yAxis: { type: 'value', name: 'km', nameTextStyle: { color: colors.text }, axisLabel: { color: colors.text, fontSize: 9 }, splitLine: { lineStyle: { color: colors.line } } },
      series: [{ name: '周里程', type: 'bar', barMaxWidth: 28, data: props.weekly.map((item) => +(item.distance_m / 1000).toFixed(1)), itemStyle: { color: '#ff6b35', borderRadius: [6, 6, 2, 2] }, emphasis: { itemStyle: { color: '#ff8c61' } } }],
    }, true)
  } else {
    chart.setOption({ ...base,
      xAxis: { type: 'category', boundaryGap: false, data: props.daily.map((item) => item.date.slice(5)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: colors.text, fontSize: 8, interval: Math.max(0, Math.ceil(props.daily.length / 9) - 1) } },
      yAxis: { type: 'value', axisLabel: { color: colors.text, fontSize: 9 }, splitLine: { lineStyle: { color: colors.line } } },
      series: [
        { name: '7 日负荷', type: 'line', smooth: .28, symbol: 'none', data: props.daily.map((item) => item.load_7d), lineStyle: { color: '#ff6b35', width: 3 }, areaStyle: { color: props.dark ? 'rgba(255,107,53,.16)' : 'rgba(255,107,53,.10)' } },
        { name: '28 日负荷', type: 'line', smooth: .28, symbol: 'none', data: props.daily.map((item) => item.load_28d), lineStyle: { color: '#5289e8', width: 2, type: 'dashed' } },
      ],
    }, true)
  }
}

const observer = new ResizeObserver(() => chart?.resize())
onMounted(async () => { await nextTick(); render(); if (container.value) observer.observe(container.value) })
watch(() => [props.daily, props.weekly, props.dark, props.mode], render, { deep: true })
onBeforeUnmount(() => { observer.disconnect(); chart?.dispose() })
</script>

<template><div ref="container" class="range-chart"></div></template>
<style scoped>.range-chart{width:100%;height:100%;min-height:12rem}</style>
