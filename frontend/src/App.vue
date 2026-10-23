<script setup lang="ts">
// `script setup` 中声明的变量和函数可以直接在下面的模板中使用。
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchAllActivities } from './activityApi'
import DistanceTrend from './components/DistanceTrend.vue'
import ActivityExplorer from './components/ActivityExplorer.vue'
import ActivityDetailModal from './components/ActivityDetailModal.vue'
import TrainingAnalysis from './components/TrainingAnalysis.vue'
import MapExplorer from './components/MapExplorer.vue'

// Cesium 体积较大，只有切换到区域探索时才加载，避免拖慢首页的首次加载。
const RegionExplorer = defineAsyncComponent(() => import('./components/RegionExplorer.vue'))

// 用联合类型限制主题和页面的可选值，避免传入拼写错误的字符串。
type ThemePreference = 'system' | 'light' | 'dark'
type View = 'overview' | 'activities' | 'analysis' | 'map' | 'region'

// 一条活动记录的字段类型，与后端返回的数据结构对应。
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

// 日历中某一天的汇总数据。
interface CalendarRow {
  date: string
  activity_count: number
  distance_m: number
  elapsed_s: number
}

// 后端健康检查和数据覆盖范围。
interface QualityReport {
  readiness: { api_ready: boolean }
  data_coverage: {
    activities_with_gps: number
    date_range: { start: string | null; end: string | null }
  }
}

// 日历网格中的一个格子，包含本月日期和上、下月的占位格。
interface CalendarCell {
  date: string
  day: number
  data: CalendarRow | null
  outside: boolean
}

// 某个月的统计结果。
interface MonthlyStats {
  month: string
  activity_count: number
  active_days: number
  total_distance_m: number
  total_elapsed_s: number
  average_distance_m: number | null
  average_pace_s_per_km: number | null
  total_ascent_m: number
  activities_with_gps: number
}

// 保存用户的主题选择，而不是最终显示的颜色；选择 system 时会跟随系统变化。
const savedTheme =
  localStorage.getItem('running-webgis-theme-preference') ||
  localStorage.getItem('running-webgis-theme')
const themePreference = ref<ThemePreference>(
  savedTheme === 'light' || savedTheme === 'dark' ? savedTheme : 'system',
)
// 读取浏览器当前的系统深色模式。
const systemDark = ref(window.matchMedia('(prefers-color-scheme: dark)').matches)
// `computed` 会根据用户选择和系统主题自动计算最终主题。
const resolvedTheme = computed(() =>
  themePreference.value === 'system'
    ? systemDark.value
      ? 'dark'
      : 'light'
    : themePreference.value,
)
// `ref` 创建响应式状态；状态变化后，使用它的模板会自动重新渲染。
const activeView = ref<View>('overview')
const activities = ref<Activity[]>([])
const calendar = ref<CalendarRow[]>([])
const report = ref<QualityReport | null>(null)
const selectedActivity = ref<Activity | null>(null)
const drawerOpen = ref(false)
const dayDialogOpen = ref(false)
const selectedDay = ref('')
const dayActivities = ref<Activity[]>([])
const dayLoading = ref(false)
const monthlyStats = ref<MonthlyStats | null>(null)
const loading = ref(false)
const apiError = ref(false)
const selectedMonth = ref(
  `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`,
)

// 把最终主题同步到 HTML 根元素，CSS 可以据此切换颜色。
watch(
  resolvedTheme,
  (value) => {
    document.documentElement.dataset.theme = value
    document.documentElement.classList.toggle('dark', value === 'dark')
  },
  { immediate: true },
)
// 每次主题选择变化时写入 localStorage，让刷新页面后仍保留选择。
watch(
  themePreference,
  (value) => {
    localStorage.setItem('running-webgis-theme-preference', value)
  },
  { immediate: true },
)

