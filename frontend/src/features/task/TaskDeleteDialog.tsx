import { useState } from 'react'
import { Button, Modal } from '../../components/ui'
import { useAppStore } from '../../stores/AppStoreContext'
import type { LearningTask } from '../../types/domain'

interface TaskDeleteDialogProps {
  task: LearningTask | null
  practiceCount?: number
  onClose: () => void
  onDeleted?: (task: LearningTask) => void
}

/**
 * 任务删除的两步确认。任何状态的任务都可以删除，
 * 删除会连带移除该任务下的练习记录与答题事实。
 */
export const TaskDeleteDialog = ({
  task,
  practiceCount = 0,
  onClose,
  onDeleted,
}: TaskDeleteDialogProps) => {
  const { removeTask, showToast } = useAppStore()
  const [stage, setStage] = useState<1 | 2>(1)
  const [busy, setBusy] = useState(false)

  const close = () => {
    if (busy) return
    setStage(1)
    onClose()
  }

  const confirm = async () => {
    if (!task) return
    setBusy(true)
    try {
      await removeTask(task.id)
      showToast('任务及关联练习记录已删除', 'success')
      setStage(1)
      onDeleted?.(task)
      onClose()
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '删除失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={Boolean(task)}
      title={stage === 1 ? '删除学习任务' : '再次确认删除'}
      description={
        stage === 1
          ? '这是第一次确认。请核对删除对象及其影响。'
          : '此操作不可撤销，请进行第二次明确确认。'
      }
      width="sm"
      danger
      onClose={close}
      footer={
        <>
          <Button onClick={close}>取消</Button>
          {stage === 1 ? (
            <Button variant="danger" onClick={() => setStage(2)}>
              继续删除
            </Button>
          ) : (
            <Button variant="danger" loading={busy} onClick={() => void confirm()}>
              永久删除
            </Button>
          )}
        </>
      }
    >
      <div className="danger-summary">
        <strong>{task?.name}</strong>
        <p>
          任务、{practiceCount} 条练习记录和相关答题事实都会被删除。
          {task?.status === 'completed' ? '该任务已完成，删除后练习结果不再保留。' : null}
        </p>
        {stage === 2 ? <span>第二次确认已就绪。</span> : null}
      </div>
    </Modal>
  )
}
