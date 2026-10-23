<script setup lang="ts">
// 这个无界面组件负责把每日里程数据绘制成 ECharts 折线图。
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface CalendarRow {
  date: string
  distance_m: number
}
// 父组件传入数据和当前主题，主题变化时图表颜色也会同步更新。
const props = defineProps<{ rows: CalendarRow[]; dark: boolean }>()
const container = ref<HTMLElement>()
// 图表实例只初始化一次；后续数据或主题变化通过 setOption 更新。
let chart: echarts.ECharts | undefined

function render(): void {
  if (!container.value) return
  // ECharts 只创建一次，后续调用 setOption 更新同一个实例。
  chart ??= echarts.init(container.value)
  const rows = props.rows
  chart.setOption(
    {
      grid: { left: 6, right: 8, top: 22, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        data: rows.map((row) => String(Number(row.date.slice(-2)))),
        axisLabel: {
          color: props.dark ? '#8e9aaf' : '#788399',
          fontSize: 9,
          interval: Math.max(0, Math.ceil(rows.length / 7) - 1),
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        splitNumber: 3,
        axisLabel: { color: props.dark ? '#8e9aaf' : '#788399', formatter: '{value}k' },
        splitLine: { lineStyle: { color: props.dark ? '#2c3648' : '#e9edf3' } },
      },
      series: [
        {
          type: 'line',
          smooth: true,
          symbol: 'none',
          data: rows.map((row) => +(row.distance_m / 1000).toFixed(1)),
          lineStyle: { color: '#ff6b35', width: 3 },
          areaStyle: { color: props.dark ? 'rgba(255,107,53,.22)' : 'rgba(255,107,53,.13)' },
        },
      ],
      tooltip: { trigger: 'axis', valueFormatter: (value: number) => `${value} km` },
    },
    true,
  )
}

const observer = new ResizeObserver(() => chart?.resize())
onMounted(async () => {
  await nextTick()
  render()
  if (container.value) observer.observe(container.value)
})
// 深度监听数组内容，保证接口刷新后图表立即重绘。
watch(() => [props.rows, props.dark], render, { deep: true })
// 组件销毁时释放 ResizeObserver 和 ECharts 实例。
onBeforeUnmount(() => {
  observer.disconnect()
  chart?.dispose()
})
</script>

<template><div ref="container" class="trend-chart"></div></template>

<style scoped>
.trend-chart {
  height: 100%;
  min-height: 128px;
  width: 100%;
}
</style>
