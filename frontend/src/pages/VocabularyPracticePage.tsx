import {
  ArrowRight,
  BookOpenText,
  Check,
  CheckCircle2,
  RotateCcw,
  X,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { PracticeLayout } from '../features/practice/PracticeLayout'
import { Badge, Button, EmptyState } from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'
import type { LearningTask, PracticeAttempt } from '../types/domain'
import { formatDuration } from '../utils/format'

interface Feedback {
  given: string
  correct: boolean
}

const makeOptions = (task: LearningTask, index: number) => {
  const entry = task.snapshot[index]
  if (!entry) return []
  const correct = entry.meanings[0]
  const distractors: string[] = []
  for (let offset = 1; offset < task.snapshot.length && distractors.length < 3; offset += 1) {
    const candidate = task.snapshot[(index + offset) % task.snapshot.length]?.meanings[0]
    if (candidate && candidate !== correct && !distractors.includes(candidate)) {
      distractors.push(candidate)
    }
  }
  const options = [correct, ...distractors]
  const rotation = index % options.length
  return [...options.slice(rotation), ...options.slice(0, rotation)]
}

export const VocabularyPracticePage = () => {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { tasks, currentUser, refresh, showToast } = useAppStore()
  const task = tasks.find((candidate) => candidate.id === taskId)
  const taskExists = tasks.some((candidate) => candidate.id === taskId)
  const [attempt, setAttempt] = useState<PracticeAttempt | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [selected, setSelected] = useState('')
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [busy, setBusy] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const startedAtRef = useRef(performance.now())

  useEffect(() => {
    if (!taskId || !currentUser || !taskExists) {
      setAttempt(null)
      return
    }
    const nextAttempt = api.practice.startOrResume(taskId, currentUser.id)
    setAttempt(nextAttempt)
    setActiveIndex(nextAttempt.currentIndex)
    setShowResults(false)
    setFeedback(null)
    setSelected('')
    startedAtRef.current = performance.now()
  }, [taskId, currentUser, taskExists])

  const entry = task?.snapshot[activeIndex]
  const options = useMemo(
    () => (task && entry ? makeOptions(task, activeIndex) : []),
    [task, entry, activeIndex],
  )

  if (!task || !currentUser || !attempt) {
    return (
      <div className="practice-shell">
        <main className="practice-main practice-centered">
          <EmptyState
            icon={BookOpenText}
            title="无法开始练习"
            description="任务不存在，或当前账户无权访问。"
            action={<Link className="button button-primary button-md" to="/tasks">返回任务列表</Link>}
          />
        </main>
      </div>
    )
  }

  if (showResults) {
    const accuracy = attempt.total ? Math.round((attempt.score / attempt.total) * 100) : 0
    const wrongAnswers = attempt.answers.filter((answer) => !answer.correct)
    const totalDuration = attempt.answers.reduce((sum, answer) => sum + answer.durationMs, 0)
    return (
      <div className="practice-shell">
        <main className="practice-main practice-result-page">
          <section className="practice-result-card">
            <span className="result-kicker">练习完成</span>
            <h1>这一组练习结束了</h1>
            <p>答题事实和任务进度已经保存，可以随时回来再练一次。</p>
            <div className="result-score-row">
              <div className="score-ring" style={{ '--score': `${accuracy * 3.6}deg` } as React.CSSProperties}>
                <strong>{accuracy}%</strong>
                <span>正确率</span>
              </div>
              <div className="result-metrics">
                <div>
                  <strong>{attempt.score}/{attempt.total}</strong>
                  <span>答对题数</span>
                </div>
                <div>
                  <strong>{formatDuration(totalDuration)}</strong>
                  <span>答题用时</span>
                </div>
                <div>
                  <strong>{wrongAnswers.length}</strong>
                  <span>需要复习</span>
                </div>
              </div>
            </div>
            {wrongAnswers.length ? (
              <div className="result-wrong-list">
                <h2>本次错题</h2>
                {wrongAnswers.map((answer) => (
                  <div key={answer.id}>
                    <span>{answer.prompt}</span>
                    <p>{answer.expected}</p>
                    <small>你的答案：{answer.given}</small>
                  </div>
                ))}
              </div>
            ) : (
              <div className="result-perfect">
                <CheckCircle2 size={20} />
                本次全部答对，继续保持。
              </div>
            )}
            <div className="result-actions">
              <Link className="button button-primary button-md" to={`/tasks/${task.id}`}>
                返回任务详情
              </Link>
              <Link className="button button-secondary button-md" to="/learning">
                查看学习记录
              </Link>
            </div>
          </section>
        </main>
      </div>
    )
  }

  if (!entry) {
    return (
      <PracticeLayout task={task} current={attempt.currentIndex} total={attempt.total} onExit={() => navigate(`/tasks/${task.id}`)}>
        <div className="empty-state">
          <h3>没有更多题目</h3>
          <p>本次练习的题目已经结束。</p>
        </div>
      </PracticeLayout>
    )
  }

  const submit = async () => {
    if (!selected || busy) return
    setBusy(true)
    try {
      const result = await api.practice.submitAnswer(task.id, currentUser.id, {
        prompt: entry.word,
        expected: entry.meanings[0],
        given: selected,
        durationMs: Math.round(performance.now() - startedAtRef.current),
      })
      setAttempt(result.attempt)
      setFeedback({ given: selected, correct: result.isCorrect })
      refresh()
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '提交失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const advance = () => {
    if (attempt.status === 'completed') {
      setShowResults(true)
      return
    }
    setActiveIndex(attempt.currentIndex)
    setSelected('')
    setFeedback(null)
    startedAtRef.current = performance.now()
  }

  const exit = () => {
    api.practice.saveExit(attempt.id)
    navigate(`/tasks/${task.id}`)
  }

  const isCorrect = feedback?.correct
  return (
    <PracticeLayout task={task} current={activeIndex} total={attempt.total} onExit={exit}>
      <section className="vocab-practice-card">
        <div className="practice-question-meta">
          <Badge>词汇理解</Badge>
          <span>选择最符合单词含义的选项</span>
        </div>
        <div className="vocab-word-block">
          <h1>{entry.word}</h1>
          <p>{entry.phonetic} <span>{entry.partOfSpeech}</span></p>
        </div>
        <div className="vocab-options">
          {options.map((option, index) => {
            const isSelected = selected === option
            const optionState = feedback
              ? option === entry.meanings[0]
                ? 'correct'
                : isSelected
                  ? 'wrong'
                  : 'muted'
              : isSelected
                ? 'selected'
                : ''
            return (
              <button
                key={`${option}-${index}`}
                type="button"
                className={`vocab-option ${optionState}`}
                disabled={Boolean(feedback) || busy}
                onClick={() => setSelected(option)}
              >
                <span className="option-letter">{String.fromCharCode(65 + index)}</span>
                <span>{option}</span>
                {feedback && option === entry.meanings[0] ? <Check size={17} /> : null}
                {feedback && isSelected && !isCorrect ? <X size={17} /> : null}
              </button>
            )
          })}
        </div>

        {feedback ? (
          <div className={`answer-feedback ${isCorrect ? 'feedback-correct' : 'feedback-wrong'}`}>
            <div className="feedback-heading">
              {isCorrect ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              <strong>{isCorrect ? '回答正确' : '需要再记一下'}</strong>
            </div>
            <p>
              <strong>{entry.word}</strong> {entry.phonetic} · {entry.meanings.join('；')}
            </p>
            <blockquote>
              {entry.example}
              <small>{entry.exampleTranslation}</small>
            </blockquote>
          </div>
        ) : null}

        <footer className="practice-card-footer">
          <span className="practice-hint">
            {feedback ? '已保存本题答题记录' : '提交后会立即显示答案反馈'}
          </span>
          {feedback ? (
            <Button variant="primary" icon={ArrowRight} onClick={advance}>
              {attempt.status === 'completed' ? '查看练习结果' : '下一题'}
            </Button>
          ) : (
            <Button variant="primary" loading={busy} disabled={!selected} onClick={() => void submit()}>
              提交答案
            </Button>
          )}
        </footer>
      </section>

      <div className="practice-secondary-note">
        <RotateCcw size={14} />
        中途退出会自动保存进度，再次进入时可以从当前题继续
      </div>
    </PracticeLayout>
  )
}
