import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api'
import { ApiError, subscribeUnauthorized } from '../api/httpClient'
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
  const [dataVersion, setDataVersion] = useState(0)
  const [toast, setToast] = useState<ToastState | null>(null)
  const refreshVersion = useRef(0)

  const replaceTask = useCallback((task: LearningTask) => {
    setTasks((current) =>
      [task, ...current.filter((item) => item.id !== task.id)].sort((left, right) =>
        right.updatedAt.localeCompare(left.updatedAt),
      ),
    )
  }, [])

  const upsertTask = useCallback(
    (task: LearningTask) => {
      refreshVersion.current += 1
      replaceTask(task)
      setDataVersion((current) => current + 1)
      setIsLoading(false)
    },
    [replaceTask],
  )

  const loadTask = useCallback(
    async (taskId: string) => {
      const task = await api.task.refreshOne(taskId)
      replaceTask(task)
      setDataVersion((current) => current + 1)
      setIsLoading(false)
      return task
    },
    [replaceTask],
  )

  const removeTask = useCallback(
    async (taskId: string) => {
      if (!currentUser) throw new Error('请先登录后再删除任务')
      await api.task.remove(currentUser.id, taskId)
      setTasks((current) => current.filter((item) => item.id !== taskId))
      setPractices((current) => current.filter((item) => item.taskId !== taskId))
      setDataVersion((current) => current + 1)
    },
    [currentUser],
  )

  const replaceLibrary = useCallback((library: Vocabulary) => {
    const replace = (items: Vocabulary[], include: boolean) =>
      include || items.some((item) => item.id === library.id)
        ? [library, ...items.filter((item) => item.id !== library.id)].sort((left, right) =>
            right.updatedAt.localeCompare(left.updatedAt),
          )
        : items
    setLibraries((current) => replace(current, library.visibility !== 'public'))
    setPublicLibraries((current) => replace(current, library.visibility === 'public'))
    setDataVersion((current) => current + 1)
  }, [])

  const upsertLibrary = useCallback(
    (library: Vocabulary) => {
      refreshVersion.current += 1
      replaceLibrary(library)
      setIsLoading(false)
    },
    [replaceLibrary],
  )

  const loadLibrary = useCallback(async (libraryId: string) => {
    const library = await api.vocabulary.refreshOne(libraryId)
    replaceLibrary(library)
    setIsLoading(false)
    return library
  }, [replaceLibrary])

  const loadFullLibraries = useCallback(async () => {
    const result = await api.vocabulary.loadFullLists()
    setLibraries(result.libraries)
    setPublicLibraries(result.publicLibraries)
    setDataVersion((current) => current + 1)
    setIsLoading(false)
  }, [])

  const refresh = useCallback(async () => {
    const version = refreshVersion.current + 1
    refreshVersion.current = version
    setIsLoading(true)
    try {
      await api.refresh((partial) => {
        if (version !== refreshVersion.current) return
        if (partial.tasks) setTasks(partial.tasks)
        if (partial.libraries) setLibraries(partial.libraries)
        if (partial.publicLibraries) setPublicLibraries(partial.publicLibraries)
        if (partial.practices) setPractices(partial.practices)
        setDataVersion((current) => current + 1)
      })
      if (version !== refreshVersion.current) return
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
      setDataVersion((current) => current + 1)
    } catch (cause) {
      if (version !== refreshVersion.current) return
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
      if (version === refreshVersion.current) setIsLoading(false)
    }
  }, [currentUser])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(
    () =>
      subscribeUnauthorized(() => {
        setCurrentUser(null)
        setToast({
          id: Date.now(),
          message: '登录状态已失效，请重新登录',
          tone: 'danger',
        })
      }),
    [],
  )

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
      dataVersion,
      toast,
      login,
      register,
      logout,
      refresh,
      upsertTask,
      loadTask,
      removeTask,
      upsertLibrary,
      loadLibrary,
      loadFullLibraries,
      showToast,
    }),
    [
      currentUser,
      tasks,
      libraries,
      publicLibraries,
      practices,
      isLoading,
      dataVersion,
      toast,
      login,
      register,
      logout,
      refresh,
      upsertTask,
      loadTask,
      removeTask,
      upsertLibrary,
      loadLibrary,
      loadFullLibraries,
      showToast,
    ],
  )

  return <AppStoreContext.Provider value={value}>{children}</AppStoreContext.Provider>
}
