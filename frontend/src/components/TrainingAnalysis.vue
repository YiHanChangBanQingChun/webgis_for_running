<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import RangeAnalysisChart from './RangeAnalysisChart.vue'

// interface = 前端开发者与数据之间的“约定”
interface DailyPoint { date: string; activity_count: number; distance_m: number; elapsed_s: number; relative_load: number; load_7d: number; load_28d: number; load_ratio: number | null }
interface WeeklyPoint { week: string; activity_count: number; distance_m: number; elapsed_s: number; relative_load: number }
interface RangeResult {
  start: string; end: string
  summary: { activity_count: number; active_days: number; total_distance_m: number; total_elapsed_s: number; total_ascent_m: number; calories: number; average_pace_s_per_km: number | null; average_distance_m: number | null; load_ratio: number | null; load_status: string }
  daily: DailyPoint[]; weekly: WeeklyPoint[]; load_note: string
}
const props = defineProps<{ dark: boolean; latestDate?: string | null }>()
const loading = ref(false)
const preset = ref(90)
const result = ref<RangeResult | null>(null)
const dates = ref<[string, string]>(['', ''])

function shiftDate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`); date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
function usePreset(days: number): void {
  preset.value = days
  const end = props.latestDate || new Date().toISOString().slice(0, 10)
  dates.value = [shiftDate(end, -(days - 1)), end]
  load()
}
function formatKm(value?: number | null): string { return value == null ? '—' : `${(value / 1000).toFixed(1)} km` }
function formatDuration(value?: number | null): string {
  if (!value) return '—'
  const hours = Math.floor(value / 3600); const minutes = Math.round(value % 3600 / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes} min`
}
function formatPace(value?: number | null): string {
  if (!value) return '—'
  return `${Math.floor(value / 60)}′${String(Math.round(value % 60)).padStart(2, '0')}″`
}
const loadMessage = computed(() => {
  const status = result.value?.summary.load_status
  const messages: Record<string, { title: string; text: string; tone: string }> = {
    recovery: { title: '近期负荷偏低', text: '近期训练量低于过去四周基线，可结合状态安排恢复或平稳回归。', tone: 'blue' },
    balanced: { title: '负荷处于稳定区间', text: '短期训练量与个人近期基线接近，节奏相对平稳。', tone: 'green' },
    rising: { title: '训练负荷正在上升', text: '最近 7 日负荷高于近期基线，建议留意睡眠、疲劳和轻松跑比例。', tone: 'orange' },
    high: { title: '近期增量较快', text: '短期训练负荷显著高于过去四周水平，下一次训练宜优先考虑恢复。', tone: 'red' },
    insufficient: { title: '数据仍在积累', text: '当前范围内训练数据不足，暂时无法判断负荷变化。', tone: 'gray' },
  }
  return messages[status || 'insufficient']
})
async function load(): Promise<void> {
  if (!dates.value[0] || !dates.value[1]) return
  loading.value = true
  try {
    const query = new URLSearchParams({ start: dates.value[0], end: dates.value[1] })
    const response = await fetch(`/api/stats/range?${query}`)
    if (!response.ok) throw new Error('range stats unavailable')
    result.value = await response.json() as RangeResult
  } catch { ElMessage.error('训练分析读取失败，请确认 FastAPI 已更新并正常运行。') }
  finally { loading.value = false }
}
function handleDateChange(): void { preset.value = 0; load() }
watch(() => props.latestDate, (value) => { if (value && !dates.value[1]) usePreset(90) })
onMounted(() => usePreset(90))
</script>

