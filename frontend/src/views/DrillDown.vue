<template>
  <div class="drilldown-page">
    <div class="page-header">
      <button class="back-btn" @click="goBack">← 返回团队状态</button>
      <h2>{{ pageTitle }}</h2>
      <p class="page-desc">{{ pageDesc }}</p>
    </div>

    <!-- 抽样信息 -->
    <div class="card sample-info">
      <h3>抽样逻辑说明</h3>
      <div class="info-row">
        <span class="label">抽样方法:</span>
        <span class="value">{{ sampleInfo.sample_method || '无' }}</span>
      </div>
      <div class="info-row">
        <span class="label">抽样数量:</span>
        <span class="value">{{ sampleInfo.sample_count }} / {{ sampleInfo.total_count }}</span>
      </div>
      <div class="info-row">
        <span class="label">数据来源:</span>
        <span class="value source-badge" :class="sampleInfo.source">{{ sampleInfo.source || 'unknown' }}</span>
      </div>
    </div>

    <!-- 符合条件的 commit 或 merge request 列表 -->
    <div class="card">
      <h3>{{ filteredTitle }}</h3>
      <div v-if="filteredItems.length === 0" class="empty-state">
        暂无符合条件的 commit 或 merge request
      </div>
      <div v-else class="commit-list">
        <div v-for="(item, index) in filteredItems" :key="index" class="commit-item">
          <div class="commit-header">
            <span class="commit-sha">{{ item.sha ? item.sha.slice(0, 8) : `MR #${item.mr_id}` }}</span>
            <span v-if="item.author" class="commit-author">{{ item.author }}</span>
            <span class="commit-score">质量: {{ item.quality_score }}/10</span>
          </div>
          <div class="commit-message">{{ item.message }}</div>
          
          <!-- 判定结果 -->
          <div class="commit-result" :class="resultClass">
            <span class="result-label">{{ resultLabel }}</span>
            <span class="result-reason">{{ getReason(item) }}</span>
          </div>
          
          <!-- 问题代码（仅新增技术债且有 code_block 时） -->
          <div v-if="drillType === 'creating_debt' && item.is_creating_debt_code_block" class="commit-code-block creating">
            <div class="code-block-inner" v-html="renderDebtCodeBlock(item.is_creating_debt_code_block)"></div>
          </div>
          
          <!-- 改进建议（仅新增技术债有） -->
          <div v-if="drillType === 'creating_debt' && item.is_creating_debt_correct_action" class="commit-action">
            <span class="action-label">改进建议:</span>
            <span class="action-text">{{ item.is_creating_debt_correct_action }}</span>
          </div>
          
          <!-- 代码 diff（可展开） -->
          <div class="diff-section">
            <button class="diff-toggle" @click="toggleDiff(index)">
              {{ expandedIndex === index ? '收起代码 diff' : '查看代码 diff' }}
            </button>
            <pre v-if="expandedIndex === index" class="diff-content">{{ item.diff }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 全部样本列表（可折叠） -->
    <div class="card">
      <button class="expand-btn" @click="showAllSamples = !showAllSamples">
        {{ showAllSamples ? '收起' : '展开' }}全部审查样本 ({{ allSamples.length }} 条)
      </button>
      <div v-if="showAllSamples" class="all-samples">
        <div v-for="(item, index) in allSamples" :key="index" class="sample-row">
          <span class="sample-sha">{{ item.sha ? item.sha.slice(0, 8) : `MR #${item.mr_id}` }}</span>
          <span v-if="item.author" class="sample-author">{{ item.author }}</span>
          <span class="sample-msg">{{ item.message?.slice(0, 50) }}...</span>
          <span class="sample-tags">
            <span v-if="item.is_paying_debt" class="tag paying">偿债</span>
            <span v-if="item.is_creating_debt" class="tag creating">新增债</span>
            <span v-if="item.is_adding_new_function" class="tag innovation">创新</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDrilldown, getLatest } from '../api/client.js'

const route = useRoute()
const router = useRouter()

// 从路由参数获取下钻类型
const drillType = computed(() => route.params.drill_type || 'paging_debt')

// 页面状态
const sampleInfo = ref({})
const allSamples = ref([])
const filteredItems = ref([])
const totalCount = ref(0)  // 符合筛选条件的总数
const expandedIndex = ref(null)
const showAllSamples = ref(false)

// 页面标题和描述
const pageTitle = computed(() => {
  const titles = {
    'paying_debt': '偿还技术债分析',
    'creating_debt': '新增技术债分析',
    'innovation': '创新功能分析'
  }
  return titles[drillType.value] || '团队状态分析'
})

