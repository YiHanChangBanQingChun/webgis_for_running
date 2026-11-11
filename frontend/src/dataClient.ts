import { assetUrl, demoManifest, isStaticDemo } from './siteConfig'
import { heatGrid, monthlyStats, queryActivities, rangeStats } from './staticData'
import type { PublicActivity, SpatialGrid } from './staticData'

const cache = new Map<string, Promise<unknown>>()
function read<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    const pending = fetch(assetUrl(`data/${path}`))
      .then((response) => {
        if (!response.ok) throw new Error(`展示数据读取失败：${response.status}`)
        return response.json()
      })
      .catch((error) => {
        cache.delete(path)
        throw error
      })
    cache.set(path, pending)
  }
  return cache.get(path)! as Promise<T>
}
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  if (!isStaticDemo) return fetch(input, init)
  init?.signal?.throwIfAborted()
  const url = new URL(input, window.location.href)
  const query = url.searchParams
  let result: unknown
  const activities = await read<PublicActivity[]>('activities.json')
  switch (url.pathname) {
    case '/api/activities':
      result = queryActivities(activities, query)
      break
    case '/api/calendar':
      result = await read('calendar.json')
      break
    case '/api/quality-report':
      result = await read('quality-report.json')
      break
    case '/api/athlete-profile':
      result = await read('athlete-profile.json')
      break
    case '/api/stats/monthly':
      result = monthlyStats(activities, query.get('month') || demoManifest.default_month)
      break
    case '/api/stats/range':
      result = rangeStats(
        activities,
        query.get('start') || '',
        query.get('end') || '',
        demoManifest.continuous_ranges,
      )
      break
    case '/api/map/heat-grid':
      result = heatGrid(await read<SpatialGrid>('spatial-grid.json'), query)
      break
    default: {
      const match = url.pathname.match(
        /^\/api\/activities\/([A-Za-z0-9_-]+)(?:\/(track|insights))?$/,
      )
      const activity = activities.find((a) => a.id === match?.[1])
      if (!match || !activity) return Response.json({ detail: '未公开该活动' }, { status: 404 })
      result =
        match[2] === 'track'
          ? await read(`tracks/${activity.id}.geojson`)
          : match[2] === 'insights'
            ? await read(`insights/${activity.id}.json`)
            : activity
    }
  }
  init?.signal?.throwIfAborted()
  return Response.json(result)
}
