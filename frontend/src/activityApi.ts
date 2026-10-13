/**
 * 后端活动接口采用分页；这里依次读取所有页，避免概览页在记录变多后被静默截断。
 */
export async function fetchAllActivities<T>(filters: Record<string, string> = {}): Promise<T[]> {
  const items: T[] = []
  const pageSize = 250
  while (true) {
    const params = new URLSearchParams({
      ...filters,
      limit: String(pageSize),
      offset: String(items.length),
    })
    const response = await fetch(`/api/activities?${params}`)
    if (!response.ok) throw new Error('Activity API unavailable')
    const page = (await response.json()) as { total: number; items: T[] }
    if (page.items.length === 0 && items.length < page.total)
      throw new Error('Incomplete activity page')
    items.push(...page.items)
    if (items.length >= page.total) return items
  }
}
