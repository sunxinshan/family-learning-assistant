import type {
  AnswerRecord,
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
import { notifyDataChanged, storage } from './storage'

const pause = (ms = 180) => new Promise((resolve) => window.setTimeout(resolve, ms))
const uid = (prefix: string) => `${prefix}-${crypto.randomUUID()}`
const now = () => new Date().toISOString()

const requireUser = (userId: string): User => {
  const user = storage.getUsers().find((candidate) => candidate.id === userId)
  if (!user || user.status !== 'active') {
    throw new Error('当前账户不可用，请重新登录')
  }
  return user
}

const requireOwner = (userId: string): User => {
  const user = requireUser(userId)
  if (user.role !== 'admin') {
    throw new Error('仅管理员可以执行此操作')
  }
  return user
}

const appendLog = (
  actor: User,
  action: string,
  target: string,
  result: OperationLog['result'] = 'success',
): void => {
  const log: OperationLog = {
    id: uid('log'),
    actorId: actor.id,
    actorName: actor.nickname,
    action,
    target,
    result,
    createdAt: now(),
  }
  storage.setLogs([log, ...storage.getLogs()].slice(0, 100))
}

const assertActionNotExecuted = (actionId: string): void => {
  if (storage.getExecutedActions().includes(actionId)) {
    throw new Error('该操作已经执行，请刷新后查看结果')
  }
}

const markActionExecuted = (actionId: string): void => {
  const executed = storage.getExecutedActions()
  if (!executed.includes(actionId)) {
    storage.setExecutedActions([...executed, actionId])
  }
}

const findTaskForUser = (taskId: string, userId: string): LearningTask => {
  const task = storage.getTasks().find((candidate) => candidate.id === taskId)
  if (!task) {
    throw new Error('任务不存在或已被删除')
  }
  if (task.userId !== userId) {
    throw new Error('你无权访问该任务')
  }
  return task
}

const taskProgressFromAttempt = (attempt: PracticeAttempt, task: LearningTask): number => {
  const correctUnique = new Set(
    attempt.answers.filter((answer) => answer.correct).map((answer) => answer.prompt),
  ).size
  const calculated = Math.round((correctUnique / Math.max(task.targetCount, 1)) * 100)
  return Math.min(100, Math.max(task.progress, calculated))
}

export const authApi = {
  async login(nickname: string, password: string): Promise<User> {
    await pause()
    const user = storage
      .getUsers()
      .find((candidate) => candidate.nickname === nickname.trim() && candidate.demoPassword === password)
    if (!user) {
      throw new Error('昵称或密码不正确')
    }
    if (user.status !== 'active') {
      throw new Error('该账户已停用')
    }
    const users = storage.getUsers().map((candidate) =>
      candidate.id === user.id ? { ...candidate, lastActiveAt: now() } : candidate,
    )
    storage.setUsers(users)
    storage.setAuthUserId(user.id)
    notifyDataChanged()
    return users.find((candidate) => candidate.id === user.id)!
  },

  async register(nickname: string, password: string): Promise<User> {
    await pause()
    const cleanNickname = nickname.trim()
    if (cleanNickname.length < 2) {
      throw new Error('昵称至少需要 2 个字符')
    }
    if (password.length < 6) {
      throw new Error('密码至少需要 6 个字符')
    }
    const users = storage.getUsers()
    if (users.some((candidate) => candidate.nickname === cleanNickname)) {
      throw new Error('该昵称已被使用')
    }
    const user: User = {
      id: uid('user'),
      nickname: cleanNickname,
      role: 'user',
      status: 'active',
      createdAt: now(),
      lastActiveAt: now(),
      demoPassword: password,
    }
    storage.setUsers([...users, user])
    storage.setAuthUserId(user.id)
    appendLog(user, '注册账户', cleanNickname)
    notifyDataChanged()
    return user
  },

  current(): User | null {
    const userId = storage.getAuthUserId()
    if (!userId) return null
    return storage.getUsers().find((user) => user.id === userId) ?? null
  },

  logout(): void {
    storage.setAuthUserId(null)
    notifyDataChanged()
  },
}

export const taskApi = {
  list(userId: string): LearningTask[] {
    requireUser(userId)
    return storage
      .getTasks()
      .filter((task) => task.userId === userId)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  },

  get(taskId: string, userId: string): LearningTask {
    return findTaskForUser(taskId, userId)
  },

  async create(userId: string, draft: TaskDraft): Promise<LearningTask> {
    await pause()
    const user = requireUser(userId)
    const library = storage
      .getVocabularies()
      .find((candidate) => candidate.id === draft.libraryId)
    if (!library) {
      throw new Error('所选词库不存在')
    }
    const canAccess = library.ownerId === userId || (library.visibility === 'public' && library.published)
    if (!canAccess) {
      throw new Error('你无权使用该词库创建任务')
    }
    if (library.entries.length === 0) {
      throw new Error('词库中没有可供学习的词条')
    }
    const targetCount = Math.min(draft.targetCount, library.entries.length)
    const task: LearningTask = {
      id: uid('task'),
      userId,
      name: draft.name.trim() || '未命名学习任务',
      type: draft.type,
      mode: draft.mode,
      status: 'in_progress',
      progress: 0,
      targetCount,
      libraryId: library.id,
      libraryName: library.name,
      config: {
        questionCount: targetCount,
        wordsPerGroup: Math.min(draft.wordsPerGroup, targetCount),
        totalGroups: Math.ceil(targetCount / Math.max(draft.wordsPerGroup, 1)),
        repeatUntilCorrect: draft.repeatUntilCorrect,
      },
      snapshot: structuredClone(library.entries).slice(0, targetCount),
      createdAt: now(),
      updatedAt: now(),
    }
    storage.setTasks([task, ...storage.getTasks()])
    appendLog(user, '创建学习任务', task.name)
    notifyDataChanged()
    return task
  },

  async update(
    userId: string,
    taskId: string,
    changes: Partial<Pick<LearningTask, 'name' | 'config' | 'targetCount' | 'mode'>>,
  ): Promise<LearningTask> {
    await pause()
    const user = requireUser(userId)
    const task = findTaskForUser(taskId, userId)
    if (task.mode === 'fixed' && (changes.targetCount || changes.config || changes.mode)) {
      throw new Error('固定任务创建后不能修改学习内容，请删除后重新创建')
    }
    if (changes.targetCount) {
      if (changes.targetCount > task.snapshot.length) {
        throw new Error('学习数量不能超过任务内容快照')
      }
      const wordsPerGroup = Math.min(
        changes.config?.wordsPerGroup ?? task.config.wordsPerGroup,
        changes.targetCount,
      )
      changes.config = {
        ...task.config,
        ...changes.config,
        questionCount: changes.targetCount,
        wordsPerGroup,
        totalGroups: Math.ceil(changes.targetCount / wordsPerGroup),
      }
    }
    const updated = { ...task, ...changes, updatedAt: now() }
    storage.setTasks(storage.getTasks().map((candidate) => (candidate.id === task.id ? updated : candidate)))
    appendLog(user, '修改学习任务', updated.name)
    notifyDataChanged()
    return updated
  },

  async remove(userId: string, taskId: string): Promise<void> {
    await pause()
    const user = requireUser(userId)
    const task = findTaskForUser(taskId, userId)
    storage.setTasks(storage.getTasks().filter((candidate) => candidate.id !== taskId))
    storage.setPractices(storage.getPractices().filter((attempt) => attempt.taskId !== taskId))
    appendLog(user, '删除学习任务', task.name)
    notifyDataChanged()
  },
}

export const vocabularyApi = {
  listMine(userId: string): Vocabulary[] {
    requireUser(userId)
    return storage
      .getVocabularies()
      .filter((library) => library.ownerId === userId)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  },

  listPublic(userId: string): Vocabulary[] {
    const user = requireUser(userId)
    return storage
      .getVocabularies()
      .filter(
        (library) =>
          library.visibility === 'public' &&
          (user.role === 'admin' || library.published),
      )
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  },

  get(libraryId: string, userId: string): Vocabulary {
    const user = requireUser(userId)
    const library = storage.getVocabularies().find((candidate) => candidate.id === libraryId)
    if (!library) {
      throw new Error('词库不存在')
    }
    const canAccess =
      library.ownerId === userId ||
      user.role === 'admin' ||
      (library.visibility === 'public' && library.published)
    if (!canAccess) {
      throw new Error('你无权访问该词库')
    }
    return library
  },

  async updateMetadata(
    userId: string,
    libraryId: string,
    changes: Pick<Vocabulary, 'name' | 'description' | 'category' | 'tags'>,
  ): Promise<Vocabulary> {
    await pause()
    const user = requireUser(userId)
    const library = vocabularyApi.get(libraryId, userId)
    if (library.ownerId !== userId && !(user.role === 'admin' && library.visibility === 'public')) {
      throw new Error('你只能编辑自己的词库信息')
    }
    const name = changes.name.trim()
    if (!name) throw new Error('词库名称不能为空')
    const updated: Vocabulary = {
      ...library,
      name,
      description: changes.description.trim(),
      category: changes.category.trim() || '未分类',
      tags: [...new Set(changes.tags.map((tag) => tag.trim()).filter(Boolean))],
      updatedAt: now(),
    }
    storage.setVocabularies(
      storage.getVocabularies().map((candidate) =>
        candidate.id === library.id ? updated : candidate,
      ),
    )
    appendLog(user, '编辑词库信息', `${library.name} → ${updated.name}`)
    notifyDataChanged()
    return updated
  },

  async create(userId: string, draft: VocabularyDraft): Promise<Vocabulary> {
    await pause()
    const user = requireUser(userId)
    assertUniqueWords(draft.entries)
    const library: Vocabulary = {
      id: uid('lib'),
      ownerId: userId,
      name: draft.name.trim(),
      description: draft.description.trim(),
      category: draft.category.trim() || '未分类',
      tags: draft.tags,
      visibility: 'personal',
      published: false,
      entries: draft.entries,
      createdAt: now(),
      updatedAt: now(),
    }
    if (!library.name) throw new Error('词库名称不能为空')
    storage.setVocabularies([library, ...storage.getVocabularies()])
    appendLog(user, '创建个人词库', library.name)
    notifyDataChanged()
    return library
  },

  async copy(userId: string, libraryId: string): Promise<Vocabulary> {
    await pause()
    const user = requireUser(userId)
    const source = vocabularyApi.get(libraryId, userId)
    if (source.visibility !== 'public' || !source.published) {
      throw new Error('只能复制已发布的公共词库')
    }
    const copy: Vocabulary = {
      ...structuredClone(source),
      id: uid('lib'),
      ownerId: userId,
      name: `${source.name} · 我的副本`,
      visibility: 'personal',
      published: false,
      entries: source.entries.map((word) => ({ ...word, id: uid('word') })),
      createdAt: now(),
      updatedAt: now(),
    }
    storage.setVocabularies([copy, ...storage.getVocabularies()])
    appendLog(user, '复制公共词库', source.name)
    notifyDataChanged()
    return copy
  },

  async insertEntries(
    userId: string,
    libraryId: string,
    entries: WordEntry[],
  ): Promise<Vocabulary> {
    await pause()
    const user = requireUser(userId)
    const library = vocabularyApi.get(libraryId, userId)
    if (library.ownerId !== userId && !(user.role === 'admin' && library.visibility === 'public')) {
      throw new Error('你只能编辑自己的词库')
    }
    const normalized = entries.map((word) => ({ ...word, id: word.id || uid('word') }))
    const existingWords = new Set(library.entries.map((word) => word.word.toLowerCase()))
    const unique = normalized.filter((word) => !existingWords.has(word.word.toLowerCase()))
    const updated = {
      ...library,
      entries: [...library.entries, ...unique],
      updatedAt: now(),
    }
    storage.setVocabularies(
      storage.getVocabularies().map((candidate) =>
        candidate.id === library.id ? updated : candidate,
      ),
    )
    appendLog(user, '添加词条', library.name)
    notifyDataChanged()
    return updated
  },

  async updateEntry(
    userId: string,
    libraryId: string,
    entry: WordEntry,
  ): Promise<Vocabulary> {
    await pause()
    const user = requireUser(userId)
    const library = vocabularyApi.get(libraryId, userId)
    if (library.ownerId !== userId && !(user.role === 'admin' && library.visibility === 'public')) {
      throw new Error('你只能编辑自己的词库')
    }
    if (
      library.entries.some(
        (word) => word.id !== entry.id && word.word.toLowerCase() === entry.word.toLowerCase(),
      )
    ) {
      throw new Error('同一词库中不能出现重复词条')
    }
    const updated = {
      ...library,
      entries: library.entries.map((word) => (word.id === entry.id ? entry : word)),
      updatedAt: now(),
    }
    storage.setVocabularies(
      storage.getVocabularies().map((candidate) =>
        candidate.id === library.id ? updated : candidate,
      ),
    )
    appendLog(user, '编辑词条', `${library.name} / ${entry.word}`)
    notifyDataChanged()
    return updated
  },

  async removeEntries(
    userId: string,
    libraryId: string,
    entryIds: string[],
  ): Promise<Vocabulary> {
    await pause()
    const user = requireUser(userId)
    const library = vocabularyApi.get(libraryId, userId)
    if (library.ownerId !== userId && !(user.role === 'admin' && library.visibility === 'public')) {
      throw new Error('你只能编辑自己的词库')
    }
    const updated = {
      ...library,
      entries: library.entries.filter((word) => !entryIds.includes(word.id)),
      updatedAt: now(),
    }
    storage.setVocabularies(
      storage.getVocabularies().map((candidate) =>
        candidate.id === library.id ? updated : candidate,
      ),
    )
    appendLog(user, '删除词条', `${library.name} / ${entryIds.length} 项`)
    notifyDataChanged()
    return updated
  },

  async createPublic(userId: string, draft: VocabularyDraft): Promise<Vocabulary> {
    await pause()
    const user = requireOwner(userId)
    const library: Vocabulary = {
      id: uid('lib'),
      ownerId: null,
      name: draft.name.trim(),
      description: draft.description.trim(),
      category: draft.category.trim() || '未分类',
      tags: draft.tags,
      visibility: 'public',
      published: false,
      entries: draft.entries,
      createdAt: now(),
      updatedAt: now(),
    }
    if (!library.name) throw new Error('词库名称不能为空')
    storage.setVocabularies([library, ...storage.getVocabularies()])
    appendLog(user, '创建公共词库草稿', library.name)
    notifyDataChanged()
    return library
  },

  async removePublic(userId: string, libraryId: string): Promise<void> {
    await pause()
    const user = requireOwner(userId)
    const library = vocabularyApi.get(libraryId, userId)
    if (library.visibility !== 'public') throw new Error('该资源不是公共词库')
    storage.setVocabularies(
      storage.getVocabularies().filter((candidate) => candidate.id !== libraryId),
    )
    appendLog(user, '删除公共词库', library.name)
    notifyDataChanged()
  },

  async togglePublish(userId: string, libraryId: string): Promise<Vocabulary> {
    await pause()
    const user = requireOwner(userId)
    const library = vocabularyApi.get(libraryId, userId)
    if (library.visibility !== 'public') throw new Error('该资源不是公共词库')
    const updated = { ...library, published: !library.published, updatedAt: now() }
    storage.setVocabularies(
      storage.getVocabularies().map((candidate) =>
        candidate.id === library.id ? updated : candidate,
      ),
    )
    appendLog(user, updated.published ? '发布公共词库' : '撤回公共词库', updated.name)
    notifyDataChanged()
    return updated
  },
}

const assertUniqueWords = (entries: WordEntry[]): void => {
  const words = entries.map((entry) => entry.word.trim().toLowerCase())
  if (new Set(words).size !== words.length) {
    throw new Error('词库中不能包含重复词条')
  }
}

export const practiceApi = {
  startOrResume(taskId: string, userId: string): PracticeAttempt {
    requireUser(userId)
    const task = findTaskForUser(taskId, userId)
    const existing = storage
      .getPractices()
      .find(
        (attempt) =>
          attempt.taskId === taskId &&
          attempt.userId === userId &&
          attempt.status === 'in_progress',
      )
    if (existing) return existing
    const total = Math.min(task.config.questionCount, task.snapshot.length)
    const attempt: PracticeAttempt = {
      id: uid('attempt'),
      taskId,
      userId,
      taskType: task.type,
      status: 'in_progress',
      currentIndex: 0,
      answers: [],
      startedAt: now(),
      updatedAt: now(),
      score: 0,
      total,
    }
    storage.setPractices([attempt, ...storage.getPractices()])
    notifyDataChanged()
    return attempt
  },

  getActive(taskId: string, userId: string): PracticeAttempt | undefined {
    return storage
      .getPractices()
      .find(
        (attempt) =>
          attempt.taskId === taskId &&
          attempt.userId === userId &&
          attempt.status === 'in_progress',
      )
  },

  get(attemptId: string): PracticeAttempt | undefined {
    return storage.getPractices().find((attempt) => attempt.id === attemptId)
  },

  async submitAnswer(
    taskId: string,
    userId: string,
    input: { prompt: string; expected: string; given: string; durationMs: number },
  ): Promise<{ attempt: PracticeAttempt; task: LearningTask; isCorrect: boolean }> {
    await pause(240)
    const user = requireUser(userId)
    const task = findTaskForUser(taskId, userId)
    const attempt = practiceApi.getActive(taskId, userId)
    if (!attempt) throw new Error('没有可继续的练习')
    if (attempt.currentIndex >= attempt.total) throw new Error('本次练习已经完成')
    const isCorrect =
      input.given.trim().toLowerCase() === input.expected.trim().toLowerCase()
    const answer: AnswerRecord = {
      id: uid('answer'),
      questionId: `${attempt.currentIndex + 1}`,
      prompt: input.prompt,
      expected: input.expected,
      given: input.given,
      correct: isCorrect,
      answeredAt: now(),
      durationMs: input.durationMs,
    }
    const answers = [...attempt.answers, answer]
    const isFinished = answers.length >= attempt.total
    const nextAttempt: PracticeAttempt = {
      ...attempt,
      currentIndex: answers.length,
      answers,
      score: answers.filter((item) => item.correct).length,
      status: isFinished ? 'completed' : 'in_progress',
      updatedAt: now(),
      completedAt: isFinished ? now() : undefined,
    }
    let nextTask = task
    if (isFinished) {
      const progress = taskProgressFromAttempt(nextAttempt, task)
      nextTask = {
        ...task,
        progress,
        status: progress >= 100 ? 'completed' : 'in_progress',
        updatedAt: now(),
      }
      storage.setTasks(storage.getTasks().map((candidate) => (candidate.id === task.id ? nextTask : candidate)))
      appendLog(user, '完成练习', task.name)
    }
    storage.setPractices(
      storage.getPractices().map((candidate) =>
        candidate.id === attempt.id ? nextAttempt : candidate,
      ),
    )
    notifyDataChanged()
    return { attempt: nextAttempt, task: nextTask, isCorrect }
  },

  saveExit(attemptId: string): void {
    const attempt = storage.getPractices().find((candidate) => candidate.id === attemptId)
    if (!attempt) return
    storage.setPractices(
      storage.getPractices().map((candidate) =>
        candidate.id === attemptId ? { ...candidate, updatedAt: now() } : candidate,
      ),
    )
    notifyDataChanged()
  },
}

const startOfDay = (date: Date): number =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()

const buildLearningStats = (userId: string): LearningStats => {
  requireUser(userId)
  const attempts = storage
    .getPractices()
    .filter((attempt) => attempt.userId === userId && attempt.status === 'completed')
    .sort((a, b) => (b.completedAt ?? b.updatedAt).localeCompare(a.completedAt ?? a.updatedAt))
  const totalAnswered = attempts.reduce((sum, attempt) => sum + attempt.answers.length, 0)
  const totalCorrect = attempts.reduce((sum, attempt) => sum + attempt.score, 0)
  const vocabularyAttempts = attempts.filter((attempt) => attempt.taskType === 'vocabulary')
  const dictationAttempts = attempts.filter((attempt) => attempt.taskType === 'dictation')
  const accuracyFor = (items: PracticeAttempt[]) => {
    const total = items.reduce((sum, attempt) => sum + attempt.answers.length, 0)
    const correct = items.reduce((sum, attempt) => sum + attempt.score, 0)
    return total ? Math.round((correct / total) * 100) : 0
  }
  const latestAnswerByWord = new Map<string, AnswerRecord>()
  attempts.forEach((attempt) => {
    attempt.answers.forEach((answer) => {
      if (!latestAnswerByWord.has(answer.prompt)) {
        latestAnswerByWord.set(answer.prompt, answer)
      }
    })
  })
  const masteredCount = [...latestAnswerByWord.values()].filter((answer) => answer.correct).length
  const wrongAnswers = [...latestAnswerByWord.values()]
    .filter((answer) => !answer.correct)
    .sort((a, b) => b.answeredAt.localeCompare(a.answeredAt))
    .slice(0, 8)
  const today = new Date('2026-11-02T12:00:00+08:00')
  const weeklyActivity = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (6 - index))
    const dayStart = startOfDay(date)
    const dayEnd = dayStart + 24 * 60 * 60 * 1000
    const dayAttempts = attempts.filter((attempt) => {
      const completed = new Date(attempt.completedAt ?? attempt.updatedAt).getTime()
      return completed >= dayStart && completed < dayEnd
    })
    const correct = dayAttempts.reduce((sum, attempt) => sum + attempt.score, 0)
    const answered = dayAttempts.reduce((sum, attempt) => sum + attempt.answers.length, 0)
    return {
      label: `${date.getMonth() + 1}/${date.getDate()}`,
      count: dayAttempts.length,
      accuracy: answered ? Math.round((correct / answered) * 100) : 0,
    }
  })
  return {
    practiceCount: attempts.length,
    averageAccuracy: totalAnswered ? Math.round((totalCorrect / totalAnswered) * 100) : 0,
    masteredCount,
    reviewCount: wrongAnswers.length,
    vocabularyAccuracy: accuracyFor(vocabularyAttempts),
    dictationAccuracy: accuracyFor(dictationAttempts),
    recentAttempts: attempts.slice(0, 8),
    wrongAnswers,
    weeklyActivity,
  }
}

