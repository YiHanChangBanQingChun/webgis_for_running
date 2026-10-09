/** Load every page so a larger export cannot silently truncate the explorer. */
export async function fetchAllActivities<T>(filters: Record<string, string> = {}): Promise<T[]> {
  const items: T[] = []
  const pageSize = 250
  while (true) {
    const params = new URLSearchParams({ ...filters, limit: String(pageSize), offset: String(items.length) })
    const response = await fetch(`/api/activities?${params}`)
    if (!response.ok) throw new Error('Activity API unavailable')
    const page = await response.json() as { total: number; items: T[] }
    if (page.items.length === 0 && items.length < page.total) throw new Error('Incomplete activity page')
    items.push(...page.items)
    if (items.length >= page.total) return items
  }
}
