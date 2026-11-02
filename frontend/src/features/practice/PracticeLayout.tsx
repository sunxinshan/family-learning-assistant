import { ArrowLeft, LogOut } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '../../components/ui'
import type { LearningTask } from '../../types/domain'
import { taskTypeLabel } from '../../utils/format'

export interface GroupProgress {
  group: number
  groupTotal: number
  current: number
  total: number
}

export const PracticeLayout = ({
  task,
  current,
  total,
  onExit,
  children,
  centered = false,
  contextLabel,
  groupProgress,
}: {
  task: LearningTask
  current: number
  total: number
  onExit: () => void
  children: ReactNode
  centered?: boolean
  contextLabel?: string
  groupProgress?: GroupProgress | null
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
        {groupProgress ? (
          <section className="practice-group-strip" aria-label="当前分组进度">
            <div>
              <span>当前分组</span>
              <strong>
                第 {groupProgress.group} / {groupProgress.groupTotal} 组
              </strong>
            </div>
            <div>
              <span>组内进度</span>
              <strong>
                第 {groupProgress.current} / {groupProgress.total} 个
              </strong>
            </div>
            <div className="practice-group-track">
              <div
                style={{
                  width: `${Math.min(100, Math.round((groupProgress.current / Math.max(groupProgress.total, 1)) * 100))}%`,
                }}
              />
            </div>
          </section>
        ) : null}
        {children}
      </main>
    </div>
  )
}