export const learningApi = {
  getStats(userId: string): LearningStats {
    return buildLearningStats(userId)
  },

  listAttempts(userId: string): PracticeAttempt[] {
    requireUser(userId)
    return storage
      .getPractices()
      .filter((attempt) => attempt.userId === userId)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  },
}

export const conversationApi = {
  get(userId: string) {
    requireUser(userId)
    const conversations = storage.getConversations()
    const existing = conversations.find((conversation) => conversation.userId === userId)
    if (existing) return existing
    const conversation = {
      id: uid('conversation'),
      userId,
      title: '学习助手',
      createdAt: now(),
      updatedAt: now(),
      messages: [],
    }
    storage.setConversations([conversation, ...conversations])
    return conversation
  },

  save(userId: string, messages: import('../types/domain').ChatMessage[]) {
    requireUser(userId)
    const conversations = storage.getConversations()
    const existing = conversations.find((conversation) => conversation.userId === userId)
    if (!existing) return
    const updated = { ...existing, messages, updatedAt: now() }
    storage.setConversations(
      conversations.map((conversation) =>
        conversation.id === existing.id ? updated : conversation,
      ),
    )
    notifyDataChanged()
  },

  clear(userId: string) {
    requireUser(userId)
    conversationApi.save(userId, [])
  },
}

