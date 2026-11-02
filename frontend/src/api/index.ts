import { httpApi } from './httpApi'
import { mockAgent } from './mockAgent'
import {
  actionApi,
  adminApi,
  authApi,
  conversationApi,
  learningApi,
  practiceApi,
  taskApi,
  vocabularyApi,
} from './mockApi'
import { initializeStorage } from './storage'

export type ApiMode = 'mock' | 'http'

export const apiMode: ApiMode =
  import.meta.env.VITE_API_MODE === 'mock' ? 'mock' : 'http'

const mockApi = {
  auth: authApi,
  task: taskApi,
  vocabulary: vocabularyApi,
  practice: practiceApi,
  learning: learningApi,
  conversation: conversationApi,
  admin: adminApi,
  action: actionApi,
  agent: mockAgent,
} as unknown as typeof httpApi

if (apiMode === 'mock') initializeStorage()

/**
 * Production composition root. Pages depend on this interface, never on fetch
 * or LocalStorage. Mock mode is opt-in and isolated to local UI development.
 */
export const api = apiMode === 'mock' ? mockApi : httpApi
export type ApplicationApi = typeof api
