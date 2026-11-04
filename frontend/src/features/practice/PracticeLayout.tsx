import { ArrowLeft, LogOut } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { Button } from '../../components/ui'
import type { LearningTask } from '../../types/domain'
import { taskTypeLabel } from '../../utils/format'
import { useKeyboardViewport } from './useKeyboardViewport'

export interface GroupProgress {
  group: number
  groupTotal: number
  current: number
  total: number
  /** 第二列的标题，强制重做时是「本轮进度」 */
  label?: string
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
  roundLabel,
}: {
  task: LearningTask
  current: number
  total: number
  onExit: () => void
  children: ReactNode
  centered?: boolean
  contextLabel?: string
  groupProgress?: GroupProgress | null
  roundLabel?: string
}) => {
  const progress = total > 0 ? Math.round((current / total) * 100) : 0
  // 手机软键盘弹起后，整页收缩到键盘上方的可视区域，按钮才不会被键盘盖住。
  const keyboard = useKeyboardViewport()
  const shellStyle = keyboard.keyboardOpen
    ? ({
        '--practice-vh': `${keyboard.height}px`,
        '--practice-vt': `${keyboard.offsetTop}px`,
      } as CSSProperties)
    : undefined
  return (
    <div
      className={`practice-shell${keyboard.keyboardOpen ? ' is-keyboard' : ''}`}
      style={shellStyle}
    >
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
              <span>{groupProgress.label ?? '组内进度'}</span>
              <strong>
                第 {groupProgress.current} / {groupProgress.total} 个
              </strong>
            </div>
            {roundLabel ? (
              <div>
                <span>练习轮次</span>
                <strong>{roundLabel}</strong>
              </div>
            ) : null}
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