export const adminApi = {
  listUsers(adminId: string): Array<User & { practiceCount: number; accuracy: number }> {
    requireOwner(adminId)
    const practices = storage.getPractices()
    return storage.getUsers().map((user) => {
      const completed = practices.filter(
        (attempt) => attempt.userId === user.id && attempt.status === 'completed',
      )
      const answered = completed.reduce((sum, attempt) => sum + attempt.answers.length, 0)
      const correct = completed.reduce((sum, attempt) => sum + attempt.score, 0)
      return {
        ...user,
        practiceCount: completed.length,
        accuracy: answered ? Math.round((correct / answered) * 100) : 0,
      }
    })
  },

  async resetPassword(adminId: string, userId: string): Promise<string> {
    await pause()
    const admin = requireOwner(adminId)
    const password = `fla-${Math.random().toString(36).slice(2, 8)}`
    const users = storage.getUsers()
    const target = users.find((user) => user.id === userId)
    if (!target) throw new Error('用户不存在')
    storage.setUsers(
      users.map((user) => (user.id === userId ? { ...user, demoPassword: password } : user)),
    )
    appendLog(admin, '重置用户密码', target.nickname)
    notifyDataChanged()
    return password
  },

  listLogs(adminId: string): OperationLog[] {
    requireOwner(adminId)
    return storage.getLogs().sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  },

  getUserStats(adminId: string, userId: string): LearningStats {
    requireOwner(adminId)
    return buildLearningStats(userId)
  },
}

