<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

interface Activity {
  id: string
  date: string | null
  sport: string | number | null
  distance_m: number | null
  elapsed_s: number | null
  average_heart_rate: number | null
  average_pace_s_per_km: number | null
  total_ascent_m?: number | null
  has_gps: boolean
}

const emit = defineEmits<{ open: [activity: Activity] }>()
const rows = ref<Activity[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 12
// 筛选状态与界面控件共用同一个响应式对象，查询时再转成 URL 参数。
const filters = reactive({
  dates: null as [string, string] | null,
  sport: '',
  distance: '',
  gps: '',
})

function formatKm(value: number | null): string {
  return value == null ? '—' : `${(value / 1000).toFixed(1)} km`
}
function formatPace(value: number | null): string {
  if (!value) return '—'
  return `${Math.floor(value / 60)}′${String(Math.round(value % 60)).padStart(2, '0')}″`
}
function formatDuration(value: number | null): string {
  if (!value) return '—'
  const hours = Math.floor(value / 3600)
  const minutes = Math.round((value % 3600) / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes} min`
}

async function search(resetPage = false): Promise<void> {
  if (resetPage) page.value = 1
  // 后端使用 limit / offset 分页，切换页码后沿用当前筛选条件。
  const query = new URLSearchParams({
    limit: String(pageSize),
    offset: String((page.value - 1) * pageSize),
  })
  if (filters.dates) {
    query.set('start', filters.dates[0])
    query.set('end', filters.dates[1])
  }
  if (filters.sport) query.set('sport', filters.sport)
  if (filters.gps) query.set('has_gps', filters.gps)
  if (filters.distance) query.set('min_distance_km', filters.distance)
  loading.value = true
  try {
    const response = await fetch(`/api/activities?${query}`)
    if (!response.ok) throw new Error('query failed')
    const result = (await response.json()) as { total: number; items: Activity[] }
    rows.value = result.items
    total.value = result.total
  } catch {
    ElMessage.error('活动查询失败，请检查 FastAPI 服务。')
  } finally {
    loading.value = false
  }
}

function reset(): void {
  filters.dates = null
  filters.sport = ''
  filters.distance = ''
  filters.gps = ''
  search(true)
}

onMounted(() => search())
</script>

<template>
  <section class="explorer-page">
    <div class="explorer-heading">
      <div>
        <p class="eyebrow">ACTIVITY ARCHIVE</p>
        <h2>活动记录</h2>
        <span>从 {{ total }} 条记录中检索你的训练足迹</span>
      </div>
    </div>
    <div class="filter-bar glass-card">
      <el-date-picker
        v-model="filters.dates"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
      />
      <el-select v-model="filters.sport" placeholder="运动类型" clearable>
        <el-option label="跑步" value="running" />
        <el-option label="骑行" value="cycling" />
        <el-option label="徒步" value="hiking" />
        <el-option label="步行" value="walking" />
        <el-option label="训练" value="training" />
      </el-select>
      <el-select v-model="filters.distance" placeholder="最小距离" clearable>
        <el-option label="≥ 5 km" value="5" />
        <el-option label="≥ 10 km" value="10" />
        <el-option label="≥ 15 km" value="15" />
        <el-option label="≥ 20 km" value="20" />
      </el-select>
      <el-select v-model="filters.gps" placeholder="轨迹状态" clearable>
        <el-option label="有 GPS" value="true" />
        <el-option label="无 GPS" value="false" />
      </el-select>
      <el-button type="primary" @click="search(true)">查询</el-button>
      <el-button @click="reset">重置</el-button>
    </div>
    <div class="archive-table glass-card">
      <el-table
        v-loading="loading"
        :data="rows"
        height="100%"
        class="activity-table full-table"
        @row-click="emit('open', $event)"
      >
        <el-table-column label="日期" min-width="120">
          <template #default="scope">
            <strong>{{ scope.row.date }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="类型" min-width="90">
          <template #default="scope">
            <span class="sport-dot"></span>
            {{ scope.row.sport || '训练' }}
          </template>
        </el-table-column>
        <el-table-column label="距离" min-width="90">
          <template #default="scope">{{ formatKm(scope.row.distance_m) }}</template>
        </el-table-column>
        <el-table-column label="配速" min-width="85">
          <template #default="scope">{{ formatPace(scope.row.average_pace_s_per_km) }}</template>
        </el-table-column>
        <el-table-column label="时长" min-width="90">
          <template #default="scope">{{ formatDuration(scope.row.elapsed_s) }}</template>
        </el-table-column>
        <el-table-column label="平均心率" min-width="90">
          <template #default="scope">
            {{ scope.row.average_heart_rate ? `${scope.row.average_heart_rate} bpm` : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="爬升" min-width="75">
          <template #default="scope">
            {{ scope.row.total_ascent_m != null ? `${scope.row.total_ascent_m} m` : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="轨迹" width="70">
          <template #default="scope">
            <el-tag size="small" :type="scope.row.has_gps ? 'success' : 'info'" effect="plain">
              {{ scope.row.has_gps ? 'GPS' : '无' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-pagination
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      @current-change="search()"
    />
  </section>
</template>
