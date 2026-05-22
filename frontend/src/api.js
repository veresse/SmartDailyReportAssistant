/** API 基础 URL 配置。开发时代理至后端 8000 端口。 */
export const API_BASE = '/api'

/**
 * 获取所有可用日期列表。
 * @returns {Promise<Array<{date: string, status: string}>>}
 */
export async function fetchDates() {
  const resp = await fetch(`${API_BASE}/dates`)
  if (!resp.ok) throw new Error('获取日期列表失败')
  return resp.json()
}

/**
 * 获取早报列表。
 * @param {number} limit
 * @returns {Promise<Array>}
 */
export async function fetchBriefings(limit = 30) {
  const resp = await fetch(`${API_BASE}/briefings?limit=${limit}`)
  if (!resp.ok) throw new Error('获取早报列表失败')
  return resp.json()
}

/**
 * 获取指定日期的早报详情。
 * @param {string} date - YYYY-MM-DD
 * @returns {Promise<Object>}
 */
export async function fetchBriefingDetail(date) {
  const resp = await fetch(`${API_BASE}/briefings/${date}`)
  if (!resp.ok) {
    if (resp.status === 404) return null
    throw new Error('获取早报详情失败')
  }
  return resp.json()
}

/**
 * 删除指定日期的早报及关联数据。
 * @param {string} date - YYYY-MM-DD
 * @returns {Promise<Object>}
 */
export async function deleteBriefing(date) {
  const resp = await fetch(`${API_BASE}/briefings/${date}`, { method: 'DELETE' })
  if (!resp.ok) {
    const message = await resp.text()
    throw new Error(message || '删除早报失败')
  }
  return resp.json()
}
