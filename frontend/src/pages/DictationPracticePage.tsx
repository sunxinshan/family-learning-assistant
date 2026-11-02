import {
  ArrowRight,
  CheckCircle2,
  Headphones,
  Play,
  RotateCcw,
  Volume2,
  XCircle,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { practiceApi } from '../api/mockApi'
import { PracticeLayout } from '../features/practice/PracticeLayout'
import { Badge, Button, EmptyState } from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import type { PracticeAttempt } from '../types/domain'
import { formatDuration } from '../utils/format'

interface Feedback {
  given: string
  correct: boolean
}

export const DictationPracticePage = () => {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { tasks, currentUser, refresh, showToast } = useAppStore()
  const task = tasks.find((candidate) => candidate.id === taskId)
  const [attempt, setAttempt] = useState<PracticeAttempt | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [answer, setAnswer] = useState('')
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [busy, setBusy] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const startedAtRef = useRef(performance.now())

  useEffect(() => {
    if (!taskId || !currentUser) return
    const nextAttempt = practiceApi.startOrResume(taskId, currentUser.id)
    setAttempt(nextAttempt)
    setActiveIndex(nextAttempt.currentIndex)
    setShowResults(false)
    setFeedback(null)
    setAnswer('')
    startedAtRef.current = performance.now()
  }, [taskId, currentUser])

  useEffect(
    () => () => {
      window.speechSynthesis?.cancel()
    },
    [],
  )

  if (!task || !currentUser || !attempt) {
    return (
      <div className="practice-shell">
        <main className="practice-main practice-centered">
          <EmptyState
            icon={Headphones}
            title="无法开始听写"
            description="任务不存在，或当前账户无权访问。"
            action={<Link className="button button-primary button-md" to="/tasks">返回任务列表</Link>}
          />
        </main>
      </div>
    )
  }

  const entry = task.snapshot[activeIndex]

  if (showResults) {
    const accuracy = attempt.total ? Math.round((attempt.score / attempt.total) * 100) : 0
    const wrongAnswers = attempt.answers.filter((item) => !item.correct)
    const totalDuration = attempt.answers.reduce((sum, item) => sum + item.durationMs, 0)
    return (
      <div className="practice-shell">
        <main className="practice-main practice-result-page">
          <section className="practice-result-card">
            <span className="result-kicker">听写完成</span>
            <h1>听写结果已保存</h1>
            <p>拼写错误已经进入复习事实，后续可以从学习记录继续查看。</p>
            <div className="result-score-row">
              <div className="score-ring" style={{ '--score': `${accuracy * 3.6}deg` } as React.CSSProperties}>
                <strong>{accuracy}%</strong>
                <span>正确率</span>
              </div>
              <div className="result-metrics">
                <div>
                  <strong>{attempt.score}/{attempt.total}</strong>
                  <span>拼写正确</span>
                </div>
                <div>
                  <strong>{formatDuration(totalDuration)}</strong>
                  <span>答题用时</span>
                </div>
                <div>
                  <strong>{wrongAnswers.length}</strong>
                  <span>拼写错题</span>
                </div>
              </div>
            </div>
            {wrongAnswers.length ? (
              <div className="result-wrong-list">
                <h2>本次错题</h2>
                {wrongAnswers.map((item) => (
                  <div key={item.id}>
                    <span>{item.prompt}</span>
                    <p>{item.expected}</p>
                    <small>你的拼写：{item.given}</small>
                  </div>
                ))}
              </div>
            ) : (
              <div className="result-perfect">
                <CheckCircle2 size={20} />
                全部拼写正确。可以再听写一次巩固记忆。
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
          <p>本次听写已经结束。</p>
        </div>
      </PracticeLayout>
    )
  }

  const speak = () => {
    if (!('speechSynthesis' in window)) {
      showToast('当前浏览器不支持语音合成，请使用支持 Web Speech 的浏览器', 'danger')
      return
    }
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(entry.word)
    utterance.lang = 'en-US'
    utterance.rate = 0.82
    utterance.pitch = 1
    utterance.onstart = () => setPlaying(true)
    utterance.onend = () => setPlaying(false)
    utterance.onerror = () => setPlaying(false)
    window.speechSynthesis.speak(utterance)
  }

  const submit = async () => {
    if (!answer.trim() || busy) return
    setBusy(true)
    try {
      const result = await practiceApi.submitAnswer(task.id, currentUser.id, {
        prompt: entry.word,
        expected: entry.word,
        given: answer,
        durationMs: Math.round(performance.now() - startedAtRef.current),
      })
      setAttempt(result.attempt)
      setFeedback({ given: answer.trim(), correct: result.isCorrect })
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
    setAnswer('')
    setFeedback(null)
    startedAtRef.current = performance.now()
  }

  const exit = () => {
    practiceApi.saveExit(attempt.id)
    navigate(`/tasks/${task.id}`)
  }

  return (
    <PracticeLayout task={task} current={activeIndex} total={attempt.total} onExit={exit} centered>
      <section className="dictation-practice-card">
        <div className="practice-question-meta">
          <Badge>听写拼写</Badge>
          <span>听单词并输入完整拼写</span>
        </div>

        <div className="dictation-audio-area">
          <button type="button" className={`audio-play-button ${playing ? 'is-playing' : ''}`} onClick={speak}>
            {playing ? <Volume2 size={30} /> : <Play size={30} fill="currentColor" />}
          </button>
          <div>
            <h1>{playing ? '正在播放…' : '点击播放单词'}</h1>
            <p>可以重复播放，不会影响答题记录</p>
          </div>
          <Button size="sm" icon={RotateCcw} onClick={speak}>重播</Button>
        </div>

        <div className="dictation-wave" aria-hidden="true">
          {Array.from({ length: 32 }, (_, index) => (
            <i
              key={index}
              style={{ height: `${12 + ((index * 13) % 28)}px` }}
            />
          ))}
        </div>

        <div className="dictation-answer-area">
          <label htmlFor="dictation-answer">输入你听到的单词</label>
          <input
            id="dictation-answer"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submit()
            }}
            disabled={Boolean(feedback) || busy}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="Type the word…"
            autoFocus
          />
        </div>

        {feedback ? (
          <div className={`answer-feedback ${feedback.correct ? 'feedback-correct' : 'feedback-wrong'}`}>
            <div className="feedback-heading">
              {feedback.correct ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              <strong>{feedback.correct ? '拼写正确' : '拼写需要修正'}</strong>
            </div>
            <div className="dictation-answer-reveal">
              <span>正确拼写</span>
              <strong>{entry.word}</strong>
              <small>{entry.phonetic} · {entry.meanings.join('；')}</small>
            </div>
            {!feedback.correct ? <p>你的答案：{feedback.given}</p> : null}
            <blockquote>
              {entry.example}
              <small>{entry.exampleTranslation}</small>
            </blockquote>
          </div>
        ) : null}

        <footer className="practice-card-footer">
          <span className="practice-hint">
            {feedback ? '本题已保存，可继续下一题' : '按 Enter 也可以提交'}
          </span>
          {feedback ? (
            <Button variant="primary" icon={ArrowRight} onClick={advance}>
              {attempt.status === 'completed' ? '查看听写结果' : '下一题'}
            </Button>
          ) : (
            <Button
              variant="primary"
              loading={busy}
              disabled={!answer.trim()}
              onClick={() => void submit()}
            >
              提交拼写
            </Button>
          )}
        </footer>
      </section>

      <div className="practice-secondary-note">
        <Headphones size={14} />
        原型使用浏览器语音合成模拟音频；正式版本将由听写服务提供音频
      </div>
    </PracticeLayout>
  )
}
