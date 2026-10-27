// Thin client for the ClimateGuard API. Local dev: `python backend/scripts/local_api.py`.
const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8787').replace(/\/$/, '')

// Mirrors backend/src/climateguard/cities.py
export const CITIES = [
  { slug: 'stockton', name: 'Stockton' },
  { slug: 'lodi', name: 'Lodi' },
  { slug: 'manteca', name: 'Manteca' },
  { slug: 'tracy', name: 'Tracy' },
  { slug: 'modesto', name: 'Modesto' },
  { slug: 'merced', name: 'Merced' },
]

export class ApiError extends Error {
  constructor(code, status) {
    super(code)
    this.code = code
    this.status = status
  }
}

async function request(path, options) {
  let res
  try {
    res = await fetch(`${API_URL}${path}`, options)
  } catch {
    throw new ApiError('network', 0)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(body.error || 'default', res.status)
  return body
}

export const getCityAlerts = (city) => request(`/cities/${city}/alerts`)

export const subscribe = ({ email, city, lang, website }) =>
  request('/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, city, lang, website }),
  })
