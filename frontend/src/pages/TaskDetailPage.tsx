import {
  ArrowLeft,
  BookOpenText,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Headphones,
  LockKeyhole,
  MessageSquare,
  Pencil,
  Play,
  RotateCcw,
  Settings2,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Field,
  InlineError,
  Modal,
  PageHeader,
  ProgressBar,
  SelectInput,
  TextInput,
} from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'
import type {
  DictationHint,
  DictationMode,
  PlaybackMode,
  WrongQuestions,
} from '../types/domain'
import {
  formatDateTime,
  practicePath,
  taskModeLabel,
  taskStatusLabel,
  taskStatusTone,
  taskTypeLabel,
  wrongPracticePath,
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
  const [taskMode, setTaskMode] = useState<'fixed' | 'long_term'>(task?.mode ?? 'fixed')
  const [repeatUntilCorrect, setRepeatUntilCorrect] = useState(
    task?.config.repeatUntilCorrect ?? false,
  )
  const [dictationMode, setDictationMode] = useState<DictationMode>(
    task?.config.dictation?.mode ?? 'online',
  )
  const [playbackMode, setPlaybackMode] = useState<PlaybackMode>(
    task?.config.dictation?.playbackMode ?? 'manual',
  )
  const [intervalSeconds, setIntervalSeconds] = useState(
    task?.config.dictation?.intervalSeconds ?? 5,
  )
  const [repeatCount, setRepeatCount] = useState(task?.config.dictation?.repeatCount ?? 1)
  const [hint, setHint] = useState<DictationHint>(task?.config.dictation?.hint ?? 'phonetic')
  const [wrongQuestions, setWrongQuestions] = useState<WrongQuestions | null>(null)
  const [wrongQuestionsLoading, setWrongQuestionsLoading] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!task || !currentUser) return
    let cancelled = false
    setWrongQuestionsLoading(true)
    void api.practice
      .getWrongQuestions(task.id, currentUser.id)
      .then((result) => {
        if (!cancelled) setWrongQuestions(result)
      })
      .catch(() => {
        if (!cancelled) setWrongQuestions(null)
      })
      .finally(() => {
        if (!cancelled) setWrongQuestionsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentUser, practices.length, task, task?.id, task?.updatedAt])

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
    setTaskMode(task.mode)
    setRepeatUntilCorrect(task.config.repeatUntilCorrect)
    setDictationMode(task.config.dictation?.mode ?? 'online')
    setPlaybackMode(task.config.dictation?.playbackMode ?? 'manual')
    setIntervalSeconds(task.config.dictation?.intervalSeconds ?? 5)
    setRepeatCount(task.config.dictation?.repeatCount ?? 1)
    setHint(task.config.dictation?.hint ?? 'phonetic')
    setError('')
    setEditOpen(true)
  }

  const saveEdit = async () => {
    if (!name.trim()) {
      setError('任务名称不能为空')
      return
    }
    if (taskMode === 'long_term' && (wordsPerGroup < 1 || wordsPerGroup > task.targetCount)) {
      setError('每组数量不能大于已选词条数量')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.task.update(currentUser.id, task.id, {
        name: name.trim(),
        mode: taskMode,
        config: {
          ...task.config,
          questionCount: task.targetCount,
          wordsPerGroup: taskMode === 'fixed' ? task.targetCount : wordsPerGroup,
          totalGroups: taskMode === 'fixed' ? 1 : Math.ceil(task.targetCount / wordsPerGroup),
          repeatUntilCorrect,
          dictation: {
            mode: dictationMode,
            playbackMode,
            intervalSeconds,
            repeatCount,
            hint,
          },
        },
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
      await api.task.remove(currentUser.id, task.id)
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
              {task.status === 'completed'
                ? '再练一次'
                : attempts.length
                  ? '继续学习'
                  : '开始学习'}
            </Link>
            {wrongQuestions?.total ? (
              <Link className="button button-secondary button-md" to={wrongPracticePath(task)}>
                <RotateCcw size={16} />
                练习错题 {wrongQuestions.total}
              </Link>
            ) : (
              <Button icon={RotateCcw} disabled title="完成练习并产生错题后可用">
                练习错题
              </Button>
            )}
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

          <section className="panel wrong-question-panel">
            <div className="panel-header">
              <div>
                <h2>练习错题</h2>
                <p>
                  答错的词条会保留在这里；之后连续答对 {wrongQuestions?.requiredCorrectStreak ?? 2}{' '}
                  次后自动移出。
                </p>
              </div>
              <Badge tone={wrongQuestions?.total ? 'warning' : 'success'}>
                {wrongQuestionsLoading
                  ? '读取中'
                  : wrongQuestions?.total
                    ? `${wrongQuestions.total} 项待复习`
                    : '暂无错题'}
              </Badge>
            </div>
            {wrongQuestions?.groups.length ? (
              <div className="wrong-question-groups">
                {wrongQuestions.groups.map((group) => (
                  <section className="wrong-question-group" key={group.groupIndex}>
                    <header>
                      <strong>{fixed ? '全部错题' : `第 ${group.groupIndex} 组`}</strong>
                      <span>{group.entries.length} 项</span>
                    </header>
                    <div>
                      {group.entries.map((entry) => (
                        <article key={entry.snapshotEntryId}>
                          <div>
                            <strong>{entry.word}</strong>
                            <span>{entry.phonetic}</span>
                          </div>
                          <p>{entry.meanings.join('；')}</p>
                          <small>
                            {entry.consecutiveCorrect > 0
                              ? `已连续答对 ${entry.consecutiveCorrect} 次，再答对 ${Math.max(
                                  wrongQuestions.requiredCorrectStreak - entry.consecutiveCorrect,
                                  1,
                                )} 次移出`
                              : `连续答对 ${wrongQuestions.requiredCorrectStreak} 次后移出`}
                          </small>
                        </article>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            ) : (
              <div className="wrong-question-empty">
                <CheckCircle2 size={18} />
                <span>
                  {wrongQuestionsLoading ? '正在读取错题记录…' : '目前没有待复习的错题。'}
                </span>
              </div>
            )}
            {wrongQuestions?.total ? (
              <div className="wrong-question-actions">
                <Link className="button button-primary button-md" to={wrongPracticePath(task)}>
                  <RotateCcw size={16} />
                  开始练习错题
                </Link>
                {!fixed ? <span>长期任务错题按原任务分组展示。</span> : null}
              </div>
            ) : null}
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
                        {attempt.kind === 'wrong' ? '错题复习 · ' : ''}
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
        description="可修改任务名称、重做规则和听写配置；创建时保存的词条快照保持不变。"
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
          <details className="advanced-settings">
            <summary>
              <span className="advanced-settings-title">
                <Settings2 size={16} />
                高级设置
              </span>
              <span className="advanced-settings-summary">
                {taskModeLabel(taskMode)} · {taskMode === 'fixed' ? '固定内容' : `每组 ${wordsPerGroup} 项`} · 强制重做
                {repeatUntilCorrect ? '开' : '关'}
              </span>
              <ChevronDown size={16} className="advanced-settings-chevron" />
            </summary>
            <div className="advanced-settings-body">
              <Field label="学习类型">
                <SelectInput value={task.type} disabled aria-readonly="true">
                  <option value="dictation">{taskTypeLabel(task.type)}（V1 唯一正式类型）</option>
                </SelectInput>
              </Field>
              <Field label="任务模式">
                <SelectInput
                  value={taskMode}
                  onChange={(event) => setTaskMode(event.target.value as 'fixed' | 'long_term')}
                >
                  <option value="fixed">固定任务</option>
                  <option value="long_term">长期任务</option>
                </SelectInput>
              </Field>
              {taskMode === 'long_term' ? (
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
              <Checkbox
                checked={repeatUntilCorrect}
                onChange={setRepeatUntilCorrect}
                label="答对后才能进入下一组"
              />
            </div>
          </details>
          <div className="form-grid-two">
            <Field label="听写方式">
              <SelectInput
                value={dictationMode}
                onChange={(event) => setDictationMode(event.target.value as DictationMode)}
              >
                <option value="online">线上听写</option>
                <option value="offline">线下听写</option>
              </SelectInput>
            </Field>
            <Field label="播放方式">
              <SelectInput
                value={playbackMode}
                onChange={(event) => setPlaybackMode(event.target.value as PlaybackMode)}
              >
                <option value="manual">手动播放</option>
                <option value="auto">自动播放</option>
              </SelectInput>
            </Field>
          </div>
          <div className="form-grid-two">
            <Field label="自动播放间隔">
              <TextInput
                type="number"
                min={2}
                max={60}
                value={intervalSeconds}
                disabled={playbackMode !== 'auto'}
                onChange={(event) => setIntervalSeconds(Number(event.target.value))}
              />
            </Field>
            <Field label="朗读次数">
              <TextInput
                type="number"
                min={1}
                max={5}
                value={repeatCount}
                onChange={(event) => setRepeatCount(Number(event.target.value))}
              />
            </Field>
          </div>
          <Field label="朗读内容">
            <SelectInput value={hint} onChange={(event) => setHint(event.target.value as DictationHint)}>
              <option value="phonetic">{task.subject === 'english' ? '英语音标' : '语文拼音'}</option>
              <option value="meaning">中文含义</option>
            </SelectInput>
          </Field>
          <div className="info-note">任务词条快照不可替换；其他配置可在后续练习中生效。</div>
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
