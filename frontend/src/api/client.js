import axios from 'axios'

const api = axios.create({
    baseURL: '/api',
    timeout: 30000,
})

/**
 * 触发一次完整分析
 * @param {string} source - 数据源: 'mock' 或 'gitlab'
 * @param {number} days - 分析天数
 * @param {boolean} enableLlmReview - 是否对 MR 进行 LLM 代码审查 (会调用大模型)
 */
export async function runAnalysis(source = 'mock', days = 30, enableLlmReview = false) {
    const params = new URLSearchParams({ source, days: String(days) })
    if (enableLlmReview) params.set('enable_llm_review', 'true')
    const { data } = await api.post(`/analyze?${params}`)
    return data
}

/** 获取最新一次分析结果 */
export async function getLatest() {
    const { data } = await api.get('/metrics/latest')
    return data
}

/** 获取历史数据 */
export async function getHistory(days = 90) {
    const { data } = await api.get(`/metrics/history?days=${days}`)
    return data
}

/** 团队规模校准 */
export async function checkTeamSizing(params) {
    const { data } = await api.post('/team-sizing', params)
    return data
}

/** 健康检查 */
export async function healthCheck() {
    const { data } = await api.get('/health')
    return data
}
