import {
  ArrowLeft,
  BookOpenText,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Headphones,
  LockKeyhole,
  MessageSquare,
  Pencil,
  Play,
  Trash2,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { taskApi } from '../api/mockApi'
import {
  Badge,
  Button,
  EmptyState,
  Field,
  InlineError,
  Modal,
  PageHeader,
  ProgressBar,
  TextInput,
} from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import {
  formatDateTime,
  practicePath,
  taskModeLabel,
  taskStatusLabel,
  taskStatusTone,
  taskTypeLabel,
} from '../utils/format'

export const TaskDetailPage = () => {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { tasks, practices, currentUser, refresh, showToast } = useAppStore()
  const task = tasks.find((candidate) => candidate.id === taskId)
  const attempts = useMemo(
    () =>
      practices
        .filter((attempt) => attempt.taskId === taskId)
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    [practices, taskId],
  )
  const [editOpen, setEditOpen] = useState(false)
  const [deleteStage, setDeleteStage] = useState<0 | 1 | 2>(0)
  const [name, setName] = useState(task?.name ?? '')
  const [wordsPerGroup, setWordsPerGroup] = useState(task?.config.wordsPerGroup ?? 0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (!task || !currentUser) {
    return (
      <main className="page-container">
        <EmptyState
          icon={BookOpenText}
          title="任务不存在"
          description="它可能已经被删除。返回任务列表查看当前可用的学习任务。"
          action={<Link className="button button-primary button-md" to="/tasks">返回任务列表</Link>}
        />
      </main>
    )
  }

  const Icon = task.type === 'vocabulary' ? BookOpenText : Headphones
  const fixed = task.mode === 'fixed'

  const openEditor = () => {
    setName(task.name)
    setWordsPerGroup(task.config.wordsPerGroup)
    setError('')
    setEditOpen(true)
  }

  const saveEdit = async () => {
    if (!name.trim()) {
      setError('任务名称不能为空')
      return
    }
    if (!fixed && (wordsPerGroup < 1 || wordsPerGroup > task.targetCount)) {
      setError('每组数量不能大于已选词条数量')
      return
    }
    setBusy(true)
    setError('')
    try {
      await taskApi.update(currentUser.id, task.id, {
        name: name.trim(),
        ...(fixed
          ? {}
          : {
              config: {
                ...task.config,
                questionCount: task.targetCount,
                wordsPerGroup,
                totalGroups: Math.ceil(task.targetCount / wordsPerGroup),
              },
            }),
      })
      refresh()
      setEditOpen(false)
      showToast('任务配置已更新', 'success')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '更新失败')
    } finally {
      setBusy(false)
    }
  }

  const removeTask = async () => {
    setBusy(true)
    try {
      await taskApi.remove(currentUser.id, task.id)
      refresh()
      showToast('任务及关联练习记录已删除', 'success')
      navigate('/tasks', { replace: true })
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '删除失败', 'danger')
    } finally {
      setBusy(false)
      setDeleteStage(0)
    }
  }

  return (
    <main className="page-container task-detail-page">
      <Link to="/tasks" className="back-link">
        <ArrowLeft size={15} />
        返回任务列表
      </Link>

      <PageHeader
        eyebrow={`${task.subject === 'english' ? '英语' : '语文'} · ${taskTypeLabel(task.type)}`}
        title={task.name}
        description={`任务内容来自「${task.libraryName}」的创建时快照。`}
        actions={
          <>
            <Link className="button button-primary button-md" to={practicePath(task)}>
              <Play size={16} />
              {task.status === 'completed' ? '再练一次' : '继续学习'}
            </Link>
            <Button icon={Pencil} onClick={openEditor}>编辑</Button>
            <Button variant="ghost" icon={Trash2} onClick={() => setDeleteStage(1)}>删除</Button>
          </>
        }
      />

      <div className="detail-grid">
        <div className="detail-main">
          <section className="panel task-overview-panel">
            <div className="task-overview-head">
              <div className={`task-detail-icon task-type-${task.type}`}>
                <Icon size={22} />
              </div>
              <div>
                <div className="inline-badges">
                  <Badge tone={taskStatusTone(task.status)}>{taskStatusLabel(task.status)}</Badge>
                  <Badge>{task.subject === 'english' ? '英语' : '语文'}</Badge>
                  <Badge>{taskModeLabel(task.mode)}</Badge>
                  {task.config.repeatUntilCorrect ? <Badge tone="warning">强制答对</Badge> : null}
                </div>
                <h2>学习进度</h2>
                <p>{task.progress >= 100 ? '已完成全部任务内容' : '进度会随练习提交自动保存'}</p>
              </div>
              <div className="large-progress-number">{task.progress}%</div>
            </div>
            <ProgressBar value={task.progress} />
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>任务配置</h2>
                <p>创建时内容快照已固定，原词库后续变化不会影响该任务。</p>
              </div>
              {fixed ? (
                <Badge tone="warning">
                  <LockKeyhole size={12} />
                  内容已锁定
                </Badge>
              ) : null}
            </div>
            <dl className="detail-list">
              <div>
                <dt>学习类型</dt>
                <dd>{taskTypeLabel(task.type)}</dd>
              </div>
              <div>
                <dt>已选内容</dt>
                <dd>{task.targetCount} 项词条</dd>
              </div>
              {!fixed ? (
                <div>
                  <dt>分组规则</dt>
                  <dd>每组 {task.config.wordsPerGroup} 项 · 共 {task.config.totalGroups} 组</dd>
                </div>
              ) : null}
              <div>
                <dt>内容来源</dt>
                <dd>{task.libraryName}</dd>
              </div>
              <div>
                <dt>创建时间</dt>
                <dd>{formatDateTime(task.createdAt)}</dd>
              </div>
              <div>
                <dt>最近更新</dt>
                <dd>{formatDateTime(task.updatedAt)}</dd>
              </div>
              {task.type === 'dictation' && task.config.dictation ? (
                <>
                  <div>
                    <dt>听写方式</dt>
                    <dd>{task.config.dictation.mode === 'online' ? '线上听写' : '线下听写'}</dd>
                  </div>
                  <div>
                    <dt>播放方式</dt>
                    <dd>
                      {task.config.dictation.playbackMode === 'auto'
                        ? `自动 · ${task.config.dictation.intervalSeconds} 秒`
                        : '手动播放'}
                    </dd>
                  </div>
                  <div>
                    <dt>朗读时显示</dt>
                    <dd>
                      {task.config.dictation.hint === 'phonetic'
                        ? task.subject === 'english' ? '英语音标' : '语文拼音'
                        : '中文释义'}
                    </dd>
                  </div>
                  <div>
                    <dt>朗读次数</dt>
                    <dd>{task.config.dictation.repeatCount ?? 1} 次</dd>
                  </div>
                </>
              ) : null}
            </dl>
            {fixed ? (
              <div className="info-note">
                <LockKeyhole size={15} />
                固定任务创建后不能修改学习内容。如需调整内容，请删除该任务后重新创建。
              </div>
            ) : null}
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>内容快照</h2>
                <p>练习题目只会从任务创建时的内容快照中生成。</p>
              </div>
              <span className="panel-count">{task.snapshot.length} 个词条</span>
            </div>
            <div className="snapshot-list">
              {task.snapshot.slice(0, 8).map((entry) => (
                <div key={entry.id}>
                  <strong>{entry.word}</strong>
                  <span>{entry.phonetic}</span>
                  <p>{entry.meanings.join('；')}</p>
                </div>
              ))}
            </div>
            {task.snapshot.length > 8 ? (
              <p className="panel-footnote">其余 {task.snapshot.length - 8} 个词条会在练习中依次出现。</p>
            ) : null}
          </section>
        </div>

        <aside className="detail-side">
          <section className="panel compact-panel">
            <div className="panel-header">
              <div>
                <h2>学习记录</h2>
                <p>该任务的全部练习 Attempt。</p>
              </div>
            </div>
            <div className="attempt-list">
              {attempts.length ? (
                attempts.map((attempt) => (
                  <div key={attempt.id} className="attempt-row">
                    <span className={`attempt-status attempt-${attempt.status}`}>
                      {attempt.status === 'completed' ? <CheckCircle2 size={15} /> : <Clock3 size={15} />}
                    </span>
                    <div>
                      <strong>
                        {attempt.status === 'completed'
                          ? `${attempt.score}/${attempt.total} 正确`
                          : `进行到 ${attempt.currentIndex}/${attempt.total}`}
                      </strong>
                      <span>{formatDateTime(attempt.updatedAt)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="muted-copy">尚未开始练习。</p>
              )}
            </div>
          </section>

          <section className="panel compact-panel">
            <div className="panel-header">
              <div>
                <h2>协同操作</h2>
                <p>页面的修改与 Agent 使用同一套业务能力。</p>
              </div>
            </div>
            <Link to="/" className="subtle-link">
              <MessageSquare size={15} />
              回到 Agent 对话
            </Link>
          </section>

          <section className="meta-card">
            <CalendarDays size={15} />
            <span>创建于 {formatDateTime(task.createdAt)}</span>
          </section>
        </aside>
      </div>

      <Modal
        open={editOpen}
        title="编辑学习任务"
        description={fixed ? '固定任务仅允许修改名称，学习内容保持锁定。' : '修改会通过 Task Service 保存，并记录关键操作日志。'}
        onClose={() => setEditOpen(false)}
        footer={
          <>
            <Button onClick={() => setEditOpen(false)}>取消</Button>
            <Button variant="primary" loading={busy} onClick={() => void saveEdit()}>
              保存修改
            </Button>
          </>
        }
      >
        <div className="form-stack">
          {error ? <InlineError>{error}</InlineError> : null}
          <Field label="任务名称">
            <TextInput value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          {!fixed ? (
            <Field label="每组数量" hint={`已选 ${task.targetCount} 项词条`}>
              <TextInput
                type="number"
                min={1}
                max={task.targetCount}
                value={wordsPerGroup}
                onChange={(event) => setWordsPerGroup(Number(event.target.value))}
              />
            </Field>
          ) : null}
          {!fixed ? (
            <div className="info-note">
              修改分组规则后，从下一组开始生效；当前组继续使用旧规则。
            </div>
          ) : null}
        </div>
      </Modal>

      <Modal
        open={deleteStage > 0}
        title={deleteStage === 1 ? '删除学习任务' : '再次确认删除'}
        description={
          deleteStage === 1
            ? '这是第一次确认。请核对删除对象及其影响。'
            : '此操作不可撤销，请进行第二次明确确认。'
        }
        width="sm"
        danger
        onClose={() => setDeleteStage(0)}
        footer={
          <>
            <Button onClick={() => setDeleteStage(0)}>取消</Button>
            {deleteStage === 1 ? (
              <Button variant="danger" onClick={() => setDeleteStage(2)}>继续删除</Button>
            ) : (
              <Button variant="danger" loading={busy} onClick={() => void removeTask()}>
                永久删除
              </Button>
            )}
          </>
        }
      >
        <div className="danger-summary">
          <strong>{task.name}</strong>
          <p>任务、{attempts.length} 条练习记录和相关答题事实都会被删除。</p>
          {deleteStage === 2 ? <span>第二次确认已就绪。</span> : null}
        </div>
      </Modal>
    </main>
  )
}
