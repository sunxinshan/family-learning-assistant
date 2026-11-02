import type {
  AgentEvent,
  ChatMessage,
  LearningStats,
  LearningTask,
  OperationLog,
  PendingAction,
  PracticeAttempt,
  TaskDraft,
  User,
  Vocabulary,
  VocabularyDraft,
  WordEntry,
} from '../types/domain'
import { notifyDataChanged } from './storage'
import { authSession, request, requestResponse } from './httpClient'

type AdminUser = User & { practiceCount: number; accuracy: number }

interface AgentRun {
  id: string
  conversationId: string
  status: string
  pendingAction: PendingAction | null
  draftVersion: number
  configHash: string | null
}

interface ContentExtraction {
  id: string
  materialId: string
  extractedJson: VocabularyDraft
  errorsJson: Array<{ row?: number; message?: string }>
  mapping: {
    fields: Record<string, { index: number; header: string }>
    unmappedHeaders: string[]
    source: 'rules' | 'llm'
    confidence: number | null
    reason: string
    usage: Record<string, number>
  }
  mappingSource: 'rules' | 'llm'
  version: number
  status: string
}

let tasksCache: LearningTask[] = []
let librariesCache: Vocabulary[] = []
let publicLibrariesCache: Vocabulary[] = []
let attemptsCache: PracticeAttempt[] = []
let statsCache: LearningStats | null = null
let adminUsersCache: AdminUser[] = []
let adminLogsCache: OperationLog[] = []
const activeAttempts = new Map<string, PracticeAttempt>()

const emptyStats = (): LearningStats => ({
  practiceCount: 0,
  averageAccuracy: 0,
  masteredCount: 0,
  reviewCount: 0,
  vocabularyAccuracy: 0,
  dictationAccuracy: 0,
  recentAttempts: [],
  wrongAnswers: [],
  weeklyActivity: Array.from({ length: 7 }, (_, index) => {
    const date = new Date()
    date.setDate(date.getDate() - (6 - index))
    return { label: `${date.getMonth() + 1}/${date.getDate()}`, count: 0, accuracy: 0 }
  }),
})

const sortUpdated = <T extends { updatedAt: string }>(items: T[]): T[] =>
  [...items].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))

const cacheAttempt = (attempt: PracticeAttempt): PracticeAttempt => {
  const existing = attemptsCache.findIndex((item) => item.id === attempt.id)
  if (existing >= 0) attemptsCache[existing] = attempt
  else attemptsCache = [attempt, ...attemptsCache]
  if (attempt.status === 'in_progress') activeAttempts.set(attempt.taskId, attempt)
  else activeAttempts.delete(attempt.taskId)
  return attempt
}

const findTask = (taskId: string): LearningTask => {
  const task = tasksCache.find((item) => item.id === taskId)
  if (!task) throw new Error('任务不存在或已被删除')
  return task
}

const findLibrary = (libraryId: string): Vocabulary => {
  const library = [...librariesCache, ...publicLibrariesCache].find(
    (item) => item.id === libraryId,
  )
  if (!library) throw new Error('词库不存在或已被删除')
  return library
}

const mapAdminUser = (raw: Record<string, unknown>, actorNames: Map<string, string>): AdminUser => ({
  id: String(raw.id),
  nickname: String(raw.nickname),
  role: raw.role as User['role'],
  status: raw.status as User['status'],
  createdAt: String(raw.created_at),
  lastActiveAt: String(raw.last_active_at ?? raw.created_at),
  ...(actorNames.has(String(raw.id)) ? {} : {}),
  practiceCount: Number(raw.practice_count ?? 0),
  accuracy: Number(raw.accuracy ?? 0),
})

const mapLog = (raw: Record<string, unknown>, actorNames: Map<string, string>): OperationLog => ({
  id: String(raw.id),
  actorId: String(raw.actorUserId),
  actorName: actorNames.get(String(raw.actorUserId)) ?? '未知用户',
  action: String(raw.action),
  target: String(raw.targetName || raw.targetType || ''),
  result: raw.result === 'error' ? 'error' : 'success',
  createdAt: String(raw.createdAt),
})

const refreshAdmin = async (): Promise<void> => {
  const rawUsers = await request<Array<Record<string, unknown>>>('/admin/users')
  const actorNames = new Map(rawUsers.map((item) => [String(item.id), String(item.nickname)]))
  adminUsersCache = rawUsers.map((item) => mapAdminUser(item, actorNames))
  const rawLogs = await request<Array<Record<string, unknown>>>('/admin/logs')
  adminLogsCache = rawLogs
    .map((item) => mapLog(item, actorNames))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
}

const refreshStats = async (): Promise<void> => {
  statsCache = await request<LearningStats>('/learning/stats')
}

