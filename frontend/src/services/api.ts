import type { DiffResponse, Health, VersionsResponse } from '../types'

const BASE = (import.meta.env.BASE_URL ?? '/').replace(/\/$/, '') + '/api'

async function request<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers ?? {}) },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Request failed')
  }
  return res.json() as Promise<T>
}

export function getHealth(): Promise<Health> {
  return request('/health')
}

export function getVersions(refresh = false): Promise<VersionsResponse> {
  return request(`/versions${refresh ? '?refresh=true' : ''}`)
}

export function postDiff(source: string, destination: string, refresh = false): Promise<DiffResponse> {
  return request('/diff', {
    method: 'POST',
    body: JSON.stringify({ source, destination, refresh }),
  })
}

export function postSummary(source: string, destination: string): Promise<{ summary: string }> {
  return request('/diff/summary', {
    method: 'POST',
    body: JSON.stringify({ source, destination }),
  })
}
