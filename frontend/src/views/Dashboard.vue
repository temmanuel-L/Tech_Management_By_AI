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
              <div class="breakdown-bar" :style="{ width: item.value + '%', background: item.color }"></div>
            </div>
            <span class="breakdown-value">
              {{ item.value.toFixed(1) }}
              <span style="color: var(--text-muted); font-size: 0.7rem;">
                (权重 {{ (item.weight * 100).toFixed(0) }}%)
              </span>
            </span>
            <div class="breakdown-tooltip" v-if="item.tip">{{ item.tip }}</div>
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
          <div 
            class="dim-item" 
            v-for="dim in stateDimensions" 
            :key="dim.label"
            :class="{ clickable: dim.clickable }"
            @click="handleDimClick(dim)"
          >
            <span class="dim-label">{{ dim.label }} <span class="dim-range">({{ dim.range }})</span></span>
            <span class="dim-value" :class="dim.cls">{{ dim.value }}</span>
            <div class="dim-tooltip" v-if="dim.tip">{{ dim.tip }}</div>
          </div>
        </div>
        <div class="state-calc-note">
          <div class="state-ranges">{{ stateScoreRanges }}</div>
          <div class="state-explanation">{{ stateCalcExplanation }}</div>
        </div>
        <p class="state-desc">{{ data.team_state.description }}</p>
      </div>

      <!-- DORA 指标 -->
      <div class="card">
        <div class="card-header">
          <h3>DORA 四指标原始值</h3>
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
        <p class="dora-note">
          本卡片展示 DORA 四指标原始值 (变更前置时间来自 MR, 其余依赖 Pipelines)。综合健康分中的「研发效能」= 本卡片四指标的综合得分 (0-100)。
        </p>
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
            <span>关键字审查偿债率: {{ data.tech_debt.fix_commit_count }} / {{ data.tech_debt.total_commit_count }}</span>
            <span v-if="data.tech_debt.llm_enhanced">
              LLM 审查偿债率: {{ data.tech_debt.llm_paying_debt_count }}/{{ data.tech_debt.llm_reviewed_mr_count + data.tech_debt.llm_reviewed_commit_count }}
            </span>
          </div>
          <p class="debt-calc-note" v-if="data.tech_debt.interest_rate_calc_note">
            {{ data.tech_debt.interest_rate_calc_note }}
          </p>
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
import { useRouter } from 'vue-router'
import { Chart, registerables } from 'chart.js'
import { runAnalysis as apiRunAnalysis, getLatest, getHistory as apiGetHistory } from '../api/client.js'

Chart.register(...registerables)

const router = useRouter()