const pageDesc = computed(() => {
  const descs = {
    'paying_debt': '以下 commit 或 merge request 被判定为在偿还技术债（修复 bug、重构优化、清理冗余等）',
    'creating_debt': '以下 commit 或 merge request 被判定为在引入技术债，需要关注并改进',
    'innovation': '以下 commit 或 merge request 被判定为在新增业务功能'
  }
  return descs[drillType.value] || ''
})

const filteredTitle = computed(() => {
  const titles = {
    'paying_debt': '偿还技术债的 commit 或 merge request',
    'creating_debt': '引入技术债的 commit 或 merge request',
    'innovation': '新增业务功能的 commit 或 merge request'
  }
  const baseTitle = titles[drillType.value] || '符合条件的 commit 或 merge request'
  const count = totalCount.value || filteredItems.value.length
  return `${baseTitle}（共 ${count} 个）`
})

const resultClass = computed(() => {
  const classes = {
    'paying_debt': 'paying',
    'creating_debt': 'creating',
    'innovation': 'innovation'
  }
  return classes[drillType.value]
})

const resultLabel = computed(() => {
  const labels = {
    'paying_debt': '偿还技术债原因:',
    'creating_debt': '引入技术债原因:',
    'innovation': '创新功能原因:'
  }
  return labels[drillType.value] || '判定原因:'
})

const getReason = (item) => {
  if (drillType.value === 'paying_debt') return item.is_paying_debt_reason
  if (drillType.value === 'creating_debt') return item.is_creating_debt_reason
  if (drillType.value === 'innovation') return item.is_adding_new_function_reason
  return ''
}