// 以下计算属性从当前状态派生出页面展示需要的数据。
const monthRows = computed(() =>
  calendar.value.filter((item) => item.date.startsWith(selectedMonth.value)),
)
const monthActivities = computed(() =>
  activities.value.filter((item) => item.date?.startsWith(selectedMonth.value)).slice(0, 5),
)
const monthDistance = computed(() =>
  monthRows.value.reduce((sum, item) => sum + item.distance_m, 0),
)
const monthDuration = computed(() => monthRows.value.reduce((sum, item) => sum + item.elapsed_s, 0))
const monthRunCount = computed(() =>
  monthRows.value.reduce((sum, item) => sum + item.activity_count, 0),
)
const monthActiveDays = computed(() => monthRows.value.filter((item) => item.distance_m > 0).length)
const displayMonthDistance = computed(
  () => monthlyStats.value?.total_distance_m ?? monthDistance.value,
)
const displayMonthDuration = computed(
  () => monthlyStats.value?.total_elapsed_s ?? monthDuration.value,
)
const displayMonthRunCount = computed(
  () => monthlyStats.value?.activity_count ?? monthRunCount.value,
)
const displayMonthActiveDays = computed(
  () => monthlyStats.value?.active_days ?? monthActiveDays.value,
)
const displayAverageDistance = computed(
  () =>
    monthlyStats.value?.average_distance_m ??
    (monthActiveDays.value ? monthDistance.value / monthActiveDays.value : null),
)
const monthLabel = computed(() => {
  const [year, month] = selectedMonth.value.split('-').map(Number)
  return `${year} 年 ${month} 月`
})
const viewTitle = computed(
  () =>
    ({
      overview: '训练总览',
      activities: '活动记录',
      analysis: '训练分析',
      map: '地图探索',
      region: '区域探索',
    })[activeView.value],
)

// 生成固定 6 × 7 的日历网格，避免不同月份导致面板高度跳动。
const calendarCells = computed<CalendarCell[]>(() => {
  const [year, month] = selectedMonth.value.split('-').map(Number)
  const first = new Date(year, month - 1, 1)
  const days = new Date(year, month, 0).getDate()
  const leading = (first.getDay() + 6) % 7
  const lookup = new Map(monthRows.value.map((item) => [item.date, item]))
  const cells: CalendarCell[] = []
  const previousDays = new Date(year, month - 1, 0).getDate()

  for (let index = 0; index < leading; index += 1) {
    cells.push({ date: '', day: previousDays - leading + index + 1, data: null, outside: true })
  }
  for (let day = 1; day <= days; day += 1) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    cells.push({ date, day, data: lookup.get(date) || null, outside: false })
  }
  let nextDay = 1
  while (cells.length < 42) cells.push({ date: '', day: nextDay++, data: null, outside: true })
  return cells
})

// 将米转换为公里，并统一处理空值显示。
function formatKm(meters: number | null, digits = 1): string {
  return meters === null ? '—' : `${(meters / 1000).toFixed(digits)} km`
}

// 将每公里秒数转换为“分′秒″”格式。
function formatPace(seconds: number | null): string {
  if (!seconds || !Number.isFinite(seconds)) return '—'
  return `${Math.floor(seconds / 60)}′${String(Math.round(seconds % 60)).padStart(2, '0')}″`
}

// 将秒数转换为小时和分钟。
function formatDuration(seconds: number | null): string {
  if (!seconds) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes} min`
}

// 根据当天里程返回热力图等级，等级越高表示里程越多。
function heatLevel(meters: number): number {
  if (!meters) return 0
  if (meters < 5000) return 1
  if (meters < 10000) return 2
  if (meters < 16000) return 3
  return 4
}

// 按偏移量切换月份，-1 表示上个月，1 表示下个月。
function shiftMonth(offset: number): void {
  const [year, month] = selectedMonth.value.split('-').map(Number)
  const target = new Date(year, month - 1 + offset, 1)
  selectedMonth.value = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}`
}

// 读取当前月份的详细统计；统计接口失败时保留日历计算出的基础数据。
async function loadMonthlyStats(): Promise<void> {
  try {
    const response = await fetch(
      `/api/stats/monthly?month=${encodeURIComponent(selectedMonth.value)}`,
    )
    if (!response.ok) throw new Error('Monthly stats unavailable')
    monthlyStats.value = (await response.json()) as MonthlyStats
  } catch {
    monthlyStats.value = null
  }
}

// 打开某一天的活动列表，并在弹窗中加载当天数据。
async function openDay(cell: CalendarCell): Promise<void> {
  if (cell.outside || !cell.date) return
  selectedDay.value = cell.date
  dayDialogOpen.value = true
  dayLoading.value = true
  dayActivities.value = []
  try {
    dayActivities.value = await fetchAllActivities<Activity>({ start: cell.date, end: cell.date })
  } catch {
    ElMessage.error('无法读取当天活动，请检查后端服务。')
  } finally {
    dayLoading.value = false
  }
}

