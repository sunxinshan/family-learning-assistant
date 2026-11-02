import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api'
import { ApiError } from '../api/httpClient'
import type {
  LearningTask,
  PracticeAttempt,
  User,
  Vocabulary,
} from '../types/domain'
import { AppStoreContext, type AppStoreValue, type ToastState } from './AppStoreContext'


export const AppStoreProvider = ({ children }: { children: ReactNode }) => {
  const [currentUser, setCurrentUser] = useState<User | null>(() => api.auth.current())
  const [tasks, setTasks] = useState<LearningTask[]>([])
  const [libraries, setLibraries] = useState<Vocabulary[]>([])
  const [publicLibraries, setPublicLibraries] = useState<Vocabulary[]>([])
  const [practices, setPractices] = useState<PracticeAttempt[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [toast, setToast] = useState<ToastState | null>(null)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      await api.refresh()
      if (!currentUser) {
        setTasks([])
        setLibraries([])
        setPublicLibraries([])
        setPractices([])
        return
      }
      setTasks(api.task.list(currentUser.id))
      setLibraries(api.vocabulary.listMine(currentUser.id))
      setPublicLibraries(api.vocabulary.listPublic(currentUser.id))
      setPractices(api.learning.listAttempts(currentUser.id))
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        api.auth.logout()
        setCurrentUser(null)
        return
      }
      setToast({
        id: Date.now(),
        message: cause instanceof Error ? cause.message : '数据加载失败',
        tone: 'danger',
      })
    } finally {
      setIsLoading(false)
    }
  }, [currentUser])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const handleChange = () => void refresh()
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
    const user = await api.auth.login(nickname, password)
    setCurrentUser(user)
    return user
  }, [])

  const register = useCallback(async (nickname: string, password: string) => {
    const user = await api.auth.register(nickname, password)
    setCurrentUser(user)
    return user
  }, [])

  const logout = useCallback(() => {
    api.auth.logout()
    setCurrentUser(null)
    void refresh()
  }, [refresh])


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
      refresh,
      showToast,
    ],
  )

  return <AppStoreContext.Provider value={value}>{children}</AppStoreContext.Provider>
}