const refreshAll = async (): Promise<void> => {
  if (!authSession.current()) {
    tasksCache = []
    librariesCache = []
    publicLibrariesCache = []
    attemptsCache = []
    statsCache = null
    adminUsersCache = []
    adminLogsCache = []
    activeAttempts.clear()
    return
  }
  const [tasks, libraries, publicLibraries, attempts, stats] = await Promise.all([
    request<LearningTask[]>('/tasks'),
    request<Vocabulary[]>('/vocabularies?scope=mine'),
    request<Vocabulary[]>('/vocabularies?scope=public'),
    request<PracticeAttempt[]>('/attempts'),
    request<LearningStats>('/learning/stats'),
  ])
  tasksCache = sortUpdated(tasks)
  librariesCache = sortUpdated(libraries)
  publicLibrariesCache = sortUpdated(publicLibraries)
  attemptsCache = sortUpdated(attempts)
  statsCache = stats
  activeAttempts.clear()
  attempts.forEach((attempt) => {
    if (attempt.status === 'in_progress') activeAttempts.set(attempt.taskId, attempt)
  })
  if (authSession.current()?.role === 'admin') await refreshAdmin()
}

const redactPayloadForRequest = (action: PendingAction): PendingAction => action

const parseSseBlocks = async function* (
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<AgentEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const data = block
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
        if (data) {
          const payload = JSON.parse(data) as { type: AgentEvent['type']; data: unknown }
          yield { type: payload.type, data: payload.data } as AgentEvent
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}

const runAgentStream = async (
  path: string,
  init: RequestInit,
  emit: (event: AgentEvent) => void,
): Promise<void> => {
  const response = await requestResponse(path, init)
  if (!response.body) throw new Error('服务端未返回流式响应')
  for await (const event of parseSseBlocks(response.body)) emit(event)
}

export const httpApi = {
  refresh: refreshAll,
  refreshStats,

  auth: {
    login: (nickname: string, password: string) => authSession.login(nickname, password),
    register: (nickname: string, password: string) => authSession.register(nickname, password),
    current: () => authSession.current(),
    logout: () => authSession.logout(),
  },

  task: {
    list: (_userId: string) => tasksCache,
    get: (taskId: string, _userId: string) => findTask(taskId),
    async refreshOne(taskId: string): Promise<LearningTask> {
      const task = await request<LearningTask>(`/tasks/${taskId}`)
      tasksCache = sortUpdated(tasksCache.map((item) => (item.id === taskId ? task : item)))
      return task
    },
    async create(_userId: string, draft: TaskDraft): Promise<LearningTask> {
      const task = await request<LearningTask>('/tasks', {
        method: 'POST',
        body: JSON.stringify({
          name: draft.name,
          type: draft.type,
          mode: draft.mode,
          libraryId: draft.libraryId,
          selectedEntryIds: draft.selectedEntryIds,
          wordsPerGroup: draft.wordsPerGroup,
          repeatUntilCorrect: draft.repeatUntilCorrect,
          dictation: draft.dictation,
        }),
      })
      tasksCache = sortUpdated([task, ...tasksCache.filter((item) => item.id !== task.id)])
      notifyDataChanged()
      return task
    },
    async update(
      _userId: string,
      taskId: string,
      changes: Partial<Pick<LearningTask, 'name' | 'config' | 'targetCount' | 'mode'>>,
    ): Promise<LearningTask> {
      const task = findTask(taskId)
      const config = changes.config ?? task.config
      const updated = await request<LearningTask>(`/tasks/${taskId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: changes.name ?? task.name,
          wordsPerGroup: config.wordsPerGroup,
          repeatUntilCorrect: config.repeatUntilCorrect,
          dictation: config.dictation,
        }),
      })
      tasksCache = sortUpdated(tasksCache.map((item) => (item.id === taskId ? updated : item)))
      notifyDataChanged()
      return updated
    },
    async remove(_userId: string, taskId: string): Promise<void> {
      await request<void>(`/tasks/${taskId}`, { method: 'DELETE' })
      tasksCache = tasksCache.filter((item) => item.id !== taskId)
      attemptsCache = attemptsCache.filter((item) => item.taskId !== taskId)
      activeAttempts.delete(taskId)
      notifyDataChanged()
    },
  },

  vocabulary: {
    listMine: (_userId: string) => librariesCache,
    listPublic: (_userId: string) => publicLibrariesCache,
    get: (libraryId: string, _userId: string) => findLibrary(libraryId),
    async updateMetadata(
      _userId: string,
      libraryId: string,
      draft: Pick<VocabularyDraft, 'subject' | 'name' | 'description' | 'tags'>,
    ): Promise<Vocabulary> {
      const updated = await request<Vocabulary>(`/vocabularies/${libraryId}`, {
        method: 'PATCH',
        body: JSON.stringify(draft),
      })
      const replace = (items: Vocabulary[]) =>
        sortUpdated(items.map((item) => (item.id === libraryId ? updated : item)))
      librariesCache = replace(librariesCache)
      publicLibrariesCache = replace(publicLibrariesCache)
      notifyDataChanged()
      return updated
    },
    async create(_userId: string, draft: VocabularyDraft): Promise<Vocabulary> {
      const library = await request<Vocabulary>('/vocabularies', {
        method: 'POST',
        body: JSON.stringify({ ...draft, visibility: 'personal' }),
      })
      librariesCache = sortUpdated([library, ...librariesCache])
      notifyDataChanged()
      return library
    },
    async createPublic(_userId: string, draft: VocabularyDraft): Promise<Vocabulary> {
      const library = await request<Vocabulary>('/vocabularies', {
        method: 'POST',
        body: JSON.stringify({ ...draft, visibility: 'public' }),
      })
      publicLibrariesCache = sortUpdated([library, ...publicLibrariesCache])
      notifyDataChanged()
      return library
    },
    async copy(_userId: string, libraryId: string): Promise<Vocabulary> {
      const library = await request<Vocabulary>(`/vocabularies/${libraryId}/copy`, {
        method: 'POST',
      })
      librariesCache = sortUpdated([library, ...librariesCache])
      notifyDataChanged()
      return library
    },
    async insertEntries(
      _userId: string,
      libraryId: string,
      entries: WordEntry[],
    ): Promise<Vocabulary> {
      const library = await request<Vocabulary>(`/vocabularies/${libraryId}/entries`, {
        method: 'POST',
        body: JSON.stringify(entries),
      })
      librariesCache = sortUpdated(
        librariesCache.map((item) => (item.id === libraryId ? library : item)),
      )
      notifyDataChanged()
      return library
    },
    async updateEntry(
      _userId: string,
      libraryId: string,
      entry: WordEntry,
    ): Promise<Vocabulary> {
      const library = await request<Vocabulary>(
        `/vocabularies/${libraryId}/entries/${entry.id}`,
        { method: 'PATCH', body: JSON.stringify(entry) },
      )
      librariesCache = sortUpdated(
        librariesCache.map((item) => (item.id === libraryId ? library : item)),
      )
      notifyDataChanged()
      return library
    },
    async removeEntries(
      _userId: string,
      libraryId: string,
      entryIds: string[],
    ): Promise<Vocabulary> {
      await request<void>(`/vocabularies/${libraryId}/entries/batch-delete`, {
        method: 'POST',
        body: JSON.stringify(entryIds),
      })
      librariesCache = librariesCache.map((item) =>
        item.id === libraryId
          ? { ...item, entries: item.entries.filter((entry) => !entryIds.includes(entry.id)) }
          : item,
      )
      notifyDataChanged()
      return findLibrary(libraryId)
    },
    async removePublic(_userId: string, libraryId: string): Promise<void> {
      await request<void>(`/vocabularies/${libraryId}`, { method: 'DELETE' })
      publicLibrariesCache = publicLibrariesCache.filter((item) => item.id !== libraryId)
      notifyDataChanged()
    },
    async togglePublish(_userId: string, libraryId: string): Promise<Vocabulary> {
      const current = publicLibrariesCache.find((item) => item.id === libraryId)
      const library = await request<Vocabulary>(
        `/vocabularies/${libraryId}/${current?.published ? 'unpublish' : 'publish'}`,
        { method: 'POST' },
      )
      publicLibrariesCache = sortUpdated(
        publicLibrariesCache.map((item) => (item.id === libraryId ? library : item)),
      )
      notifyDataChanged()
      return library
    },
  },

  materials: {
    async upload(file: File): Promise<{ id: string; originalFilename: string }> {
      const form = new FormData()
      form.append('file', file)
      return request<{ id: string; originalFilename: string }>('/materials', {
        method: 'POST',
        body: form,
      })
    },
    async downloadTemplate(): Promise<Blob> {
      const response = await requestResponse('/vocabularies/import-template')
      return response.blob()
    },
  },

  content: {
    extract: (materialId: string) =>
      request<ContentExtraction>(`/materials/${materialId}/extractions`, { method: 'POST' }),
    update: (extractionId: string, version: number, extractedJson: VocabularyDraft) =>
      request<ContentExtraction>(`/content/extractions/${extractionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ version, extractedJson }),
      }),
    confirm: (extractionId: string, version: number) =>
      request<Vocabulary>(`/content/extractions/${extractionId}/confirm?version=${version}`, {
        method: 'POST',
      }),
  },

  practice: {
    async startOrResume(taskId: string, _userId: string): Promise<PracticeAttempt> {
      const attempt = await request<PracticeAttempt>(`/tasks/${taskId}/attempts`, {
        method: 'POST',
      })
      return cacheAttempt(attempt)
    },
    async getActive(taskId: string, _userId: string): Promise<PracticeAttempt | undefined> {
      const attempt = await request<PracticeAttempt | null>(`/tasks/${taskId}/attempts/active`)
      return attempt ? cacheAttempt(attempt) : undefined
    },
    async get(attemptId: string): Promise<PracticeAttempt | undefined> {
      const attempt = await request<PracticeAttempt>(`/attempts/${attemptId}`)
      return cacheAttempt(attempt)
    },
    async submitAnswer(
      taskId: string,
      userId: string,
      input: { prompt: string; expected: string; given: string; durationMs: number },
    ): Promise<{ attempt: PracticeAttempt; task: LearningTask; isCorrect: boolean }> {
      const active =
        activeAttempts.get(taskId) ?? (await httpApi.practice.startOrResume(taskId, userId))
      const attempt = await request<PracticeAttempt>(`/attempts/${active.id}/answers`, {
        method: 'POST',
        body: JSON.stringify({ given: input.given, durationMs: input.durationMs }),
      })
      const cached = cacheAttempt(attempt)
      await httpApi.task.refreshOne(taskId)
      await refreshStats()
      notifyDataChanged()
      const answer = attempt.answers.at(-1)
      return {
        attempt: cached,
        task: findTask(taskId),
        isCorrect: answer?.correct ?? false,
      }
    },
    async submitOfflineAttempt(
      taskId: string,
      userId: string,
      wrongEntryIds: string[],
    ): Promise<{ attempt: PracticeAttempt; task: LearningTask }> {
      const active =
        activeAttempts.get(taskId) ?? (await httpApi.practice.startOrResume(taskId, userId))
      const attempt = await request<PracticeAttempt>(`/attempts/${active.id}/self-check`, {
        method: 'POST',
        body: JSON.stringify({ wrongEntryIds }),
      })
      const cached = cacheAttempt(attempt)
      await httpApi.task.refreshOne(taskId)
      await refreshStats()
      notifyDataChanged()
      return { attempt: cached, task: findTask(taskId) }
    },
    saveExit: (_attemptId: string) => undefined,
  },

  learning: {
    getStats: (_userId: string): LearningStats => statsCache ?? emptyStats(),
    listAttempts: (_userId: string) => attemptsCache,
  },

  conversation: {
    async get(_userId: string): Promise<{ id: string; messages: ChatMessage[] }> {
      return request('/conversations/current')
    },
    save: (_userId: string, _messages: ChatMessage[]) => undefined,
    async clear(_userId: string): Promise<void> {
      await request<void>('/conversations/current/messages', { method: 'DELETE' })
      notifyDataChanged()
    },
  },

  admin: {
    listUsers: (_adminId: string): AdminUser[] => adminUsersCache,
    listLogs: (_adminId: string): OperationLog[] => adminLogsCache,
    async getUserStats(_adminId: string, userId: string): Promise<LearningStats> {
      return request(`/admin/users/${userId}/learning-stats`)
    },
    async resetPassword(_adminId: string, userId: string): Promise<string> {
      const result = await request<{ temporaryPassword: string }>(
        `/admin/users/${userId}/reset-password`,
        { method: 'POST' },
      )
      notifyDataChanged()
      return result.temporaryPassword
    },
    async updateStatus(_adminId: string, userId: string, status: User['status']): Promise<void> {
      await request(`/admin/users/${userId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      })
      notifyDataChanged()
    },
  },

  agent: {
    getActive: () => request<AgentRun | null>('/agent/runs/active'),
    async run(
      input: {
        text: string
        materialId?: string
        fileName?: string
        fileSize?: number
        fileType?: string
      },
      _userId: string,
      emit: (event: AgentEvent) => void,
    ): Promise<void> {
      await runAgentStream(
        '/agent/runs/stream',
        {
          method: 'POST',
          body: JSON.stringify({ message: input.text, materialId: input.materialId }),
        },
        emit,
      )
    },
    async confirm(
      action: PendingAction,
      _userId: string,
      emit: (event: AgentEvent) => void,
    ): Promise<void> {
      if (!action.id) throw new Error('确认操作缺少 action_id')
      const updated = await request<PendingAction & { draftVersion: number; configHash: string }>(
        `/agent/actions/${action.id}/draft`,
        {
          method: 'PATCH',
          body: JSON.stringify({ action: redactPayloadForRequest(action) }),
        },
      )
      await runAgentStream(
        `/agent/actions/${action.id}/confirm`,
        {
          method: 'POST',
          body: JSON.stringify({
            draftVersion: updated.draftVersion,
            configHash: updated.configHash,
          }),
        },
        emit,
      )
    },
    async cancel(action: PendingAction, _userId: string): Promise<void> {
      await request<void>(`/agent/actions/${action.id}/cancel`, { method: 'POST' })
    },
  },
}