/** 将 is_creating_debt_code_block 的 Markdown（**问题代码** + ``` 代码块 ```）转为安全 HTML */
function renderDebtCodeBlock(raw) {
  if (!raw || typeof raw !== 'string') return ''
  const escape = (s) => String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  const parts = raw.split(/```/)
  let out = ''
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) {
      let seg = parts[i].replace(/\*\*问题代码\*\*/g, '{{BOLD}}')
      seg = escape(seg).replace(/\n/g, '<br/>').replace(/\{\{BOLD\}\}/g, '<strong>问题代码</strong>')
      out += seg
    } else {
      out += '<pre class="debt-code-block"><code>' + escape(parts[i].replace(/^\n+|\n+$/g, '')) + '</code></pre>'
    }
  }
  return out
}

const toggleDiff = (index) => {
  expandedIndex.value = expandedIndex.value === index ? null : index
}

const goBack = () => {
  router.push('/')
}

// 从 API 获取数据下钻信息（抽样说明、分母等由后端根据配置与快照计算）
onMounted(async () => {
  try {
    // 优先使用下钻接口：后端返回正确的抽样方法说明（来自 config）和抽样数量/总量（来自快照）
    const drill = await getDrilldown(drillType.value)
    if (drill && (drill.sample_info || drill.all_samples?.length > 0)) {
      sampleInfo.value = {
        sample_method: drill.sample_info?.sample_method ?? 'LLM 审查',
        sample_count: drill.sample_info?.sample_count ?? drill.all_samples?.length ?? 0,
        total_count: drill.sample_info?.total_count ?? drill.all_samples?.length ?? 0,
        source: drill.sample_info?.source ?? 'llm'
      }
      allSamples.value = drill.all_samples ?? []
      filteredItems.value = drill.filtered_items ?? []
      totalCount.value = drill.total_count ?? drill.filtered_items?.length ?? 0
      return
    }

    // 无下钻数据时，尝试从「最新指标」接口 + 本地缓存补全（向后兼容）
    const latest = await getLatest()
    if (latest?.llm_reviews?.length > 0) {
      const reviews = latest.llm_reviews
      allSamples.value = reviews
      if (drillType.value === 'paying_debt') filteredItems.value = reviews.filter(r => r.is_paying_debt)
      else if (drillType.value === 'creating_debt') filteredItems.value = reviews.filter(r => r.is_creating_debt)
      else if (drillType.value === 'innovation') filteredItems.value = reviews.filter(r => r.is_adding_new_function)
      totalCount.value = filteredItems.value.length
      sampleInfo.value = {
        sample_method: latest.sample_info?.sample_method || 'LLM 审查',
        sample_count: latest.sample_info?.sample_count ?? reviews.length,
        total_count: latest.sample_info?.total_count ?? reviews.length,
        source: latest.sample_info?.source || 'llm'
      }
      return
    }

    const cached = localStorage.getItem('llm_reviews')
    if (cached) {
      const reviews = JSON.parse(cached)
      allSamples.value = reviews
      if (drillType.value === 'paying_debt') filteredItems.value = reviews.filter(r => r.is_paying_debt)
      else if (drillType.value === 'creating_debt') filteredItems.value = reviews.filter(r => r.is_creating_debt)
      else if (drillType.value === 'innovation') filteredItems.value = reviews.filter(r => r.is_adding_new_function)
      totalCount.value = filteredItems.value.length
      sampleInfo.value = {
        sample_method: '从本地缓存加载',
        sample_count: reviews.length,
        total_count: reviews.length,
        source: 'local'
      }
      return
    }

    filteredItems.value = []
    totalCount.value = 0
    sampleInfo.value = {
      sample_method: '请先运行分析（需开启 LLM 审查）',
      sample_count: 0,
      total_count: 0,
      source: 'none'
    }
  } catch (e) {
    console.error('加载数据失败:', e)
    filteredItems.value = []
    sampleInfo.value = {
      sample_method: '加载数据失败',
      sample_count: 0,
      total_count: 0,
      source: 'error'
    }
  }
})
</script>

<style scoped>
.drilldown-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  margin-bottom: 24px;
}

.back-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 16px;
}

.back-btn:hover {
  background: var(--bg-card-hover);
}

.page-header h2 {
  font-size: 1.5rem;
  margin-bottom: 8px;
}

.page-desc {
  color: var(--text-muted);
}

.card {
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}

.card h3 {
  font-size: 1.1rem;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
}

.sample-info .info-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.sample-info .label {
  color: var(--text-muted);
  min-width: 80px;
}

.source-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.8rem;
}

.source-badge.llm {
  background: rgba(66, 165, 245, 0.2);
  color: var(--accent-blue);
}

.source-badge.keyword {
  background: rgba(255, 167, 38, 0.2);
  color: var(--accent-orange);
}

.commit-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.commit-item {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
}

.commit-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.commit-sha {
  font-family: monospace;
  color: var(--accent-blue);
  font-weight: 600;
}

.commit-author {
  color: var(--text-muted);
  font-size: 0.9rem;
  margin-left: 12px;
}

.commit-score {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.commit-message {
  color: var(--text-secondary);
  margin-bottom: 12px;
  line-height: 1.5;
}

.commit-result {
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}

.commit-result.paying {
  background: rgba(76, 175, 80, 0.1);
  border-left: 3px solid var(--accent-green);
}

.commit-result.creating {
  background: rgba(239, 83, 80, 0.1);
  border-left: 3px solid var(--accent-red);
}

/* 问题代码块：与引入技术债原因同套红色系 */
.commit-code-block.creating {
  background: rgba(239, 83, 80, 0.1);
  border-left: 3px solid var(--accent-red);
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}

.commit-code-block .code-block-inner {
  color: var(--text-secondary);
}

.commit-code-block .debt-code-block {
  margin: 8px 0 0;
  padding: 12px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  font-size: 0.85rem;
  overflow-x: auto;
  white-space: pre;
}

.commit-code-block .debt-code-block code {
  font-family: ui-monospace, monospace;
}

.commit-result.innovation {
  background: rgba(66, 165, 245, 0.1);
  border-left: 3px solid var(--accent-blue);
}

.result-label {
  font-weight: 600;
  display: block;
  margin-bottom: 4px;
}

.result-reason {
  color: var(--text-secondary);
}

.commit-action {
  background: rgba(255, 167, 38, 0.1);
  padding: 12px;
  border-radius: 6px;
  border-left: 3px solid var(--accent-orange);
}

.action-label {
  font-weight: 600;
  display: block;
  margin-bottom: 4px;
}

.action-text {
  color: var(--text-secondary);
}

.diff-section {
  margin-top: 12px;
}

.diff-toggle {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}

.diff-toggle:hover {
  background: var(--bg-card);
}

.diff-content {
  margin-top: 8px;
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  font-size: 0.8rem;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
}

.expand-btn {
  width: 100%;
  background: transparent;
  border: none;
  color: var(--accent-blue);
  padding: 12px;
  cursor: pointer;
  font-size: 0.9rem;
}

.all-samples {
  margin-top: 12px;
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.sample-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.85rem;
}

.sample-sha {
  font-family: monospace;
  color: var(--text-muted);
  min-width: 80px;
}

.sample-author {
  color: var(--text-secondary);
  min-width: 80px;
}

.sample-msg {
  flex: 1;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sample-tags {
  display: flex;
  gap: 4px;
}

.tag {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.7rem;
}

.tag.paying {
  background: rgba(76, 175, 80, 0.2);
  color: var(--accent-green);
}

.tag.creating {
  background: rgba(239, 83, 80, 0.2);
  color: var(--accent-red);
}

.tag.innovation {
  background: rgba(66, 165, 245, 0.2);
  color: var(--accent-blue);
}
</style>
