import {
  seedConversations,
  seedOperationLogs,
  seedPractices,
  seedTasks,
  seedUsers,
  seedVocabularies,
} from '../data/mockData'
import type {
  Conversation,
  LearningTask,
  OperationLog,
  PracticeAttempt,
  User,
  Vocabulary,
} from '../types/domain'

export const STORAGE_KEYS = {
  initialized: 'fla.initialized.v1',
  auth: 'fla.auth.v1',
  users: 'fla.users.v1',
  conversations: 'fla.conversations.v1',
  tasks: 'fla.tasks.v1',
  vocabularies: 'fla.vocabularies.v1',
  practices: 'fla.practices.v1',
  logs: 'fla.operation-logs.v1',
  actions: 'fla.executed-actions.v1',
} as const

const read = <T,>(key: string, fallback: T): T => {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

const write = <T,>(key: string, value: T): void => {
  window.localStorage.setItem(key, JSON.stringify(value))
}

const DEMO_USER_NAMES: Record<string, string> = {
  'user-1': 'Alice',
  'user-2': 'Bob',
  'admin-1': 'Admin',
  'admin-2': 'Manager',
}

const migrateLearningData = (): void => {
  const vocabularies = read<Vocabulary[]>(STORAGE_KEYS.vocabularies, [])
  if (vocabularies.length) {
    const normalized = vocabularies.map((library) => ({
      ...library,
      subject:
        library.subject ??
        (library.name.includes('语文') || library.id.includes('-zh-') ? 'chinese' : 'english'),
    }))
    const existingIds = new Set(normalized.map((library) => library.id))
    const missingChineseSeeds = seedVocabularies.filter(
      (library) =>
        library.subject === 'chinese' &&
        ['lib-personal-zh-1', 'lib-public-zh-1'].includes(library.id) &&
        !existingIds.has(library.id),
    )
    write(STORAGE_KEYS.vocabularies, [...normalized, ...missingChineseSeeds])
  }

  const tasks = read<LearningTask[]>(STORAGE_KEYS.tasks, [])
  if (tasks.length) {
    const libraries = read<Vocabulary[]>(STORAGE_KEYS.vocabularies, [])
    const normalized = tasks.map((task) => {
      const library = libraries.find((candidate) => candidate.id === task.libraryId)
      return {
        ...task,
        subject: task.subject ?? library?.subject ?? 'english',
        config:
          task.type === 'dictation'
            ? {
                ...task.config,
                dictation: task.config.dictation ?? {
                  mode: 'online',
                  playbackMode: 'manual',
                  intervalSeconds: 5,
                  hint: 'phonetic',
                  repeatCount: 1,
                },
              }
            : task.config,
      }
    })
    if (!normalized.some((task) => task.id === 'task-5')) {
      const chineseTask = seedTasks.find((task) => task.id === 'task-5')
      if (chineseTask) normalized.push(chineseTask)
    }
    write(STORAGE_KEYS.tasks, normalized)
  }
}

const migrateDemoUserNames = (): void => {
  const users = read<User[]>(STORAGE_KEYS.users, [])
  if (users.length) {
    const renamed = users.map((user) =>
      DEMO_USER_NAMES[user.id] ? { ...user, nickname: DEMO_USER_NAMES[user.id] } : user,
    )
    const missingDemoAdmins = seedUsers.filter(
      (seedUser) => seedUser.role === 'admin' && !renamed.some((user) => user.id === seedUser.id),
    )
    write(STORAGE_KEYS.users, [...renamed, ...missingDemoAdmins])
  }
  const logs = read<OperationLog[]>(STORAGE_KEYS.logs, [])
  if (logs.length) {
    write(
      STORAGE_KEYS.logs,
      logs.map((log) =>
        DEMO_USER_NAMES[log.actorId]
          ? { ...log, actorName: DEMO_USER_NAMES[log.actorId] }
          : log,
      ),
    )
  }
}

export const initializeStorage = (force = false): void => {
  if (!force && window.localStorage.getItem(STORAGE_KEYS.initialized) === 'true') {
    migrateDemoUserNames()
    migrateLearningData()
    return
  }

  write(STORAGE_KEYS.users, seedUsers)
  write(STORAGE_KEYS.conversations, seedConversations)
  write(STORAGE_KEYS.tasks, seedTasks)
  write(STORAGE_KEYS.vocabularies, seedVocabularies)
  write(STORAGE_KEYS.practices, seedPractices)
  write(STORAGE_KEYS.logs, seedOperationLogs)
  write(STORAGE_KEYS.actions, [])
  if (force) {
    window.localStorage.removeItem(STORAGE_KEYS.auth)
  }
  window.localStorage.setItem(STORAGE_KEYS.initialized, 'true')
}

export const resetStorage = (): void => {
  Object.values(STORAGE_KEYS).forEach((key) => window.localStorage.removeItem(key))
  initializeStorage(true)
  window.dispatchEvent(new CustomEvent('fla:data-changed'))
}

export const storage = {
  getUsers: () => read<User[]>(STORAGE_KEYS.users, seedUsers),
  setUsers: (users: User[]) => write(STORAGE_KEYS.users, users),
  getConversations: () => read<Conversation[]>(STORAGE_KEYS.conversations, seedConversations),
  setConversations: (conversations: Conversation[]) => write(STORAGE_KEYS.conversations, conversations),
  getTasks: () => read<LearningTask[]>(STORAGE_KEYS.tasks, seedTasks),
  setTasks: (tasks: LearningTask[]) => write(STORAGE_KEYS.tasks, tasks),
  getVocabularies: () => read<Vocabulary[]>(STORAGE_KEYS.vocabularies, seedVocabularies),
  setVocabularies: (vocabularies: Vocabulary[]) => write(STORAGE_KEYS.vocabularies, vocabularies),
  getPractices: () => read<PracticeAttempt[]>(STORAGE_KEYS.practices, seedPractices),
  setPractices: (practices: PracticeAttempt[]) => write(STORAGE_KEYS.practices, practices),
  getLogs: () => read<OperationLog[]>(STORAGE_KEYS.logs, seedOperationLogs),
  setLogs: (logs: OperationLog[]) => write(STORAGE_KEYS.logs, logs),
  getExecutedActions: () => read<string[]>(STORAGE_KEYS.actions, []),
  setExecutedActions: (actions: string[]) => write(STORAGE_KEYS.actions, actions),
  getAuthUserId: () => read<string | null>(STORAGE_KEYS.auth, null),
  setAuthUserId: (userId: string | null) => write(STORAGE_KEYS.auth, userId),
}

export const notifyDataChanged = (): void => {
  window.dispatchEvent(new CustomEvent('fla:data-changed'))
}
