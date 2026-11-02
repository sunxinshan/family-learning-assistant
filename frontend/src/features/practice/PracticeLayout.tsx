import { ArrowLeft, LogOut } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '../../components/ui'
import type { LearningTask } from '../../types/domain'
import { taskTypeLabel } from '../../utils/format'

export const PracticeLayout = ({
  task,
  current,
  total,
  onExit,
  children,
  centered = false,
  contextLabel,
}: {
  task: LearningTask
  current: number
  total: number
  onExit: () => void
  children: ReactNode
  centered?: boolean
  contextLabel?: string
}) => {
  const progress = total > 0 ? Math.round((current / total) * 100) : 0
  return (
    <div className="practice-shell">
      <header className="practice-header">
        <div className="practice-header-left">
          <button type="button" className="back-link" onClick={onExit}>
            <ArrowLeft size={15} />
            保存并退出
          </button>
          <span className="practice-header-divider" />
          <div className="practice-task-name">
            <strong>{task.name}</strong>
            <span>{contextLabel ?? taskTypeLabel(task.type)}</span>
          </div>
        </div>
        <div className="practice-progress">
          <span>
            {Math.min(current + 1, total)} / {total}
          </span>
          <div className="practice-progress-track">
            <div style={{ width: `${progress}%` }} />
          </div>
        </div>
        <Button variant="ghost" size="sm" icon={LogOut} onClick={onExit} className="practice-exit-button">
          退出
        </Button>
      </header>
      <main className={`practice-main ${centered ? 'practice-centered' : ''}`}>
        {children}
      </main>
    </div>
  )
}