export const actionApi = {
  isExecuted(actionId: string): boolean {
    return storage.getExecutedActions().includes(actionId)
  },

  async execute(action: PendingAction, userId: string): Promise<{
    message: string
    link?: { label: string; to: string }
  }> {
    assertActionNotExecuted(action.id)
    if (action.operation === 'create_task' && action.payload.taskDraft) {
      const task = await taskApi.create(userId, action.payload.taskDraft)
      markActionExecuted(action.id)
      return {
        message: `任务「${task.name}」已经创建，学习内容快照已保存。`,
        link: { label: '查看任务详情', to: `/tasks/${task.id}` },
      }
    }
    if (action.operation === 'update_task' && action.payload.taskId && action.payload.changes) {
      const task = await taskApi.update(userId, action.payload.taskId, action.payload.changes)
      markActionExecuted(action.id)
      return {
        message: `任务「${task.name}」的配置已经更新。`,
        link: { label: '查看任务详情', to: `/tasks/${task.id}` },
      }
    }
    if (action.operation === 'delete_task' && action.payload.taskId) {
      const task = taskApi.get(action.payload.taskId, userId)
      await taskApi.remove(userId, action.payload.taskId)
      markActionExecuted(action.id)
      return {
        message: `任务「${task.name}」及其历史练习记录已经删除。`,
        link: { label: '返回任务列表', to: '/tasks' },
      }
    }
    if (
      (action.operation === 'create_vocabulary' || action.operation === 'import_vocabulary') &&
      action.payload.vocabularyDraft
    ) {
      const library = await vocabularyApi.create(userId, action.payload.vocabularyDraft)
      markActionExecuted(action.id)
      return {
        message: `词库「${library.name}」已经保存，共 ${library.entries.length} 个词条。`,
        link: { label: '打开词库', to: `/vocabulary/${library.id}` },
      }
    }
    throw new Error('无法识别该操作')
  },
}