// 并行加载首页需要的活动、日历和数据质量报告。
async function loadDashboard(): Promise<void> {
  loading.value = true
  apiError.value = false
  try {
    // 三个接口相互独立，同时请求以缩短首页首次加载时间。
    const [activityData, calendarResponse, reportResponse] = await Promise.all([
      fetchAllActivities<Activity>(),
      fetch('/api/calendar'),
      fetch('/api/quality-report'),
    ])
    if (!calendarResponse.ok || !reportResponse.ok) throw new Error('API unavailable')
    activities.value = activityData
    calendar.value = (await calendarResponse.json()) as CalendarRow[]
    report.value = (await reportResponse.json()) as QualityReport
    const latestDate = calendar.value.at(-1)?.date
    if (latestDate) selectedMonth.value = latestDate.slice(0, 7)
    await loadMonthlyStats()
  } catch {
    apiError.value = true
    ElMessage.info('后端尚未连接，当前显示页面框架。')
  } finally {
    loading.value = false
  }
}

// 切换左侧导航对应的主视图。
function chooseView(view: View): void {
  activeView.value = view
}

// 打开活动详情抽屉。
function openActivity(activity: Activity): void {
  selectedActivity.value = activity
  dayDialogOpen.value = false
  drawerOpen.value = true
}

// 监听操作系统主题变化，仅在用户选择“跟随系统”时会影响最终主题。
const systemThemeQuery = window.matchMedia('(prefers-color-scheme: dark)')
function handleSystemTheme(event: MediaQueryListEvent): void {
  systemDark.value = event.matches
}

// 组件挂载后注册系统主题监听，并开始加载首页数据。
onMounted(() => {
  systemThemeQuery.addEventListener('change', handleSystemTheme)
  loadDashboard()
})
// 组件销毁前移除监听，防止监听器泄漏。
onBeforeUnmount(() => systemThemeQuery.removeEventListener('change', handleSystemTheme))
// 月份变化时重新请求该月份的统计数据。
watch(selectedMonth, loadMonthlyStats)
</script>

