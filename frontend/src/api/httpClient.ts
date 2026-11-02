import type { User } from '../types/domain'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? '/api/v1'
const SESSION_KEY = 'fla.http.session.v1'

export interface StoredSession {
  accessToken: string
  refreshToken: string
  user: User
}

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: {
    id: string
    nickname: string
    role: 'user' | 'admin'
    status: 'active' | 'disabled'
    created_at: string
    last_active_at: string | null
  }
}

const mapUser = (raw: TokenResponse['user']): User => ({
  id: raw.id,
  nickname: raw.nickname,
  role: raw.role,
  status: raw.status,
  createdAt: raw.created_at,
  lastActiveAt: raw.last_active_at ?? raw.created_at,
})

const readSession = (): StoredSession | null => {
  const value = localStorage.getItem(SESSION_KEY)
  if (!value) return null
  try {
    return JSON.parse(value) as StoredSession
  } catch {
    localStorage.removeItem(SESSION_KEY)
    return null
  }
}

const writeSession = (response: TokenResponse): StoredSession => {
  const session = {
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
    user: mapUser(response.user),
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  return session
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(message: string, status: number, code = 'api_error', details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

let refreshPromise: Promise<StoredSession | null> | null = null
const unauthorizedListeners = new Set<() => void>()

const notifyUnauthorized = () => {
  localStorage.removeItem(SESSION_KEY)
  for (const listener of unauthorizedListeners) listener()
}

export const subscribeUnauthorized = (listener: () => void): (() => void) => {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

const refreshSession = async (): Promise<StoredSession | null> => {
  const current = readSession()
  if (!current?.refreshToken) return null
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: current.refreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) {
          notifyUnauthorized()
          return null
        }
        return writeSession((await response.json()) as TokenResponse)
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

const parseError = async (response: Response): Promise<ApiError> => {
  let body: Record<string, unknown> | null = null
  try {
    body = (await response.json()) as Record<string, unknown>
  } catch {
    // Non-JSON proxy/server errors use the HTTP status text below.
  }
  const error = body?.error as
    | { code?: string; message?: string; details?: unknown }
    | undefined
  return new ApiError(
    error?.message ?? response.statusText ?? '请求失败',
    response.status,
    error?.code ?? 'api_error',
    error?.details,
  )
}

async function send(path: string, init: RequestInit, allowRefresh: boolean): Promise<Response> {
  const session = readSession()
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (session?.accessToken) headers.set('Authorization', `Bearer ${session.accessToken}`)
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  if (response.status === 401 && allowRefresh && session?.refreshToken) {
    const refreshed = await refreshSession()
    if (refreshed) return send(path, init, false)
    notifyUnauthorized()
  } else if (response.status === 401) {
    notifyUnauthorized()
  }
  return response
}

export const request = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const response = await send(path, init, true)
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const requestResponse = async (path: string, init: RequestInit = {}): Promise<Response> => {
  const response = await send(path, init, true)
  if (!response.ok) throw await parseError(response)
  return response
}

export const authSession = {
  current: (): User | null => readSession()?.user ?? null,

  async login(nickname: string, password: string): Promise<User> {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname, password }),
    })
    if (!response.ok) throw await parseError(response)
    return writeSession((await response.json()) as TokenResponse).user
  },

  async register(nickname: string, password: string): Promise<User> {
    const response = await fetch(`${API_BASE_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname, password }),
    })
    if (!response.ok) throw await parseError(response)
    return writeSession((await response.json()) as TokenResponse).user
  },

  logout(): void {
    const session = readSession()
    localStorage.removeItem(SESSION_KEY)
    if (session?.refreshToken) {
      void fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: session.refreshToken }),
      }).catch(() => undefined)
    }
  },
}

export const apiBaseUrl = API_BASE_URL
export const mapApiUser = mapUser