// 点击跳转到数据下钻页面
const handleDimClick = (dim) => {
  if (dim.clickable && dim.route) {
    // 缓存当前数据到 localStorage
    if (data.value?.llm_reviews) {
      localStorage.setItem('llm_reviews', JSON.stringify(data.value.llm_reviews))
    }
    router.push(dim.route)
  }
}

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
          label: '综合健康分',
          data: history.value.map(h => h.health_score),
          borderColor: '#43e97b',
          backgroundColor: 'rgba(67, 233, 123, 0.1)',
          fill: true, tension: 0.4,
        },
        {
          label: '研发效能 (DORA, ×100)',
          data: history.value.map(h => h.dora_overall_score * 100),
          borderColor: '#42a5f5',
          tension: 0.4,
        },
        {
          label: '技术债利息率 (×100)',
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

// 健康分维度分解 (技术债健康度 = 1-利息率, 0-100 越高越健康)
const HEALTH_BREAKDOWN_TIPS = {
  '研发效能 (DORA)': '数据: MR 变更前置时间、Pipelines 部署频率/变更失败率/MTTR。计算: 四指标各自按等级映射 (Low=0.25, Medium=0.5, High=0.75, Elite=1.0)，取算术平均后×100 得 0-100 分；卡片上的综合等级(如 MEDIUM)仅作展示，分数由四指标平均决定，故可能为 50~75 等中间值。权重 30%。',
  '技术债健康度': '数据: Commits 涉及偿还技术债的提交、LLM 偿债/新增债判定。计算: 健康度 = 1 - 技术债利息率，0-100 越高越健康，权重 25%。',
  '协作均衡': '数据: Commits 作者分布。计算: 1 - 基尼系数，0-100 越均匀越好，权重 20%。',
  '团队状态': '数据: Issues/MR/LLM 审查。计算: 四状态映射为 0-100 分，权重 25%。',
}
const healthBreakdown = computed(() => {
  if (!data.value) return []
  const h = data.value.health
  return [
    { label: '研发效能 (DORA)', value: h.dora_score, weight: h.w_dora, color: 'var(--accent-blue)', tip: HEALTH_BREAKDOWN_TIPS['研发效能 (DORA)'] },
    { label: '技术债健康度', value: h.debt_score, weight: h.w_debt, color: 'var(--accent-orange)', tip: HEALTH_BREAKDOWN_TIPS['技术债健康度'] },
    { label: '协作均衡', value: h.hero_score, weight: h.w_hero, color: 'var(--accent-purple)', tip: HEALTH_BREAKDOWN_TIPS['协作均衡'] },
    { label: '团队状态', value: h.state_score, weight: h.w_state, color: 'var(--accent-green)', tip: HEALTH_BREAKDOWN_TIPS['团队状态'] },
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

// 团队状态各子指标: 值域、数据来源与计算逻辑 (用于 tooltip)
const STATE_DIM_META = {
  积压趋势: {
    range: '[-1,1] 正值=积压减少 负值=增加',
    tip: '数据: Issues 的 tasks_closed/tasks_created/total_backlog，或 MR 的 merged_count/total_mr_count。计算: 有 Issues 时 (关闭-新增)/积压 截断至[-1,1]；无 Issues 时以 MR 合并率为代理，(合并率-0.85)×2 截断至[-1,1]，85% 合并率视为中性(0)，避免长期满分。',
  },
  偿债占比: {
    range: '[-1,1] 0.4 最优，过高或过低均降分',
    tip: '数据: LLM 偿债数/总审查数，或 Issues 债务任务占比。计算: 偿债占比 0.4 时得分 1，0 时 -0.1，1 时 -1；[0,0.4] 单调增，(0.4,1] 单调减。',
  },
  士气: {
    range: '[-1,1] 越高越好 (0=中性)',
    tip: '数据: MR 的 comments_count、team_size。计算: 2×(reviews/team/5)-1 映射到[-1,1]。',
  },
  创新占比: {
    range: '[-0.5,1] 越高越好（约10–20%映射到0，100%→1）',
    tip: '数据: LLM 或 Issues。计算: 非线性映射，占比 0→-0.5、约15%→0、100%→1，权重 20%。',
  },
  新增技术债任务占比: {
    range: '[-1, 0.5] 无新增=0.5，全部新增=-1（非线性）',
    tip: '数据: LLM 审查的 is_creating_debt 判定。计算: 非线性映射，0→0.5、约1/8→0.2、2/8→0、3/8→-0.2、全部新增→-1，放大新增债惩罚，权重 20%。',
  },
}
// 团队状态子指标颜色：>=0.3 绿，0<=得分<0.3 黄，<0 红
function stateDimCls(score) {
  const v = score ?? 0
  if (v >= 0.3) return 'positive'
  if (v >= 0) return 'neutral'
  return 'negative'
}
// 团队状态维度 (新增技术债任务占比 有 LLM 时常显)
const stateDimensions = computed(() => {
  if (!data.value) return []
  const s = data.value.team_state
  const dims = [
    { label: '积压趋势', ...STATE_DIM_META.积压趋势, value: s.backlog_score?.toFixed(3) ?? '-', cls: stateDimCls(s.backlog_score), clickable: false },
    { label: '偿债占比', ...STATE_DIM_META.偿债占比, value: s.debt_score?.toFixed(3) ?? '-', cls: stateDimCls(s.debt_score), clickable: true, route: '/drilldown/paying_debt' },
    { label: '士气', ...STATE_DIM_META.士气, value: s.morale_score?.toFixed(3) ?? '-', cls: stateDimCls(s.morale_score), clickable: false },
    { label: '创新占比', ...STATE_DIM_META.创新占比, value: s.innovation_score?.toFixed(3) ?? '-', cls: stateDimCls(s.innovation_score), clickable: true, route: '/drilldown/innovation' },
  ]
  // 始终显示新增技术债任务占比 (无 LLM 时为 0)，值域 [-1, 0.5]
  dims.push({
    label: '新增技术债任务占比',
    ...STATE_DIM_META.新增技术债任务占比,
    value: (s.creating_debt_score ?? 0).toFixed(3),
    cls: stateDimCls(s.creating_debt_score),
    clickable: true,
    route: '/drilldown/creating_debt',
  })
  return dims
})
// 加权得分分箱说明 (API 未返回时使用默认)
const stateScoreRanges = computed(() => {
  const s = data.value?.team_state?.score_ranges
  return s && s.trim() ? s : '得分区间: 落后 S<-0.3 | 停滞 -0.3≤S<0 | 偿债 0≤S<0.3 | 创新 S≥0.3'
})
// 加权计算过程 (API 未返回时根据当前值拼接)
const stateCalcExplanation = computed(() => {
  const s = data.value?.team_state
  if (!s) return ''
  const expl = s.calc_explanation
  if (expl && expl.trim()) return expl
  const parts = [
    `积压=${(s.backlog_score ?? 0).toFixed(3)}`,
    `偿债=${(s.debt_score ?? 0).toFixed(3)}`,
    `士气=${(s.morale_score ?? 0).toFixed(3)}`,
    `创新=${(s.innovation_score ?? 0).toFixed(3)}`,
    `新增债占比=${(s.creating_debt_score ?? 0).toFixed(3)}`,
  ]
  const formula = 'S = 积压趋势×20% + 偿债占比×20% + 士气×20% + 创新占比×20% + 新增技术债任务占比×20%'
  return `${formula} | 当前: ${parts.join(' ')} → S=${(s.score ?? 0).toFixed(3)}`
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
  margin-bottom: 8px; font-size: 0.8rem; position: relative; cursor: help;
}
.breakdown-tooltip {
  position: absolute; left: 0; bottom: 100%; margin-bottom: 6px; padding: 8px 10px;
  font-size: 0.7rem; line-height: 1.4; color: #e6e6e6; background: rgba(20,22,30,0.98);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  opacity: 0; visibility: hidden; transition: opacity 0.2s, visibility 0.2s; z-index: 100;
  pointer-events: none; max-width: 280px; text-align: left;
}
.breakdown-item:hover .breakdown-tooltip { opacity: 1; visibility: visible; }
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
.dim-item { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; font-size: 0.8rem; padding: 8px 10px; background: rgba(255,255,255,0.03); border-radius: 6px; position: relative; cursor: help; }
.dim-item.clickable { cursor: pointer; }
.dim-item.clickable:hover { background: rgba(255,255,255,0.06); }
.dim-label { color: var(--text-muted); flex: 1; min-width: 0; line-height: 1.3; }
.dim-range { font-size: 0.7rem; color: var(--text-muted); opacity: 0.9; font-weight: normal; display: block; margin-top: 2px; }
.dim-tooltip {
  position: absolute; left: 0; right: 0; bottom: 100%; margin-bottom: 6px; padding: 8px 10px;
  font-size: 0.7rem; line-height: 1.4; color: #e6e6e6; background: rgba(20,22,30,0.98);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  opacity: 0; visibility: hidden; transition: opacity 0.2s, visibility 0.2s; z-index: 100;
  pointer-events: none; max-width: 320px; text-align: left;
}
.dim-item:hover .dim-tooltip { opacity: 1; visibility: visible; }
.state-calc-note { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 12px; padding: 8px 10px; background: rgba(255,255,255,0.02); border-radius: 6px; }
.state-ranges { font-weight: 600; margin-bottom: 4px; }
.state-explanation { line-height: 1.4; word-break: break-word; }
.positive { color: var(--accent-green); }
.negative { color: var(--accent-red); }
.neutral { color: #e6a23c; } /* 0<=得分<0.3 黄色 */
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
.debt-stats { display: flex; justify-content: space-around; font-size: 0.8rem; color: var(--text-muted); margin-top: 8px; }
.debt-calc-note { font-size: 0.75rem; color: var(--text-muted); margin-top: 12px; line-height: 1.4; text-align: left; }

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
