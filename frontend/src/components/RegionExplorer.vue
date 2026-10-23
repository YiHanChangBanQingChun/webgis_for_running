<script setup lang="ts">
// 区域探索页面只负责展示控件；数据处理和 Cesium 操作分别放在 composable 与场景类中。
import { ref } from 'vue'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { formatDuration, formatPace, useRegionExplorer } from '../features/region/useRegionExplorer'

const container = ref<HTMLDivElement>()
// composable 返回响应式状态和操作函数，模板可以直接绑定它们。
const {
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
} = useRegionExplorer(container)
</script>

<template>
  <!-- 左侧是控制面板，右侧是三维场景和轨迹回放控制条。 -->
  <section class="region-explorer">
    <!-- 控件只绑定状态；请求、筛选和动画在 composable 中，Cesium 调用在场景类中。 -->
    <aside class="region-inspector glass-card">
      <header>
        <p class="eyebrow">CITY RUNNING THEATER</p>
        <h2>在城市之间，重走一次跑步</h2>
        <p class="intro">把配速、心率与沿途建筑放回同一段三维旅程。</p>
      </header>

      <label class="control-label" for="region-activity">
        选择跑步 · {{ activities.length }} 次 GPS 活动
      </label>
      <el-select
        id="region-activity"
        v-model="selectedActivityId"
        filterable
        :loading="loadingActivities"
        placeholder="按日期检索活动"
        aria-label="选择跑步活动"
      >
        <el-option
          v-for="activity in activities"
          :key="activity.id"
          :value="activity.id"
          :label="`${activity.date || '日期未知'} · ${((activity.distance_m || 0) / 1000).toFixed(2)} km`"
        />
      </el-select>
      <div v-if="activityError" class="feedback" role="alert">
        {{ activityError }}
        <el-button text @click="loadActivities">重新读取活动</el-button>
      </div>
      <p v-if="trackError" class="feedback" role="alert">{{ trackError }}</p>

      <div class="journey-stats">
        <div>
          <strong>{{ track ? (track.distanceMeters / 1000).toFixed(2) : '—' }}</strong>
          <span>轨迹里程 km</span>
        </div>
        <div>
          <strong>{{ track ? formatDuration(track.durationSeconds) : '—' }}</strong>
          <span>记录时长 min:s</span>
        </div>
      </div>

      <label class="control-label" for="region-color">轨迹颜色</label>
      <el-select id="region-color" v-model="colorMode" aria-label="轨迹颜色">
        <el-option label="按配速" value="pace" />
        <el-option label="按心率" value="heartRate" />
        <el-option label="单色发光" value="plain" />
      </el-select>
      <div class="route-legend">
        <span v-for="item in legend" :key="item.label">
          <i :style="{ background: item.color }"></i>
          {{ item.label }}
        </span>
      </div>
      <p class="hint">颜色是固定数值分组，不代表个人训练强度区间。</p>

      <div class="section-heading">
        <h3>沿线建筑</h3>
        <el-switch v-model="showBuildings" aria-label="显示沿线建筑" />
      </div>
      <label class="control-label" for="region-radius">探索距离</label>
      <el-select id="region-radius" v-model="radius" aria-label="沿线建筑探索距离">
        <el-option :value="100" label="轨迹两侧 100 m" />
        <el-option :value="250" label="轨迹两侧 250 m" />
        <el-option :value="500" label="轨迹两侧 500 m" />
      </el-select>
      <div class="building-stats" aria-live="polite">
        <div>
          <strong>{{ loadingBuildings ? '…' : buildingStats.count }}</strong>
          <span>沿线建筑</span>
        </div>
        <div>
          <strong>{{ buildingStats.maximum.toFixed(0) }} m</strong>
          <span>最高建筑</span>
        </div>
        <div>
          <strong>{{ buildingStats.average.toFixed(0) }} m</strong>
          <span>平均楼高</span>
        </div>
      </div>
      <label class="control-label" for="region-height">
        高度夸张 × {{ heightScale.toFixed(1) }}
      </label>
      <input
        id="region-height"
        v-model.number="heightScale"
        type="range"
        min="1"
        max="3"
        step="0.1"
        aria-label="建筑高度夸张倍数"
      />
      <p class="hint">
        颜色按原始楼高：蓝 &lt;30 m，青 30–80 m，橙 80–150 m，红 ≥150
        m。夸张仅改变视觉，统计与属性保持原值。
      </p>
      <p
        v-if="
          track && totalBuildings && !loadingBuildings && !buildingStats.count && !buildingError
        "
        class="feedback"
      >
        这段轨迹附近没有广州建筑记录；可扩大距离或换一条轨迹。
      </p>
      <div v-if="buildingError" class="feedback" role="alert">
        {{ buildingError }}
        <el-button text @click="loadBuildings">重新加载建筑</el-button>
      </div>

      <div v-if="selectedBuilding" class="building-selection" aria-live="polite">
        <span>选中的建筑</span>
        <strong>{{ selectedBuilding.name }}</strong>
        <span>原始高度 {{ selectedBuilding.height.toFixed(1) }} m</span>
      </div>
      <p v-else class="hint">点击三维建筑，可查看名称与原始高度。</p>
      <div class="section-heading">
        <h3>在线 OSM 底图</h3>
        <el-switch v-model="onlineBasemap" aria-label="开启在线 OSM 底图" />
      </div>
      <p class="hint">默认本地纯色地球；开启底图需要网络。</p>
      <p v-if="basemapError" class="feedback" role="status">{{ basemapError }}</p>
      <p class="method-note">
        建筑源
        {{ totalBuildings.toLocaleString() }}
        个面。按建筑包围盒中心至完整轨迹的近似距离筛选；无地形，建筑底部统一为椭球高 0 m，轨迹抬高 5
        m 便于辨识。
      </p>
    </aside>

    <div class="region-stage">
      <div ref="container" class="cesium-container"></div>
      <div class="stage-caption">
        <span>GUANGZHOU · RUNNING ATLAS</span>
        <strong>{{ selectedActivity?.date || '等待选择跑步' }}</strong>
      </div>
      <div v-if="loadingTrack || loadingBuildings" class="stage-status" role="status">
        {{ loadingTrack ? '正在加载跑步轨迹…' : '正在构建沿线建筑…' }}
      </div>
      <p v-if="sceneError" class="scene-error" role="alert">{{ sceneError }}</p>

      <footer class="playback-panel">
        <div class="playback-metrics" aria-live="off">
          <div>
            <span>当前位置</span>
            <strong>
              {{ currentPoint ? (currentPoint.distanceMeters / 1000).toFixed(2) : '—' }} km
            </strong>
          </div>
          <div>
            <span>采样配速</span>
            <strong>{{ formatPace(currentPoint?.paceSeconds ?? null) }}</strong>
          </div>
          <div>
            <span>采样心率</span>
            <strong>{{ currentPoint?.heartRate ?? '—' }} bpm</strong>
          </div>
        </div>
        <div class="timeline-row">
          <button class="play-button" :disabled="!track || !!sceneError" @click="togglePlayback">
            {{ playing ? '暂停' : '播放' }}
          </button>
          <input
            type="range"
            min="0"
            :max="track?.durationSeconds || 1"
            step="0.1"
            :value="elapsed"
            :disabled="!track"
            aria-label="跑步回放进度"
            @input="seek"
          />
          <span class="time-label">
            {{ formatDuration(elapsed) }} / {{ formatDuration(track?.durationSeconds || 0) }}
          </span>
        </div>
        <div class="playback-actions">
          <label>
            倍速
            <select v-model.number="speed" aria-label="回放倍速">
              <option :value="10">10×</option>
              <option :value="30">30×</option>
              <option :value="60">60×</option>
            </select>
          </label>
          <label>
            <input v-model="following" type="checkbox" :disabled="!track" />
            跟随跑者
          </label>
          <button :disabled="!track" @click="overview">全程俯瞰</button>
          <small>
            {{
              track?.usedTimeFallback
                ? '部分时间戳缺失，按 1 秒/点近似回放'
                : '按轨迹记录时间回放（含停顿）'
            }}
          </small>
        </div>
      </footer>
    </div>
  </section>
