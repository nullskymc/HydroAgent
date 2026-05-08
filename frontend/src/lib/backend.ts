import 'server-only'

type FetchOptions = {
  method?: string
  body?: BodyInit | null
  headers?: HeadersInit
  searchParams?: URLSearchParams
  authToken?: string | null
}

const BACKEND_URL = process.env.BACKEND_API_BASE_URL || 'http://127.0.0.1:7860'

export function getBackendUrl(path: string, searchParams?: URLSearchParams) {
  const url = new URL(path, BACKEND_URL)
  if (searchParams) {
    url.search = searchParams.toString()
  }
  return url.toString()
}

export async function fetchBackend(path: string, options: FetchOptions = {}) {
  const response = await fetch(getBackendUrl(path, options.searchParams), {
    method: options.method || 'GET',
    body: options.body,
    headers: {
      Accept: 'application/json',
      ...(options.authToken ? { Authorization: `Bearer ${options.authToken}` } : {}),
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
    cache: 'no-store',
  })

  return response
}

export async function fetchBackendJson<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const response = await fetchBackend(path, options)

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Backend request failed: ${response.status}`)
  }

  return (await response.json()) as T
}
