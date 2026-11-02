import type { LearningTask, TaskMode, TaskStatus, TaskType } from '../types/domain'

export const formatDateTime = (value: string): string =>
  new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

export const formatDate = (value: string): string =>
  new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value))

export const formatShortDate = (value: string): string =>
  new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
  }).format(new Date(value))

export const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const formatDuration = (milliseconds: number): string => {
  const seconds = Math.round(milliseconds / 1000)
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}

export const taskTypeLabel = (type: TaskType): string =>
  type === 'vocabulary' ? '词汇练习' : '听写练习'

export const taskModeLabel = (mode: TaskMode): string =>
  mode === 'fixed' ? '固定任务' : '长期任务'

export const taskStatusLabel = (status: TaskStatus): string =>
  status === 'completed' ? '已完成' : '进行中'

export const taskStatusTone = (status: TaskStatus): 'success' | 'neutral' =>
  status === 'completed' ? 'success' : 'neutral'

export const practicePath = (task: LearningTask): string =>
  `/practice/${task.type}/${task.id}`

export const truncate = (value: string, length: number): string =>
  value.length > length ? `${value.slice(0, length)}…` : value
