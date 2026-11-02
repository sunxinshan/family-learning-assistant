import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Headphones,
  ListChecks,
  Play,
  RotateCcw,
  Volume2,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { practiceApi } from '../api/mockApi'
import { PracticeLayout } from '../features/practice/PracticeLayout'
import { Badge, Button, EmptyState } from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import type { DictationConfig, PracticeAttempt } from '../types/domain'
import { formatDuration } from '../utils/format'

interface Feedback {
  given: string
  correct: boolean
}

const defaultDictationConfig: DictationConfig = {
  mode: 'online',
  playbackMode: 'manual',
  intervalSeconds: 5,
  hint: 'phonetic',
}

export const DictationPracticePage = () => {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { tasks, currentUser, refresh, showToast } = useAppStore()
  const task = tasks.find((candidate) => candidate.id === taskId)
  const config = task?.config.dictation ?? defaultDictationConfig
  const isOffline = config.mode === 'offline'
  const [attempt, setAttempt] = useState<PracticeAttempt | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [offlineIndex, setOfflineIndex] = useState(0)
  const [offlineReview, setOfflineReview] = useState(false)
  const [wrongEntryIds, setWrongEntryIds] = useState<string[]>([])
  const [answer, setAnswer] = useState('')
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [busy, setBusy] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [countdown, setCountdown] = useState<number | null>(null)
  const [showResults, setShowResults] = useState(false)
  const startedAtRef = useRef(performance.now())
  const entry = task?.snapshot[activeIndex]
  const offlineEntry = task?.snapshot[offlineIndex]

  useEffect(() => {
    if (!taskId || !currentUser) return
    const nextAttempt = practiceApi.startOrResume(taskId, currentUser.id)
    setAttempt(nextAttempt)
    setActiveIndex(nextAttempt.currentIndex)
    setOfflineIndex(0)
    setOfflineReview(false)
    setWrongEntryIds([])
    setShowResults(false)
    setFeedback(null)
    setAnswer('')
    startedAtRef.current = performance.now()
  }, [taskId, currentUser])

  const speakWord = useCallback(
    (word: string) => {
      if (!('speechSynthesis' in window)) {
        showToast('当前浏览器不支持语音合成，请使用支持 Web Speech 的浏览器', 'danger')
        return
      }
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(word)
      utterance.lang = task?.subject === 'chinese' ? 'zh-CN' : 'en-US'
      utterance.rate = task?.subject === 'chinese' ? 0.86 : 0.82
      utterance.pitch = 1
      utterance.onstart = () => setPlaying(true)
      utterance.onend = () => setPlaying(false)
      utterance.onerror = () => setPlaying(false)
      window.speechSynthesis.speak(utterance)
    },
    [showToast, task?.subject],
  )

  useEffect(() => {
    if (
      !task ||
      !attempt ||
      isOffline ||
      showResults ||
      feedback ||
      !entry ||
      config.playbackMode !== 'auto'
    ) {
      setCountdown(null)
      return
    }
    speakWord(entry.word)
    let remaining = Math.max(2, config.intervalSeconds)
    setCountdown(remaining)
    const timer = window.setInterval(() => {
      remaining -= 1
      if (remaining <= 0) {
        speakWord(entry.word)
        remaining = Math.max(2, config.intervalSeconds)
      }
      setCountdown(remaining)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [
    attempt?.id,
    config.intervalSeconds,
    config.playbackMode,
    entry?.id,
    entry?.word,
    feedback,
    isOffline,
    showResults,
    speakWord,
    task?.id,
  ])

  useEffect(() => {
    if (
      !task ||
      !attempt ||
      !isOffline ||
      offlineReview ||
      showResults ||
      !offlineEntry ||
      config.playbackMode !== 'auto'
    ) {
      setCountdown(null)
      return
    }
    speakWord(offlineEntry.word)
    let remaining = Math.max(2, config.intervalSeconds)
    setCountdown(remaining)
    const timer = window.setInterval(() => {
      remaining -= 1
      if (remaining <= 0) {
        if (offlineIndex + 1 < task.snapshot.length) {
          setOfflineIndex((current) => current + 1)
        } else {
          setOfflineReview(true)
        }
        remaining = Math.max(2, config.intervalSeconds)
      }
      setCountdown(remaining)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [
    attempt?.id,
    config.intervalSeconds,
    config.playbackMode,
    isOffline,
    offlineEntry?.id,
    offlineIndex,
    offlineReview,
    showResults,
    speakWord,
    task?.id,
  ])

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

  const hintFor = (word: (typeof task.snapshot)[number] | undefined) => {
    if (!word) return ''
    return config.hint === 'phonetic' ? word.phonetic : word.meanings.join('；')
  }

  if (showResults) {
    const accuracy = attempt.total ? Math.round((attempt.score / attempt.total) * 100) : 0
    const wrongAnswers = attempt.answers.filter((item) => !item.correct)
    const totalDuration = attempt.answers.reduce((sum, item) => sum + item.durationMs, 0)
    return (
      <div className="practice-shell">
        <main className="practice-main practice-result-page">
          <section className="practice-result-card">
            <span className="result-kicker">听写完成</span>
            <h1>{isOffline ? '线下听写自查已提交' : '听写结果已保存'}</h1>
            <p>答题事实和任务进度已经保存，可以随时回来再练一次。</p>
            <div className="result-score-row">
              <div className="score-ring" style={{ '--score': `${accuracy * 3.6}deg` } as React.CSSProperties}>
                <strong>{accuracy}%</strong>
                <span>正确率</span>
              </div>
              <div className="result-metrics">
                <div>
                  <strong>{attempt.score}/{attempt.total}</strong>
                  <span>{isOffline ? '自查正确' : '拼写正确'}</span>
                </div>
                <div>
                  <strong>{formatDuration(totalDuration)}</strong>
                  <span>练习用时</span>
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
                {wrongAnswers.map((item) => (
                  <div key={item.id}>
                    <span>{item.prompt}</span>
                    <p>{item.expected}</p>
                    <small>{isOffline ? '已由用户自查标记为错误' : `你的拼写：${item.given}`}</small>
                  </div>
                ))}
              </div>
            ) : (
              <div className="result-perfect">
                <CheckCircle2 size={20} />
                本次全部正确，继续保持。
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

  const exit = () => {
    practiceApi.saveExit(attempt.id)
    navigate(`/tasks/${task.id}`)
  }

  if (isOffline) {
    const submitOffline = async () => {
      setBusy(true)
      try {
        const result = await practiceApi.submitOfflineAttempt(
          task.id,
          currentUser.id,
          wrongEntryIds,
        )
        setAttempt(result.attempt)
        refresh()
        setShowResults(true)
      } catch (cause) {
        showToast(cause instanceof Error ? cause.message : '提交失败', 'danger')
      } finally {
        setBusy(false)
      }
    }

    const toggleWrong = (entryId: string) => {
      setWrongEntryIds((current) =>
        current.includes(entryId)
          ? current.filter((id) => id !== entryId)
          : [...current, entryId],
      )
    }

    if (offlineReview) {
      return (
        <PracticeLayout
          task={task}
          current={task.snapshot.length}
          total={attempt.total}
          onExit={exit}
          centered
        >
          <section className="dictation-practice-card offline-review-card">
            <div className="practice-question-meta">
              <Badge>线下听写核对</Badge>
              <span>勾选你在纸上写错的词语，其他词条将按正确记录。</span>
            </div>
            <div className="offline-review-heading">
              <ListChecks size={20} />
              <div>
                <h1>提交线下自查结果</h1>
                <p>共 {task.snapshot.length} 个词语，已标记 {wrongEntryIds.length} 个错误。</p>
              </div>
            </div>
            <div className="offline-review-list">
              {task.snapshot.map((word, index) => (
                <label
                  key={word.id}
                  className={`offline-review-row ${wrongEntryIds.includes(word.id) ? 'is-wrong' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={wrongEntryIds.includes(word.id)}
                    onChange={() => toggleWrong(word.id)}
                  />
                  <span className="offline-review-index">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <strong>{word.word}</strong>
                    <p>{word.phonetic} · {word.meanings.join('；')}</p>
                  </div>
                  <Badge tone={wrongEntryIds.includes(word.id) ? 'danger' : 'success'}>
                    {wrongEntryIds.includes(word.id) ? '写错了' : '正确'}
                  </Badge>
                </label>
              ))}
            </div>
            <footer className="practice-card-footer">
              <Button icon={ArrowLeft} onClick={() => setOfflineReview(false)}>
                返回播放
              </Button>
              <Button variant="primary" loading={busy} onClick={() => void submitOffline()}>
                提交自查结果
              </Button>
            </footer>
          </section>
        </PracticeLayout>
      )
    }

    return (
      <PracticeLayout
        task={task}
        current={offlineIndex}
        total={task.snapshot.length}
        onExit={exit}
        centered
      >
        <section className="dictation-practice-card">
          <div className="practice-question-meta">
            <Badge>线下听写</Badge>
            <span>在纸上完成听写，全部播放后进入自查核对。</span>
          </div>
          <div className="offline-dictation-progress">
            <span>当前第 {offlineIndex + 1} / {task.snapshot.length} 个词</span>
            <Badge tone={config.playbackMode === 'auto' ? 'info' : 'neutral'}>
              {config.playbackMode === 'auto' ? `自动播放 · ${config.intervalSeconds} 秒` : '手动播放'}
            </Badge>
          </div>
          <div className="dictation-audio-area offline-audio-area">
            <button
              type="button"
              className={`audio-play-button ${playing ? 'is-playing' : ''}`}
              onClick={() => offlineEntry && speakWord(offlineEntry.word)}
            >
              {playing ? <Volume2 size={30} /> : <Play size={30} fill="currentColor" />}
            </button>
            <div>
              <h1>{playing ? '正在播放…' : '点击播放当前词语'}</h1>
              <p>播放内容不会在页面直接显示，请根据提示在纸上书写。</p>
            </div>
            <Button
              size="sm"
              icon={RotateCcw}
              onClick={() => offlineEntry && speakWord(offlineEntry.word)}
            >
              重播
            </Button>
          </div>
          <div className="dictation-hint-card">
            <span>
              {config.hint === 'phonetic'
                ? task.subject === 'english' ? '英语音标提示' : '语文拼音提示'
                : '中文释义提示'}
            </span>
            <strong>{hintFor(offlineEntry) || '暂无提示内容'}</strong>
          </div>
          {countdown !== null ? (
            <div className="auto-play-countdown">
              <Clock3 size={15} />
              {offlineIndex + 1 < task.snapshot.length
                ? `${countdown} 秒后自动播放下一个词`
                : `${countdown} 秒后进入自查核对`}
            </div>
          ) : null}
          <footer className="practice-card-footer offline-play-footer">
            <Button
              icon={ArrowLeft}
              disabled={offlineIndex === 0}
              onClick={() => setOfflineIndex((current) => Math.max(0, current - 1))}
            >
              上一个
            </Button>
            <div>
              <Button onClick={() => setOfflineReview(true)}>完成听写并核对</Button>
              <Button
                variant="primary"
                icon={ArrowRight}
                onClick={() => {
                  if (offlineIndex + 1 < task.snapshot.length) {
                    setOfflineIndex((current) => current + 1)
                  } else {
                    setOfflineReview(true)
                  }
                }}
              >
                {offlineIndex + 1 < task.snapshot.length ? '下一个词' : '进入核对'}
              </Button>
            </div>
          </footer>
        </section>
        <div className="practice-secondary-note">
          <Headphones size={14} />
          线下听写由用户完成纸面书写，并在页面提交自己的错误项
        </div>
      </PracticeLayout>
    )
  }

  if (!entry) {
    return (
      <PracticeLayout task={task} current={attempt.currentIndex} total={attempt.total} onExit={exit}>
        <div className="empty-state">
          <h3>没有更多题目</h3>
          <p>本次听写已经结束。</p>
        </div>
      </PracticeLayout>
    )
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

  return (
    <PracticeLayout task={task} current={activeIndex} total={attempt.total} onExit={exit} centered>
      <section className="dictation-practice-card">
        <div className="practice-question-meta">
          <Badge>线上听写</Badge>
          <span>
            {config.playbackMode === 'auto'
              ? `自动播放 · 每 ${config.intervalSeconds} 秒重播`
              : '手动播放 · 按需重播'}
          </span>
        </div>

        <div className="dictation-audio-area">
          <button type="button" className={`audio-play-button ${playing ? 'is-playing' : ''}`} onClick={() => speakWord(entry.word)}>
            {playing ? <Volume2 size={30} /> : <Play size={30} fill="currentColor" />}
          </button>
          <div>
            <h1>{playing ? '正在播放…' : '点击播放当前词语'}</h1>
            <p>可以重复播放，不会影响答题记录</p>
          </div>
          <Button size="sm" icon={RotateCcw} onClick={() => speakWord(entry.word)}>重播</Button>
        </div>

        <div className="dictation-hint-card">
          <span>
            {config.hint === 'phonetic'
              ? task.subject === 'english' ? '英语音标提示' : '语文拼音提示'
              : '中文释义提示'}
          </span>
          <strong>{hintFor(entry) || '暂无提示内容'}</strong>
        </div>

        {countdown !== null ? (
          <div className="auto-play-countdown">
            <Clock3 size={15} />
            {countdown} 秒后自动重播当前词语
          </div>
        ) : null}

        <div className="dictation-wave" aria-hidden="true">
          {Array.from({ length: 32 }, (_, index) => (
            <i key={index} style={{ height: `${12 + ((index * 13) % 28)}px` }} />
          ))}
        </div>

        <div className="dictation-answer-area">
          <label htmlFor="dictation-answer">输入你听到的词语</label>
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
            placeholder={task.subject === 'chinese' ? '输入汉字…' : 'Type the word…'}
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
              <span>正确答案</span>
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
