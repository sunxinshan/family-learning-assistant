import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { learningApi, taskApi, vocabularyApi } from '../api/mockApi'
import { initializeStorage, resetStorage } from '../api/storage'
import { authApi } from '../api/mockApi'
import type {
  LearningTask,
  PracticeAttempt,
  User,
  Vocabulary,
} from '../types/domain'

initializeStorage()

interface ToastState {
  id: number
  message: string
  tone: 'default' | 'success' | 'danger'
}

interface AppStoreValue {
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

const AppStoreContext = createContext<AppStoreValue | null>(null)

export const AppStoreProvider = ({ children }: { children: ReactNode }) => {
  const [currentUser, setCurrentUser] = useState<User | null>(() => authApi.current())
  const [tasks, setTasks] = useState<LearningTask[]>([])
  const [libraries, setLibraries] = useState<Vocabulary[]>([])
  const [publicLibraries, setPublicLibraries] = useState<Vocabulary[]>([])
  const [practices, setPractices] = useState<PracticeAttempt[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [toast, setToast] = useState<ToastState | null>(null)

  const refresh = useCallback(() => {
    if (!currentUser) {
      setTasks([])
      setLibraries([])
      setPublicLibraries([])
      setPractices([])
      setIsLoading(false)
      return
    }
    setTasks(taskApi.list(currentUser.id))
    setLibraries(vocabularyApi.listMine(currentUser.id))
    setPublicLibraries(vocabularyApi.listPublic(currentUser.id))
    setPractices(learningApi.listAttempts(currentUser.id))
    setIsLoading(false)
  }, [currentUser])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const handleChange = () => refresh()
    window.addEventListener('fla:data-changed', handleChange)
    return () => window.removeEventListener('fla:data-changed', handleChange)
  }, [refresh])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 2800)
    return () => window.clearTimeout(timer)
  }, [toast])

  const showToast = useCallback((message: string, tone: ToastState['tone'] = 'default') => {
    setToast({ id: Date.now(), message, tone })
  }, [])

  const login = useCallback(async (nickname: string, password: string) => {
    const user = await authApi.login(nickname, password)
    setCurrentUser(user)
    return user
  }, [])

  const register = useCallback(async (nickname: string, password: string) => {
    const user = await authApi.register(nickname, password)
    setCurrentUser(user)
    return user
  }, [])

  const logout = useCallback(() => {
    authApi.logout()
    setCurrentUser(null)
  }, [])

  const resetDemo = useCallback(() => {
    resetStorage()
    setCurrentUser(null)
  }, [])

  const value = useMemo<AppStoreValue>(
    () => ({
      currentUser,
      tasks,
      libraries,
      publicLibraries,
      practices,
      isLoading,
      toast,
      login,
      register,
      logout,
      resetDemo,
      refresh,
      showToast,
    }),
    [
      currentUser,
      tasks,
      libraries,
      publicLibraries,
      practices,
      isLoading,
      toast,
      login,
      register,
      logout,
      resetDemo,
      refresh,
      showToast,
    ],
  )

  return <AppStoreContext.Provider value={value}>{children}</AppStoreContext.Provider>
}

export const useAppStore = (): AppStoreValue => {
  const context = useContext(AppStoreContext)
  if (!context) {
    throw new Error('useAppStore must be used inside AppStoreProvider')
  }
  return context
}