<template>
  <!-- 背景装饰层不参与交互，只负责显示渐变光晕。 -->
  <div class="app-background">
    <i class="aurora aurora-a"></i>
    <i class="aurora aurora-b"></i>
  </div>
  <!-- Element Plus 容器负责页面的左右布局：侧边栏 + 主内容区。 -->
  <el-container class="shell">
    <!-- 左侧导航栏：切换主视图并显示 API 状态。 -->
    <aside class="sidebar glass-dark">
      <div class="brand">
        <div class="brand-mark">R</div>
        <div>
          <strong>强风吹拂</strong>
          <span>RUNNING ATLAS</span>
        </div>
      </div>
      <nav class="nav-list" aria-label="主导航">
        <button :class="{ active: activeView === 'overview' }" @click="chooseView('overview')">
          <span>◉</span>
          训练总览
        </button>
        <button :class="{ active: activeView === 'activities' }" @click="chooseView('activities')">
          <span>≡</span>
          活动记录
        </button>
        <button :class="{ active: activeView === 'analysis' }" @click="chooseView('analysis')">
          <span>⌁</span>
          训练分析
        </button>
        <button :class="{ active: activeView === 'map' }" @click="chooseView('map')">
          <span>⌖</span>
          地图探索
        </button>
        <button :class="{ active: activeView === 'region' }" @click="chooseView('region')">
          <span>🗺️</span>
          区域探索
        </button>
      </nav>
      <div class="sidebar-status">
        <i :class="{ online: report?.readiness.api_ready }"></i>
        <div>
          <strong>{{ report?.readiness.api_ready ? '数据已就绪' : '等待 API' }}</strong>
          <span>
            {{
              report ? `${report.data_coverage.activities_with_gps} 条 GPS 轨迹` : 'LOCAL ARCHIVE'
            }}
          </span>
        </div>
      </div>
    </aside>

    <!-- 主区域包含顶部工具栏和当前页面内容。 -->
    <el-container class="main-shell">
      <!-- 顶部工具栏：显示标题、月份选择器、刷新按钮和主题切换。 -->
      <header class="topbar glass-bar">
        <div>
          <p class="eyebrow">PERSONAL RUNNING INTELLIGENCE</p>
          <h1>{{ viewTitle }}</h1>
        </div>
        <!-- 只有训练总览需要月份筛选，其他页面显示固定提示文字。 -->
        <div v-if="activeView === 'overview'" class="month-controller glass-control">
          <button aria-label="上个月" @click="shiftMonth(-1)">‹</button>
          <el-date-picker
            v-model="selectedMonth"
            type="month"
            value-format="YYYY-MM"
            format="YYYY 年 M 月"
            :clearable="false"
          />
          <button aria-label="下个月" @click="shiftMonth(1)">›</button>
        </div>
        <div v-else class="view-caption">FILTER · REVIEW · EXPLORE</div>
        <div class="topbar-actions">
          <!-- loading 状态会让按钮显示加载效果，避免用户误以为请求已完成。 -->
          <el-button circle plain :loading="loading" aria-label="刷新数据" @click="loadDashboard">
            ↻
          </el-button>
          <!-- v-model 会把选中的主题值双向绑定到 themePreference。 -->
          <el-segmented
            v-model="themePreference"
            :options="[
              { label: '◐', value: 'system' },
              { label: '☀', value: 'light' },
              { label: '☾', value: 'dark' },
            ]"
            aria-label="主题模式：跟随系统、浅色或深色"
          />
          <div class="avatar">G</div>
        </div>
      </header>

      <!-- v-if / v-else-if 根据 activeView 只渲染当前选中的页面。 -->
      <main class="dashboard" :class="{ 'explorer-dashboard': activeView !== 'overview' }">
        <template v-if="activeView === 'overview'">
          <!-- 总览页顶部的欢迎区域和本月里程摘要。 -->
          <section class="welcome-strip glass-card">
            <div>
              <p class="eyebrow">{{ monthLabel }} · MONTHLY FOCUS</p>
              <h2>稳定积累，让每一步都有迹可循。</h2>
            </div>
            <div class="month-highlight">
              <span>本月里程</span>
              <strong>{{ (displayMonthDistance / 1000).toFixed(1) }}</strong>
              <small>km</small>
            </div>
          </section>

          <!-- 四个核心指标卡片。 -->
          <section class="stat-grid">
            <article class="stat-card glass-card">
              <span>训练次数</span>
              <strong>{{ displayMonthRunCount }}</strong>
              <small>sessions</small>
            </article>
            <article class="stat-card glass-card">
              <span>活跃天数</span>
              <strong>{{ displayMonthActiveDays }}</strong>
              <small>active days</small>
            </article>
            <article class="stat-card glass-card">
              <span>训练时长</span>
              <strong>{{ formatDuration(displayMonthDuration) }}</strong>
              <small>moving time</small>
            </article>
            <article class="stat-card glass-card">
              <span>日均里程</span>
              <strong>{{ formatKm(displayAverageDistance) }}</strong>
              <small>per active day</small>
            </article>
          </section>

          <!-- 日历和趋势图、活动列表组成总览页的主要工作区。 -->
          <section class="workspace-grid">
            <article class="calendar-panel glass-card">
              <div class="panel-heading">
                <div>
                  <p class="eyebrow">CONSISTENCY</p>
                  <h3>{{ monthLabel }}运动日历</h3>
                </div>
                <div class="legend">
                  <span>少</span>
                  <i></i>
                  <i></i>
                  <i></i>
                  <i></i>
                  <span>多</span>
                </div>
              </div>
              <div class="weekday-row">
                <span>一</span>
                <span>二</span>
                <span>三</span>
                <span>四</span>
                <span>五</span>
                <span>六</span>
                <span>日</span>
              </div>
              <div class="month-grid">
                <!-- v-for 为每个日历格子生成按钮，点击后打开当天活动。 -->
                <button
                  v-for="(cell, index) in calendarCells"
                  :key="`${cell.date}-${index}`"
                  class="day-cell"
                  :class="[
                    `heat-${heatLevel(cell.data?.distance_m || 0)}`,
                    { outside: cell.outside },
                  ]"
                  :title="
                    cell.data ? `${cell.date} · ${formatKm(cell.data.distance_m)}` : cell.date
                  "
                  @click="openDay(cell)"
                >
                  <span>{{ cell.day }}</span>
                  <div v-if="cell.data" class="day-data">
                    <strong>{{ (cell.data.distance_m / 1000).toFixed(1) }}</strong>
                    <small>km</small>
                  </div>
                  <i v-if="cell.data?.activity_count">{{ cell.data.activity_count }}</i>
                </button>
              </div>
            </article>

            <div class="right-stack">
              <article class="trend-panel glass-card">
                <div class="panel-heading">
                  <div>
                    <p class="eyebrow">DAILY VOLUME</p>
                    <h3>每日里程趋势</h3>
                  </div>
                  <span class="panel-note">{{ monthRows.length }} 个训练日</span>
                </div>
                <!-- props 把父组件的数据传给趋势图子组件。 -->
                <DistanceTrend :rows="monthRows" :dark="resolvedTheme === 'dark'" />
              </article>
              <article class="activities-panel glass-card">
                <div class="panel-heading">
                  <div>
                    <p class="eyebrow">MONTHLY SESSIONS</p>
                    <h3>当月活动</h3>
                  </div>
                  <el-button text type="primary" @click="chooseView('activities')">
                    全部 →
                  </el-button>
                </div>
                <!-- Element Plus 的 row-click 事件把选中的行交给详情处理函数。 -->
                <el-table
                  v-if="monthActivities.length"
                  :data="monthActivities"
                  class="activity-table"
                  :show-header="false"
                  @row-click="openActivity"
                >
                  <el-table-column min-width="100">
                    <template #default="scope">
                      <div class="activity-name">
                        <i></i>
                        <div>
                          <strong>{{ scope.row.date?.slice(5) }}</strong>
                          <span>{{ scope.row.sport || '训练' }}</span>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column min-width="90" align="right">
                    <template #default="scope">
                      <strong>{{ formatKm(scope.row.distance_m) }}</strong>
                    </template>
                  </el-table-column>
                  <el-table-column min-width="72" align="right">
                    <template #default="scope">
                      <span class="muted">{{ formatPace(scope.row.average_pace_s_per_km) }}</span>
                    </template>
                  </el-table-column>
                </el-table>
                <el-empty v-else description="本月暂无活动" :image-size="42" />
              </article>
            </div>
          </section>
        </template>
        <!-- 其他页面由独立子组件负责，父组件只传入必要的 props 和事件。 -->
        <ActivityExplorer v-else-if="activeView === 'activities'" @open="openActivity" />
        <TrainingAnalysis
          v-else-if="activeView === 'analysis'"
          :dark="resolvedTheme === 'dark'"
          :latest-date="report?.data_coverage.date_range.end"
        />
        <MapExplorer
          v-else-if="activeView === 'map'"
          :dark="resolvedTheme === 'dark'"
          :start-date="report?.data_coverage.date_range.start"
          :end-date="report?.data_coverage.date_range.end"
        />
        <RegionExplorer v-else-if="activeView === 'region'" />
        <!-- 后端不可用时显示提示，但仍保留页面框架供用户浏览。 -->
        <el-alert
          v-if="apiError"
          class="api-alert"
          title="后端未连接：请启动 FastAPI 以载入真实数据。"
          type="info"
          :closable="false"
        />
      </main>
    </el-container>
  </el-container>

  <!-- 活动详情抽屉通过 v-model 与 drawerOpen 双向绑定。 -->
  <ActivityDetailModal
    v-model="drawerOpen"
    :activity="selectedActivity"
    :dark="resolvedTheme === 'dark'"
  />

  <!-- 日历日期弹窗：先显示加载状态，再显示当天活动或空状态。 -->
  <el-dialog
    v-model="dayDialogOpen"
    width="520px"
    class="day-dialog"
    align-center
    :show-close="false"
    :close-on-press-escape="true"
  >
    <template #header>
      <!-- #header 将这段内容插入 Element Plus 对话框的 header 插槽。 -->
      <div class="day-dialog-header">
        <button class="day-close" title="关闭" aria-label="关闭" @click="dayDialogOpen = false">
          ×
        </button>
        <div>
          <p class="eyebrow">DAILY SESSIONS</p>
          <h3>{{ selectedDay }} 活动记录</h3>
        </div>
        <span></span>
      </div>
    </template>
    <div v-loading="dayLoading">
      <!-- v-if / v-else-if / v-else 确保加载、列表和空状态不会同时出现。 -->
      <div v-if="dayActivities.length" class="day-summary">
        <span>{{ dayActivities.length }} 次训练</span>
        <strong>
          {{ formatKm(dayActivities.reduce((sum, item) => sum + (item.distance_m || 0), 0)) }}
        </strong>
      </div>
      <el-table
        v-if="dayActivities.length"
        :data="dayActivities"
        class="activity-table"
        @row-click="openActivity"
      >
        <el-table-column label="类型" min-width="100">
          <template #default="scope">{{ scope.row.sport || '训练' }}</template>
        </el-table-column>
        <el-table-column label="距离" min-width="90">
          <template #default="scope">{{ formatKm(scope.row.distance_m) }}</template>
        </el-table-column>
        <el-table-column label="配速" min-width="80">
          <template #default="scope">{{ formatPace(scope.row.average_pace_s_per_km) }}</template>
        </el-table-column>
        <el-table-column label="时长" min-width="90">
          <template #default="scope">{{ formatDuration(scope.row.elapsed_s) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else-if="!dayLoading" description="当天没有运动记录" :image-size="58" />
    </div>
  </el-dialog>
</template>
