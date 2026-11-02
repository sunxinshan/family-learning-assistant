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
import { mockAgent } from './mockAgent'

/**
 * Composition root for the frontend API boundary.
 *
 * Phase 0 uses the Mock implementation. A later HTTP adapter must implement the
 * same surface so page components do not depend on LocalStorage or Mock details.
 */
export const api = {
  auth: authApi,
  task: taskApi,
  vocabulary: vocabularyApi,
  practice: practiceApi,
  learning: learningApi,
  conversation: conversationApi,
  admin: adminApi,
  action: actionApi,
  agent: mockAgent,
}

export type ApplicationApi = typeof api
export type ApiMode = 'mock' | 'http'

export const apiMode: ApiMode = 'mock'
