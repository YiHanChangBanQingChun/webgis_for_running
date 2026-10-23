// 活动接口相关的请求工具，供多个页面复用。
/**
 * 后端活动接口采用分页；这里依次读取所有页，避免概览页在记录变多后被静默截断。
 */
export async function fetchAllActivities<T>(
  filters: Record<string, string> = {},
  signal?: AbortSignal,
): Promise<T[]> {
  const items: T[] = []
  const pageSize = 250
  while (true) {
    // offset 表示已经读取的数量，limit 表示本次最多读取的记录数。
    const params = new URLSearchParams({
      ...filters,
      limit: String(pageSize),
      offset: String(items.length),
    })
    const response = await fetch(`/api/activities?${params}`, { signal })
    if (!response.ok) throw new Error('Activity API unavailable')
    const page = (await response.json()) as { total: number; items: T[] }
    // 空页面但总数仍未完成，说明分页数据不完整，应显式报错而不是静默返回。
    if (page.items.length === 0 && items.length < page.total)
      throw new Error('Incomplete activity page')
    items.push(...page.items)
    if (items.length >= page.total) return items
  }
}
