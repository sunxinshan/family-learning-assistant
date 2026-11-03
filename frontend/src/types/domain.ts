export type UserRole = 'user' | 'admin'
export type UserStatus = 'active' | 'disabled'
export type Subject = 'english' | 'chinese'
export type TaskType = 'vocabulary' | 'dictation'
export type DictationMode = 'online' | 'offline'
export type PlaybackMode = 'auto' | 'manual'
export type DictationHint = 'phonetic' | 'meaning'
export type TaskMode = 'fixed' | 'long_term'
export type TaskStatus = 'in_progress' | 'completed'
export type PracticeStatus = 'in_progress' | 'completed'
export type PracticeKind = 'regular' | 'wrong'
export type LibraryVisibility = 'personal' | 'public'

export interface User {
  id: string
  nickname: string
  role: UserRole
  status: UserStatus
  createdAt: string
  lastActiveAt: string
  demoPassword?: string
}

export interface WordEntry {
  id: string
  word: string
  phonetic: string
  partOfSpeech: string
  meanings: string[]
  example: string
  exampleTranslation: string
}

export interface Vocabulary {
  id: string
  ownerId: string | null
  subject: Subject
  name: string
  description: string
  category?: string
  tags: string[]
  visibility: LibraryVisibility
  published: boolean
  entryCount?: number
  entries: WordEntry[]
  entriesIncluded?: boolean
  createdAt: string
  updatedAt: string
}

export interface DictationConfig {
  mode: DictationMode
  playbackMode: PlaybackMode
  intervalSeconds: number
  hint: DictationHint
  repeatCount: number
  /** 关闭后练习页不自动朗读，只在答错时提供朗读入口。 */
  speechEnabled?: boolean
}

export interface TaskConfig {
  questionCount: number
  wordsPerGroup: number
  totalGroups: number
  repeatUntilCorrect: boolean
  dictation?: DictationConfig
}

export interface LearningTask {
  id: string
  userId: string
  name: string
  subject: Subject
  type: TaskType
  mode: TaskMode
  status: TaskStatus
  progress: number
  targetCount: number
  libraryId: string
  libraryName: string
  config: TaskConfig
  snapshot: WordEntry[]
  snapshotIncluded?: boolean
  createdAt: string
  updatedAt: string
}

export interface AnswerRecord {
  id: string
  questionId: string
  snapshotEntryId?: string
  prompt: string
  expected: string
  given: string
  correct: boolean
  answeredAt: string
  durationMs: number
  evaluationSource?: 'auto' | 'self_report'
}

export interface PracticeAttempt {
  id: string
  taskId: string
  userId: string
  taskType: TaskType
  kind?: PracticeKind
  targetEntryIds?: string[]
  status: PracticeStatus
  currentIndex: number
  answers: AnswerRecord[]
  startedAt: string
  updatedAt: string
  completedAt?: string
  score: number
  total: number
}

export interface WrongQuestion {
  snapshotEntryId: string
  word: string
  phonetic: string
  meanings: string[]
  example: string
  exampleTranslation: string
  consecutiveCorrect: number
  lastWrongAt: string
  groupIndex: number
}

export interface WrongQuestionGroup {
  groupIndex: number
  entries: WrongQuestion[]
}

export interface WrongQuestions {
  taskId: string
  total: number
  requiredCorrectStreak: number
  groups: WrongQuestionGroup[]
}

export interface LearningStats {
  practiceCount: number
  averageAccuracy: number
  masteredCount: number
  reviewCount: number
  vocabularyAccuracy: number
  dictationAccuracy: number
  recentAttempts: PracticeAttempt[]
  wrongAnswers: AnswerRecord[]
  weeklyActivity: Array<{ label: string; count: number; accuracy: number }>
}

export interface OperationLog {
  id: string
  actorId: string
  actorName: string
  action: string
  target: string
  result: 'success' | 'error'
  createdAt: string
}

export interface TaskDraft {
  name: string
  type: TaskType
  mode: TaskMode
  targetCount: number
  libraryId: string
  selectedEntryIds: string[]
  wordsPerGroup: number
  repeatUntilCorrect: boolean
  dictation?: DictationConfig
}

export interface VocabularyDraft {
  subject: Subject
  name: string
  description: string
  category?: string
  tags: string[]
  entries: WordEntry[]
}

export interface ActionField {
  label: string
  value: string
}

export interface ActionDiff {
  label: string
  before: string
  after: string
}

export type ActionOperation =
  | 'create_task'
  | 'update_task'
  | 'delete_task'
  | 'create_vocabulary'
  | 'import_vocabulary'

export interface PendingActionPayload {
  taskDraft?: TaskDraft
  taskId?: string
  changes?: Partial<Pick<LearningTask, 'name' | 'config' | 'targetCount' | 'mode'>>
  vocabularyDraft?: VocabularyDraft
  fileName?: string
}

export interface PendingAction {
  id: string
  operation: ActionOperation
  title: string
  description: string
  target: string
  fields: ActionField[]
  diff?: ActionDiff[]
  impact: string
  confirmLabel: string
  danger?: boolean
  stage?: 1 | 2
  executed?: boolean
  draftVersion?: number
  configHash?: string
  payload: PendingActionPayload
}

export type ChatMessageKind =
  | 'text'
  | 'file'
  | 'action_preview'
  | 'execution'
  | 'error'
  | 'progress'

export interface MessageLink {
  label: string
  to: string
}

export interface ChatFile {
  name: string
  size: number
  type: string
}

export interface ToolExecution {
  id: string
  tool: string
  label: string
  status: 'running' | 'success' | 'error'
  args: Record<string, unknown>
  result?: string
  error?: string
  durationMs?: number
  startedAt: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  kind: ChatMessageKind
  content: string
  createdAt: string
  file?: ChatFile
  action?: PendingAction
  execution?: ToolExecution
  quickReplies?: string[]
  links?: MessageLink[]
}

export interface Conversation {
  id: string
  userId: string
  title: string
  createdAt: string
  updatedAt: string
  messages: ChatMessage[]
}

export type AgentEvent =
  | { type: 'message'; data: { content: string; quickReplies?: string[]; links?: MessageLink[] } }
  | { type: 'progress'; data: { stage: string; message: string } }
  | { type: 'tool_status'; data: ToolExecution }
  | { type: 'confirmation_required'; data: PendingAction }
  | { type: 'error'; data: { code: string; message: string } }
  | { type: 'done'; data: { executionId: string } }
