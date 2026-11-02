import { ArrowRight, BookOpenText, Headphones, Play } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge, ProgressBar } from '../../components/ui'
import type { LearningTask } from '../../types/domain'
import {
  formatShortDate,
  practicePath,
  taskModeLabel,
  taskStatusLabel,
  taskStatusTone,
  taskTypeLabel,
} from '../../utils/format'

export const TaskCard = ({ task }: { task: LearningTask }) => {
  const Icon = task.type === 'vocabulary' ? BookOpenText : Headphones
  return (
    <article className="task-card">
      <div className={`task-type-icon task-type-${task.type}`}>
        <Icon size={18} />
      </div>
      <div className="task-card-main">
        <div className="task-card-titleline">
          <Link to={`/tasks/${task.id}`}>{task.name}</Link>
          <Badge tone={taskStatusTone(task.status)}>{taskStatusLabel(task.status)}</Badge>
        </div>
        <div className="task-card-meta">
          <span>{task.subject === 'english' ? '英语' : '语文'}</span>
          <span>{taskTypeLabel(task.type)}</span>
          <span>{taskModeLabel(task.mode)}</span>
          <span>{task.libraryName}</span>
          <span>更新于 {formatShortDate(task.updatedAt)}</span>
        </div>
        <ProgressBar value={task.progress} compact />
      </div>
      <div className="task-card-progress">
        <strong>{task.progress}%</strong>
        <span>{task.targetCount} 项内容</span>
      </div>
      <div className="task-card-actions">
        {task.status === 'in_progress' ? (
          <Link className="button button-primary button-sm" to={practicePath(task)}>
            <Play size={15} />
            继续学习
          </Link>
        ) : (
          <Link className="button button-secondary button-sm" to={practicePath(task)}>
            <Play size={15} />
            再练一次
          </Link>
        )}
        <Link className="icon-button icon-button-md" aria-label="查看任务详情" to={`/tasks/${task.id}`}>
          <ArrowRight size={16} />
        </Link>
      </div>
    </article>
  )
}