</template>

<style scoped>
.region-explorer {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  height: 100%;
  min-height: 0;
}

.region-inspector {
  display: flex;
  flex-direction: column;
  padding: 20px;
  border-radius: 18px;
  overflow-y: auto;
  gap: 9px;
  color: var(--text);
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 9px;
}
h2 {
  margin: 0;
  font-size: 19px;
  line-height: 1.5;
}
.intro {
  margin: 8px 0 12px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}
.control-label {
  margin-top: 5px;
  font-size: 12px;
  font-weight: 600;
}
.journey-stats,
.building-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  padding: 14px 0;
  border-block: 1px solid var(--line);
}
.building-stats {
  grid-template-columns: repeat(3, 1fr);
}
.journey-stats strong,
.building-stats strong {
  display: block;
  font-size: 19px;
}
.building-stats strong {
  font-size: 16px;
}
.journey-stats span,
.building-stats span {
  display: block;
  margin-top: 5px;
  color: var(--muted);
  font-size: 10px;
}
.route-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 10px;
}
.route-legend span {
  display: inline-flex;
  gap: 5px;
  align-items: center;
}
.route-legend i {
  width: 14px;
  height: 4px;
  border-radius: 3px;
}
.hint,
.method-note {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}
.method-note {
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
}
h3 {
  margin: 0;
  font-size: 13px;
}
.feedback {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  background: rgba(245, 154, 74, 0.12);
  font-size: 12px;
  line-height: 1.6;
}
.building-selection {
  display: grid;
  gap: 5px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(88, 222, 197, 0.12);
  font-size: 12px;
}
.region-stage {
  position: relative;
  min-width: 0;
  min-height: 450px;
  border-radius: 18px;
  overflow: hidden;
  background: #101b2a;
}
.cesium-container {
  width: 100%;
  height: 100%;
}
.stage-caption {
  position: absolute;
  top: 20px;
  left: 20px;
  display: grid;
  gap: 6px;
  color: #e7f1fa;
  pointer-events: none;
  text-shadow: 0 1px 8px #101b2a;
}
.stage-caption span {
  font-family: monospace;
  letter-spacing: 0.12em;
  font-size: 9px;
}
.stage-caption strong {
  font-size: 19px;
}
.stage-status {
  position: absolute;
  top: 22px;
  right: 18px;
  border-radius: 7px;
  padding: 8px 10px;
  color: #e7f1fa;
  background: #243b50;
  font-size: 11px;
}
.scene-error {
  position: absolute;
  top: 80px;
  left: 20px;
  right: 20px;
  padding: 14px;
  background: #7c3333;
  color: white;
  border-radius: 9px;
}
.playback-panel {
  position: absolute;
  bottom: 36px;
  left: 18px;
  right: 18px;
  padding: 16px;
  border-radius: 14px;
  color: #e9f2fa;
  background: rgba(15, 29, 45, 0.9);
  border: 1px solid rgba(180, 206, 226, 0.22);
  backdrop-filter: blur(16px);
}
.playback-metrics {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 12px;
}
.playback-metrics span {
  display: block;
  margin-bottom: 5px;
  color: #99aec2;
  font-size: 10px;
}
.playback-metrics strong {
  font-size: 16px;
}
.timeline-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
input[type='range'] {
  min-width: 0;
  accent-color: #58dec5;
  cursor: pointer;
}
.timeline-row input {
  flex: 1;
}
.play-button {
  min-width: 55px;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: #58dec5;
  color: #102b31;
  cursor: pointer;
}
.time-label {
  font-family: monospace;
  font-size: 10px;
}
.playback-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 11px;
}
.playback-actions label {
  display: flex;
  align-items: center;
  gap: 5px;
}
.playback-actions select,
.playback-actions button {
  color: #e9f2fa;
  background: #263c50;
  border: 1px solid #3b536a;
  border-radius: 6px;
  padding: 4px 8px;
}
.playback-actions small {
  margin-left: auto;
  color: #99aec2;
  font-size: 10px;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}

@media (max-width: 1100px) {
  .region-explorer {
    grid-template-columns: 250px minmax(0, 1fr);
    gap: 10px;
  }
  .region-inspector {
    padding: 15px;
  }
  .playback-metrics strong {
    font-size: 12px;
  }
  .playback-actions small {
    display: none;
  }
}

@media (max-width: 760px) {
  .region-explorer {
    height: auto;
    grid-template-columns: 1fr;
  }
  .region-inspector {
    max-height: 420px;
  }
  .region-stage {
    height: 560px;
  }
  .time-label {
    font-size: 9px;
  }
}
</style>