<template>
  <section class="analysis-page" v-loading="loading">
    <div class="analysis-heading">
      <div><p class="eyebrow">TRAINING RHYTHM</p><h2>训练分析</h2><span>用自己的近期基线观察训练量变化</span></div>
      <div class="analysis-controls glass-card">
        <el-segmented :model-value="preset" :options="[{ label: '30 天', value: 30 }, { label: '90 天', value: 90 }, { label: '半年', value: 180 }, { label: '一年', value: 365 }]" @change="usePreset" />
        <el-date-picker v-model="dates" type="daterange" value-format="YYYY-MM-DD" range-separator="—" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" @change="handleDateChange" />
      </div>
    </div>

    <div class="analysis-stats">
      <article class="glass-card"><span>总里程</span><strong>{{ formatKm(result?.summary.total_distance_m) }}</strong><small>DISTANCE</small></article>
      <article class="glass-card"><span>训练时长</span><strong>{{ formatDuration(result?.summary.total_elapsed_s) }}</strong><small>DURATION</small></article>
      <article class="glass-card"><span>活动 / 天数</span><strong>{{ result?.summary.activity_count ?? 0 }} / {{ result?.summary.active_days ?? 0 }}</strong><small>SESSIONS</small></article>
      <article class="glass-card"><span>累计爬升</span><strong>{{ result ? `${result.summary.total_ascent_m.toFixed(0)} m` : '—' }}</strong><small>ASCENT</small></article>
      <article class="glass-card"><span>整体配速</span><strong>{{ formatPace(result?.summary.average_pace_s_per_km) }}</strong><small>AVG PACE</small></article>
    </div>

    <div class="analysis-workspace">
      <article class="analysis-chart-card glass-card"><div class="panel-heading"><div><p class="eyebrow">WEEKLY VOLUME</p><h3>周训练里程</h3></div><span class="panel-note">{{ result?.weekly.length || 0 }} 周</span></div><RangeAnalysisChart :daily="result?.daily || []" :weekly="result?.weekly || []" :dark="dark" mode="volume" /></article>
      <div class="analysis-side">
        <article class="load-card glass-card"><div class="panel-heading"><div><p class="eyebrow">LOAD SIGNAL</p><h3>近期负荷判断</h3></div><strong v-if="result?.summary.load_ratio">{{ result.summary.load_ratio.toFixed(2) }}×</strong></div><div class="load-message" :class="loadMessage.tone"><i></i><div><strong>{{ loadMessage.title }}</strong><span>{{ loadMessage.text }}</span></div></div><small>{{ result?.load_note }}</small></article>
        <article class="analysis-chart-card compact glass-card"><div class="panel-heading"><div><p class="eyebrow">ROLLING LOAD</p><h3>7 / 28 日负荷曲线</h3></div></div><RangeAnalysisChart :daily="result?.daily || []" :weekly="result?.weekly || []" :dark="dark" mode="load" /></article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.analysis-page{height:100%;display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:clamp(.6rem,1vw,.85rem)}.analysis-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.analysis-heading .eyebrow{margin:0 0 .25rem;color:var(--accent)}.analysis-heading h2{display:inline;margin:0 .6rem 0 0;font-size:1.35rem}.analysis-heading span{color:var(--muted);font-size:.65rem}.analysis-controls{display:flex;align-items:center;gap:.55rem;padding:.4rem;border-radius:.9rem}.analysis-controls .el-date-editor{width:clamp(15rem,25vw,21rem)}.analysis-stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem}.analysis-stats article{min-width:0;padding:.75rem 1rem;border-radius:.95rem}.analysis-stats span,.analysis-stats strong,.analysis-stats small{display:block}.analysis-stats span{color:var(--muted);font-size:.62rem}.analysis-stats strong{margin:.25rem 0;font-size:clamp(.95rem,1.5vw,1.25rem);letter-spacing:-.04em}.analysis-stats small{color:var(--accent);font-family:"DM Mono",monospace;font-size:.45rem;letter-spacing:.1em}.analysis-workspace{min-height:0;display:grid;grid-template-columns:minmax(0,1.2fr) minmax(20rem,.8fr);gap:.65rem}.analysis-chart-card,.load-card{min-height:0;padding:1rem 1.1rem;border-radius:1.05rem}.analysis-chart-card{display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden}.analysis-side{min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);gap:.65rem}.load-card .panel-heading strong{font-size:1.3rem;color:var(--accent)}.load-message{display:flex;gap:.7rem;align-items:flex-start;padding:.75rem;border-radius:.8rem;background:rgba(127,142,164,.08)}.load-message i{width:.55rem;height:.55rem;flex:0 0 auto;margin-top:.15rem;border-radius:50%;background:#8995a8}.load-message.green i{background:#47bd7a}.load-message.orange i{background:#ff9138}.load-message.red i{background:#ff5f57}.load-message.blue i{background:#5289e8}.load-message strong,.load-message span{display:block}.load-message strong{font-size:.72rem}.load-message span{margin-top:.25rem;color:var(--muted);font-size:.56rem;line-height:1.55}.load-card>small{display:block;margin-top:.5rem;color:var(--muted);font-size:.48rem}.compact{padding-bottom:.55rem}@media(max-width:1000px){.analysis-heading span{display:none}.analysis-workspace{grid-template-columns:1fr}.analysis-side{display:none}.analysis-stats{grid-template-columns:repeat(3,1fr)}.analysis-stats article:nth-child(n+4){display:none}}@media(max-width:760px){.analysis-heading{align-items:flex-start;flex-direction:column}.analysis-controls{width:100%;flex-wrap:wrap}.analysis-controls .el-date-editor{width:100%}.analysis-stats{grid-template-columns:1fr 1fr}.analysis-workspace{min-height:28rem}}
</style>
