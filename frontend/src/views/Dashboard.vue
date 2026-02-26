<template>
  <div class="dashboard">
    <!-- 顶部操作栏 -->
    <div class="action-bar">
      <button class="btn btn-primary" @click="runAnalysis" :disabled="loading">
        <span v-if="loading" class="spinner"></span>
        <span v-else>🔄</span>
        {{ loading ? '分析中...' : '运行分析' }}
      </button>
      <select v-model="source" class="select">
        <option value="mock">模拟数据</option>
        <option value="gitlab">GitLab 数据</option>
      </select>
      <select v-model="days" class="select">
        <option :value="7">最近 7 天</option>
        <option :value="14">最近 14 天</option>
        <option :value="30">最近 30 天</option>
        <option :value="90">最近 90 天</option>
      </select>
      <label class="checkbox-label">
        <input type="checkbox" v-model="enableLlmReview" />
        启用 LLM 代码审查
      </label>
    </div>

    <!-- 核心指标卡片 -->
    <div class="metrics-grid" v-if="data">
      <!-- 综合健康分 -->
      <div class="card card-health" :class="'health-' + data.health.level">
        <div class="card-header">
          <h3>综合健康分</h3>
          <span class="badge" :class="'badge-' + data.health.level">
            {{ levelLabel(data.health.level) }}
          </span>
        </div>
        <div class="health-score-display">
          <div class="score-ring">
            <svg viewBox="0 0 120 120" class="score-svg">
              <circle cx="60" cy="60" r="52" class="ring-bg" />
              <circle cx="60" cy="60" r="52" class="ring-fill"
                :style="{ strokeDashoffset: ringOffset(data.health.score) }" />
            </svg>
            <div class="score-value">{{ Math.round(data.health.score) }}</div>
          </div>
        </div>
        <div class="health-breakdown">
          <div class="breakdown-item" v-for="item in healthBreakdown" :key="item.label">
            <span class="breakdown-label">{{ item.label }}</span>
            <div class="breakdown-bar-wrapper">
              <div class="breakdown-bar" :style="{ width: item.pct + '%', background: item.color }"></div>
            </div>
            <span class="breakdown-value">{{ item.value.toFixed(1) }}</span>
          </div>
        </div>
      </div>

      <!-- 团队状态 -->
      <div class="card">
        <div class="card-header">
          <h3>团队状态</h3>
          <span class="state-emoji">{{ stateEmoji(data.team_state.state) }}</span>
        </div>
        <div class="state-display">
          <div class="state-name">{{ stateLabel(data.team_state.state) }}</div>
          <div class="state-score">得分: {{ data.team_state.score.toFixed(3) }}</div>
        </div>
        <div class="state-dimensions">
          <div class="dim-item" v-for="dim in stateDimensions" :key="dim.label">
            <span class="dim-label">{{ dim.label }}</span>
            <span class="dim-value" :class="dim.cls">{{ dim.value }}</span>
          </div>
        </div>
        <p class="state-desc">{{ data.team_state.description }}</p>
      </div>

      <!-- DORA 指标 -->
      <div class="card">
        <div class="card-header">
          <h3>DORA 效能指标</h3>
          <span class="badge" :class="'badge-dora-' + data.dora.overall_level">
            {{ data.dora.overall_level.toUpperCase() }}
          </span>
        </div>
        <div class="dora-grid">
          <div class="dora-item" v-for="metric in doraMetrics" :key="metric.label">
            <div class="dora-icon">{{ metric.icon }}</div>
            <div class="dora-label">{{ metric.label }}</div>
            <div class="dora-value">{{ metric.value }}</div>
          </div>
        </div>
      </div>

      <!-- 技术债 -->
      <div class="card">
        <div class="card-header">
          <h3>技术债利息率</h3>
          <span class="badge" :class="'badge-debt-' + data.tech_debt.level">
            {{ debtLevelLabel(data.tech_debt.level) }}
          </span>
        </div>
        <div class="debt-display">
          <div class="debt-rate">{{ (data.tech_debt.interest_rate * 100).toFixed(1) }}%</div>
          <div class="debt-bar-wrapper">
            <div class="debt-bar" :style="{ width: Math.min(data.tech_debt.interest_rate * 100, 100) + '%' }"></div>
            <div class="debt-threshold" style="left: 30%"></div>
            <div class="debt-threshold danger" style="left: 50%"></div>
          </div>
          <div class="debt-stats">
            <span>修复 Commits: {{ data.tech_debt.fix_commit_count }}</span>
            <span>总 Commits: {{ data.tech_debt.total_commit_count }}</span>
          </div>
        </div>
      </div>

      <!-- 英雄检测 -->
      <div class="card">
        <div class="card-header">
          <h3>代码提交集中度</h3>
          <span class="badge" :class="'badge-hero-' + data.hero.level">
            基尼 {{ data.hero.gini_coefficient.toFixed(3) }}
          </span>
        </div>
        <div class="hero-display">
          <div class="hero-team-size">团队: {{ data.hero.team_size }} 人</div>
          <div class="hero-contributors" v-if="data.hero.top_contributors.length">
            <div class="contrib-item" v-for="(c, i) in data.hero.top_contributors" :key="i">
              <span class="contrib-rank">#{{ i + 1 }}</span>
              <span class="contrib-name">{{ c.author }}</span>
              <div class="contrib-bar-wrapper">
                <div class="contrib-bar" :style="{ width: contribPct(c.count) + '%' }"></div>
              </div>
              <span class="contrib-count">{{ c.count }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 趋势图 -->
      <div class="card card-wide" v-if="history.length > 1">
        <div class="card-header">
          <h3>健康分趋势</h3>
        </div>
        <div class="chart-container">
          <canvas ref="trendCanvas"></canvas>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div class="empty-state" v-else-if="!loading">
      <div class="empty-icon">📈</div>
      <h2>欢迎使用 AI 技术管理工具</h2>
      <p>点击「运行分析」开始首次团队健康评估</p>
      <p class="empty-hint">基于《An Elegant Puzzle》中的管理方法论</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { Chart, registerables } from 'chart.js'
import { runAnalysis as apiRunAnalysis, getLatest, getHistory as apiGetHistory } from '../api/client.js'

Chart.register(...registerables)

const data = ref(null)
const loading = ref(false)
const source = ref('mock')
const days = ref(30)
const enableLlmReview = ref(false)
const history = ref([])
const trendCanvas = ref(null)
let trendChart = null

// 加载最新数据
onMounted(async () => {
  try {
    const latest = await getLatest()
    if (latest) data.value = latest
    const hist = await apiGetHistory(90)
    if (hist) history.value = hist
  } catch (e) {
    // 首次启动可能无数据
  }
})

// 运行分析
async function runAnalysis() {
  loading.value = true
  try {
    const result = await apiRunAnalysis(source.value, days.value, enableLlmReview.value)
    data.value = result
    // 刷新历史
    const hist = await apiGetHistory(90)
    history.value = hist || []
    await nextTick()
    renderTrend()
  } catch (e) {
    alert('分析失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

// 趋势图
watch(history, async () => {
  await nextTick()
  renderTrend()
})

function renderTrend() {
  if (!trendCanvas.value || history.value.length < 2) return
  if (trendChart) trendChart.destroy()
  const labels = history.value.map(h => {
    const d = new Date(h.created_at)
    return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`
  })
  trendChart = new Chart(trendCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '健康分',
          data: history.value.map(h => h.health_score),
          borderColor: '#43e97b',
          backgroundColor: 'rgba(67, 233, 123, 0.1)',
          fill: true, tension: 0.4,
        },
        {
          label: 'DORA 得分 (×100)',
          data: history.value.map(h => h.dora_overall_score * 100),
          borderColor: '#42a5f5',
          tension: 0.4,
        },
        {
          label: '技术债率 (×100)',
          data: history.value.map(h => h.tech_debt_interest_rate * 100),
          borderColor: '#ffa726',
          tension: 0.4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#9fa8c7', font: { family: 'Inter' } } },
      },
      scales: {
        x: { ticks: { color: '#6b7394' }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { ticks: { color: '#6b7394' }, grid: { color: 'rgba(255,255,255,0.04)' }, min: 0, max: 100 },
      },
    },
  })
}

// 健康分维度分解
const healthBreakdown = computed(() => {
  if (!data.value) return []
  const h = data.value.health
  const max = 30 // 最大可能贡献
  return [
    { label: 'DORA 效能', value: h.dora_contribution, pct: (h.dora_contribution / max) * 100, color: 'var(--accent-blue)' },
    { label: '技术债', value: h.debt_contribution, pct: (h.debt_contribution / max) * 100, color: 'var(--accent-orange)' },
    { label: '协作均衡', value: h.hero_contribution, pct: (h.hero_contribution / max) * 100, color: 'var(--accent-purple)' },
    { label: '团队状态', value: h.state_contribution, pct: (h.state_contribution / max) * 100, color: 'var(--accent-green)' },
  ]
})

// DORA 指标
const doraMetrics = computed(() => {
  if (!data.value) return []
  const d = data.value.dora
  return [
    { icon: '⏱️', label: '变更前置时间', value: d.lead_time_hours.toFixed(1) + 'h' },
    { icon: '🚀', label: '部署频率', value: d.deploy_frequency.toFixed(2) + '/天' },
    { icon: '❌', label: '变更失败率', value: (d.change_failure_rate * 100).toFixed(1) + '%' },
    { icon: '🔧', label: '平均恢复时间', value: d.mttr_hours.toFixed(1) + 'h' },
  ]
})

// 团队状态维度
const stateDimensions = computed(() => {
  if (!data.value) return []
  const s = data.value.team_state
  return [
    { label: '积压趋势', value: s.backlog_score?.toFixed(3) || '-', cls: s.backlog_score >= 0 ? 'positive' : 'negative' },
    { label: '技术债', value: s.debt_score?.toFixed(3) || '-', cls: s.debt_score >= 0 ? 'positive' : 'negative' },
    { label: '士气', value: s.morale_score?.toFixed(3) || '-', cls: 'neutral' },
    { label: '创新占比', value: s.innovation_score?.toFixed(3) || '-', cls: 'positive' },
  ]
})

// 贡献者占比
const maxContrib = computed(() => {
  if (!data.value?.hero?.top_contributors?.length) return 1
  return Math.max(...data.value.hero.top_contributors.map(c => c.count), 1)
})
function contribPct(count) { return (count / maxContrib.value) * 100 }

// 环形图偏移
function ringOffset(score) {
  const circumference = 2 * Math.PI * 52
  return circumference * (1 - score / 100)
}

// 标签
function levelLabel(level) {
  return { excellent: '优秀', good: '良好', attention: '需关注', danger: '危险' }[level] || level
}
function stateLabel(state) {
  return {
    falling_behind: '落后', treading_water: '停滞',
    paying_down_debt: '偿债', innovating: '创新',
  }[state] || state
}
function stateEmoji(state) {
  return {
    falling_behind: '⚠️', treading_water: '🔄',
    paying_down_debt: '📈', innovating: '🚀',
  }[state] || '❓'
}
function debtLevelLabel(level) {
  return { healthy: '健康', warning: '需关注', alert: '告警', danger: '危险' }[level] || level
}
</script>

<style scoped>
.dashboard { min-height: 80vh; }

/* 操作栏 */
.action-bar {
  display: flex; gap: 12px; margin-bottom: 24px; align-items: center; flex-wrap: wrap;
}
.btn {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 24px; border: none; border-radius: var(--radius-sm);
  font-family: var(--font-family); font-size: 0.9rem; font-weight: 600;
  cursor: pointer; transition: all 0.2s;
}
.btn-primary {
  background: var(--gradient-primary); color: #fff;
  box-shadow: 0 4px 14px rgba(102, 126, 234, 0.4);
}
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
.select {
  background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color);
  padding: 10px 16px; border-radius: var(--radius-sm); font-family: var(--font-family);
  font-size: 0.85rem; outline: none;
}
.checkbox-label {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.85rem; color: var(--text-secondary); cursor: pointer;
}
.checkbox-label input { accent-color: var(--accent-blue); }
.spinner {
  width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 卡片网格 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 20px;
}
.card {
  background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: var(--radius); padding: 24px;
  box-shadow: var(--shadow-card); transition: all 0.3s;
}
.card:hover { border-color: rgba(102, 126, 234, 0.3); box-shadow: var(--shadow-glow); }
.card-wide { grid-column: 1 / -1; }
.card-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px;
}
.card-header h3 { font-size: 1rem; font-weight: 600; color: var(--text-secondary); }

/* 徽章 */
.badge {
  padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600;
}
.badge-excellent { background: rgba(67,233,123,0.15); color: var(--accent-green); }
.badge-good { background: rgba(66,165,245,0.15); color: var(--accent-blue); }
.badge-attention { background: rgba(255,167,38,0.15); color: var(--accent-orange); }
.badge-danger { background: rgba(239,83,80,0.15); color: var(--accent-red); }
.badge-dora-elite { background: rgba(67,233,123,0.15); color: var(--accent-green); }
.badge-dora-high { background: rgba(66,165,245,0.15); color: var(--accent-blue); }
.badge-dora-medium { background: rgba(255,167,38,0.15); color: var(--accent-orange); }
.badge-dora-low { background: rgba(239,83,80,0.15); color: var(--accent-red); }
.badge-debt-healthy { background: rgba(67,233,123,0.15); color: var(--accent-green); }
.badge-debt-warning { background: rgba(255,167,38,0.15); color: var(--accent-orange); }
.badge-debt-alert, .badge-debt-danger { background: rgba(239,83,80,0.15); color: var(--accent-red); }
.badge-hero-healthy { background: rgba(67,233,123,0.15); color: var(--accent-green); }
.badge-hero-warning { background: rgba(255,167,38,0.15); color: var(--accent-orange); }
.badge-hero-alert { background: rgba(239,83,80,0.15); color: var(--accent-red); }

/* 健康分环形图 */
.health-score-display { display: flex; justify-content: center; margin: 16px 0; }
.score-ring { position: relative; width: 120px; height: 120px; }
.score-svg { transform: rotate(-90deg); }
.ring-bg { fill: none; stroke: rgba(255,255,255,0.06); stroke-width: 8; }
.ring-fill {
  fill: none; stroke: url(#healthGradient); stroke-width: 8;
  stroke-linecap: round; stroke-dasharray: 326.73;
  transition: stroke-dashoffset 1s ease;
}
.health-excellent .ring-fill { stroke: var(--accent-green); }
.health-good .ring-fill { stroke: var(--accent-blue); }
.health-attention .ring-fill { stroke: var(--accent-orange); }
.health-danger .ring-fill { stroke: var(--accent-red); }
.score-value {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  font-size: 2rem; font-weight: 700;
}

/* 健康分分解 */
.health-breakdown { margin-top: 16px; }
.breakdown-item {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px; font-size: 0.8rem;
}
.breakdown-label { width: 70px; color: var(--text-muted); flex-shrink: 0; }
.breakdown-bar-wrapper {
  flex: 1; height: 6px; background: rgba(255,255,255,0.06);
  border-radius: 3px; overflow: hidden;
}
.breakdown-bar { height: 100%; border-radius: 3px; transition: width 1s ease; }
.breakdown-value { width: 36px; text-align: right; color: var(--text-secondary); }

/* 团队状态 */
.state-display { text-align: center; margin-bottom: 16px; }
.state-name { font-size: 1.5rem; font-weight: 700; }
.state-score { color: var(--text-muted); font-size: 0.85rem; margin-top: 4px; }
.state-dimensions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.dim-item { display: flex; justify-content: space-between; font-size: 0.8rem; padding: 6px 10px; background: rgba(255,255,255,0.03); border-radius: 6px; }
.dim-label { color: var(--text-muted); }
.positive { color: var(--accent-green); }
.negative { color: var(--accent-red); }
.neutral { color: var(--accent-blue); }
.state-desc { font-size: 0.8rem; color: var(--text-muted); line-height: 1.5; }

/* DORA */
.dora-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.dora-item {
  text-align: center; padding: 16px; background: rgba(255,255,255,0.03);
  border-radius: var(--radius-sm);
}
.dora-icon { font-size: 1.5rem; margin-bottom: 6px; }
.dora-label { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; }
.dora-value { font-size: 1.1rem; font-weight: 600; }

/* 技术债 */
.debt-display { text-align: center; }
.debt-rate { font-size: 2.5rem; font-weight: 700; margin-bottom: 12px; }
.debt-bar-wrapper {
  position: relative; height: 8px; background: rgba(255,255,255,0.06);
  border-radius: 4px; overflow: visible; margin-bottom: 16px;
}
.debt-bar {
  height: 100%; border-radius: 4px; transition: width 1s ease;
  background: linear-gradient(90deg, var(--accent-green), var(--accent-orange), var(--accent-red));
}
.debt-threshold {
  position: absolute; top: -4px; width: 2px; height: 16px;
  background: var(--accent-orange); opacity: 0.5;
}
.debt-threshold.danger { background: var(--accent-red); }
.debt-stats { display: flex; justify-content: space-around; font-size: 0.8rem; color: var(--text-muted); }

/* 英雄检测 */
.hero-display { }
.hero-team-size { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 12px; }
.contrib-item {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px; font-size: 0.8rem;
}
.contrib-rank { color: var(--text-muted); width: 24px; }
.contrib-name { width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.contrib-bar-wrapper {
  flex: 1; height: 6px; background: rgba(255,255,255,0.06);
  border-radius: 3px; overflow: hidden;
}
.contrib-bar {
  height: 100%; border-radius: 3px; transition: width 0.6s ease;
  background: var(--gradient-primary);
}
.contrib-count { width: 30px; text-align: right; color: var(--text-secondary); }

/* 趋势图 */
.chart-container { height: 300px; position: relative; }

/* 空状态 */
.empty-state {
  text-align: center; padding: 80px 20px;
}
.empty-icon { font-size: 4rem; margin-bottom: 20px; }
.empty-state h2 {
  font-size: 1.5rem; font-weight: 600;
  background: var(--gradient-primary); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent; background-clip: text;
  margin-bottom: 12px;
}
.empty-state p { color: var(--text-muted); font-size: 0.95rem; }
.empty-hint { margin-top: 8px; font-size: 0.85rem; }
</style>
