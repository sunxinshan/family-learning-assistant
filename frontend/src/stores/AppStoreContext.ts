import { createContext, useContext } from 'react'
import type {
  LearningTask,
  PracticeAttempt,
  User,
  Vocabulary,
} from '../types/domain'

export interface ToastState {
  id: number
  message: string
  tone: 'default' | 'success' | 'danger'
}

export interface AppStoreValue {
  currentUser: User | null
  tasks: LearningTask[]
  libraries: Vocabulary[]
  publicLibraries: Vocabulary[]
  practices: PracticeAttempt[]
  isLoading: boolean
  toast: ToastState | null
  login: (nickname: string, password: string) => Promise<User>
  register: (nickname: string, password: string) => Promise<User>
  logout: () => void
  resetDemo: () => void
  refresh: () => void
  showToast: (message: string, tone?: ToastState['tone']) => void
}

export const AppStoreContext = createContext<AppStoreValue | null>(null)

export const useAppStore = (): AppStoreValue => {
  const context = useContext(AppStoreContext)
  if (!context) {
    throw new Error('useAppStore must be used inside AppStoreProvider')
  }
  return context
}
