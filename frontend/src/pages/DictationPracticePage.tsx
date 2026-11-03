import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Headphones,
  ListChecks,
  Pause,
  Play,
  RotateCcw,
  Volume2,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { PracticeLayout } from '../features/practice/PracticeLayout'
import { Badge, Button, EmptyState, LoadingBlock } from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'
import type { DictationConfig, PracticeAttempt, WordEntry } from '../types/domain'
import { formatDuration } from '../utils/format'
import { cancelSpeech, isSpeechSupported, speakText } from '../utils/speech'

interface Feedback {
  given: string
  correct: boolean
  /** 本词当前连续拼对次数（强制答对模式下用来判断能不能进入下一题） */
  streak: number
  /** 是否已经过关，可以进入下一个词 */
  passed: boolean
}

const defaultDictationConfig: DictationConfig = {
  mode: 'online',
  playbackMode: 'manual',
  intervalSeconds: 8,
  hint: 'phonetic',
  repeatCount: 1,
  speechEnabled: true,
}

/** 线上听写答对后停留多久再自动进入下一题（毫秒） */
const AUTO_ADVANCE_DELAY_MS = 1000

/** 强制答对模式下，同一个词要连续拼对几次才算过关 */
const REQUIRED_CORRECT_STREAK = 2

/** 从最近一次作答往前数，某个词连续拼对的次数。 */
function streakFor(attempt: PracticeAttempt | null, target: WordEntry | undefined) {
  if (!attempt || !target) return 0
  let streak = 0
  for (let index = attempt.answers.length - 1; index >= 0; index -= 1) {
    const record = attempt.answers[index]
    // 老数据没有 snapshotEntryId，退化成用提示词比对。
    const matches = record.snapshotEntryId
      ? record.snapshotEntryId === target.id
      : record.prompt === target.word
    if (!matches || !record.correct) break
    streak += 1
  }
  return streak
}

export const DictationPracticePage = () => {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const isWrongPractice = location.pathname.endsWith('/wrong')
  const { tasks, currentUser, loadTask, refresh, showToast } = useAppStore()
  const task = tasks.find((candidate) => candidate.id === taskId)
  const taskDetailsReady = task?.snapshotIncluded !== false
  const config = task?.config.dictation ?? defaultDictationConfig
  const isOffline = config.mode === 'offline'
  const speechEnabled = config.speechEnabled !== false
  const repeatUntilCorrect = Boolean(task?.config.repeatUntilCorrect)
  // 错题复习仍是一次过一遍（两轮复习后移出错题池），只有任务勾了强制重做才要求连对。
  const requiresStreak = repeatUntilCorrect
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
  const [autoPaused, setAutoPaused] = useState(false)
  const [autoRound, setAutoRound] = useState(0)
  /** 同一个词重复练习时，用它触发重新朗读 */
  const [replayToken, setReplayToken] = useState(0)
  const [showResults, setShowResults] = useState(false)
  const [taskLoading, setTaskLoading] = useState(true)
  const [taskLoadError, setTaskLoadError] = useState('')
  const startedAtRef = useRef(performance.now())
  const autoAdvanceTimer = useRef<number | null>(null)
  const answerInputRef = useRef<HTMLInputElement>(null)
  const attemptRef = useRef<PracticeAttempt | null>(attempt)
  attemptRef.current = attempt
  const practiceEntries = useMemo(
    () =>
      task
        ? attempt?.kind === 'wrong'
          ? task.snapshot.filter((item) => attempt.targetEntryIds?.includes(item.id))
          : task.snapshot
        : [],
    [attempt, task],
  )
  const entry = practiceEntries[activeIndex]
  const offlineEntry = practiceEntries[offlineIndex]
  // 当前这个词已经连续拼对了几次（强制答对 / 错题复习用来提示还差几次）。
  const currentStreak = requiresStreak ? streakFor(attempt, entry) : 0
  const groupProgressFor = (target: WordEntry | undefined) => {
    if (!target || !task) return null
    const snapshotIndex = task.snapshot.findIndex((item) => item.id === target.id)
    if (snapshotIndex < 0) return null
    const groupSize = Math.max(task.config.wordsPerGroup, 1)
    const group = task.mode === 'fixed' ? 1 : Math.floor(snapshotIndex / groupSize) + 1
    const groupTotal =
      task.mode === 'fixed'
        ? 1
        : Math.max(Math.ceil(task.snapshot.length / groupSize), task.config.totalGroups)
    const current = (snapshotIndex % groupSize) + 1
    const total = Math.min(groupSize, task.snapshot.length - (group - 1) * groupSize)
    return { group, groupTotal, current, total }
  }
  const currentGroupProgress = groupProgressFor(entry)
  const offlineGroupProgress = groupProgressFor(offlineEntry)
  const currentGroupIndex = currentGroupProgress?.group ?? null
  const offlineGroupIndex = offlineGroupProgress?.group ?? null
  const wrongContextLabel = isWrongPractice
    ? currentGroupIndex
      ? `错题复习 · 第 ${currentGroupIndex} 组`
      : '错题复习'
    : undefined
  const answeredWrong = Boolean(feedback && !feedback.correct)
  // 英语听写的音标等于把答案拆成音节摆出来，只在答错后揭示；语文拼音不是答案本身，始终显示。
  const showPhonetic = task?.subject === 'chinese' || answeredWrong

  useEffect(() => {
    if (!taskId || !currentUser) {
      setTaskLoading(false)
      return
    }
    if (taskDetailsReady) {
      setTaskLoading(false)
      setTaskLoadError('')
      return
    }
    let cancelled = false
    setTaskLoading(true)
    void loadTask(taskId)
      .catch((cause) => {
        if (!cancelled) {
          setTaskLoadError(cause instanceof Error ? cause.message : '任务加载失败')
        }
      })
      .finally(() => {
        if (!cancelled) setTaskLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentUser, loadTask, taskDetailsReady, taskId])

  useEffect(() => {
    if (!taskId || !currentUser || !taskDetailsReady) {
      setAttempt(null)
      return
    }
    let cancelled = false
    const start = async () => {
      try {
        const nextAttempt = isWrongPractice
          ? await api.practice.startWrongAttempt(taskId, currentUser.id)
          : await api.practice.startOrResume(taskId, currentUser.id)
        if (cancelled) return
        setAttempt(nextAttempt)
        setActiveIndex(nextAttempt.currentIndex)
        setOfflineIndex(0)
        setOfflineReview(false)
        setWrongEntryIds([])
        setShowResults(false)
        setFeedback(null)
        setAnswer('')
        setAutoPaused(false)
        setAutoRound(0)
        startedAtRef.current = performance.now()
      } catch (cause) {
        if (!cancelled) showToast(cause instanceof Error ? cause.message : '练习加载失败', 'danger')
      }
    }
    void start()
    return () => {
      cancelled = true
    }
  }, [taskId, currentUser, taskDetailsReady, isWrongPractice, showToast])

  const clearAutoAdvance = useCallback(() => {
    if (autoAdvanceTimer.current !== null) {
      window.clearTimeout(autoAdvanceTimer.current)
      autoAdvanceTimer.current = null
    }
  }, [])

  const speakEntry = useCallback(
    (target: WordEntry | undefined) => {
      if (!target) return
      if (!isSpeechSupported()) {
        showToast('当前浏览器不支持语音合成，请使用支持 Web Speech 的浏览器', 'danger')
        return
      }
      const isChinese = task?.subject === 'chinese'
      // 英语听写要读的是单词本身；音标是一串 IPA 符号，交给语音合成只会被逐字符念成乱码。
      const readingText = isChinese
        ? target.word
        : config.hint === 'meaning'
          ? target.meanings.join('；') || target.word
          : target.word
      const lang = config.hint === 'meaning' || isChinese ? 'zh' : 'en'
      void speakText(readingText, {
        lang,
        rate: lang === 'zh' ? 0.86 : 0.82,
        repeat: config.repeatCount,
        onStart: () => setPlaying(true),
        onFinish: () => setPlaying(false),
      })
    },
    [config.hint, config.repeatCount, showToast, task?.subject],
  )

  const toggleAutoPause = useCallback(() => {
    if (!autoPaused) {
      cancelSpeech()
      setPlaying(false)
    }
    setAutoPaused(!autoPaused)
  }, [autoPaused])

  // 进入词语即发音，手动模式也不用先点播放按钮。
  // 自动模式在这里额外负责倒计时：时间到就进入下一个词，而不是重播当前词。
  useEffect(() => {
    if (!task || !attempt || isOffline || showResults || feedback || !entry) {
      setCountdown(null)
      return
    }
    if (!speechEnabled || autoPaused) {
      setCountdown(null)
      return
    }
    speakEntry(entry)
    if (config.playbackMode !== 'auto' || requiresStreak) {
      // 强制答对模式下不能到点就换词，否则等于没答对也能过；这里只负责进词发音。
      setCountdown(null)
      return
    }
    let remaining = Math.max(2, config.intervalSeconds)
    setCountdown(remaining)
    const timer = window.setInterval(() => {
      remaining -= 1
      if (remaining <= 0) {
        window.clearInterval(timer)
        if (activeIndex + 1 < practiceEntries.length) {
          setActiveIndex(activeIndex + 1)
        } else {
          // 播到最后一个词后回到第一个未作答的词，避免自动播放停在结尾不动。
          setActiveIndex(attemptRef.current?.currentIndex ?? 0)
          setAutoRound((round) => round + 1)
        }
        return
      }
      setCountdown(remaining)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [
    activeIndex,
    attempt?.id,
    autoPaused,
    autoRound,
    config.intervalSeconds,
    config.playbackMode,
    entry?.id,
    feedback,
    isOffline,
    practiceEntries.length,
    replayToken,
    requiresStreak,
    showResults,
    speakEntry,
    speechEnabled,
    task?.id,
  ])

  // 线下听写同样进入词语即发音，自动模式下时间到进入下一个词。
  useEffect(() => {
    if (!task || !attempt || !isOffline || offlineReview || showResults || !offlineEntry) {
      setCountdown(null)
      return
    }
    if (!speechEnabled || autoPaused) {
      setCountdown(null)
      return
    }
    speakEntry(offlineEntry)
    if (config.playbackMode !== 'auto') {
      setCountdown(null)
      return
    }
    let remaining = Math.max(2, config.intervalSeconds)
    setCountdown(remaining)
    const timer = window.setInterval(() => {
      remaining -= 1
      if (remaining <= 0) {
        if (offlineIndex + 1 < practiceEntries.length) {
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
    autoPaused,
    config.intervalSeconds,
    config.playbackMode,
    isOffline,
    offlineEntry?.id,
    offlineIndex,
    offlineReview,
    practiceEntries.length,
    showResults,
    speakEntry,
    speechEnabled,
    task?.id,
  ])

  useEffect(
    () => () => {
      clearAutoAdvance()
      cancelSpeech()
    },
    [clearAutoAdvance],
  )

  // 换题或反馈消失后把焦点还给输入框，自动进入下一题时不用再点一下。
  useEffect(() => {
    if (!feedback && !showResults && entry) answerInputRef.current?.focus()
  }, [activeIndex, entry, feedback, showResults])

  if (!currentUser) return null

  if (taskLoading) {
    return (
      <div className="practice-shell">
        <main className="practice-main practice-centered">
          <LoadingBlock label="正在加载听写任务" />
        </main>
      </div>
    )
  }

  if (!task || !taskDetailsReady || taskLoadError) {
    return (
      <div className="practice-shell">
        <main className="practice-main practice-centered">
          <EmptyState
            icon={Headphones}
            title="无法开始听写"
            description={taskLoadError || '任务不存在，或当前账户无权访问。'}
            action={<Link className="button button-primary button-md" to="/tasks">返回任务列表</Link>}
          />
        </main>
      </div>
    )
  }

  if (!attempt) {
    return (
      <div className="practice-shell">
        <main className="practice-main practice-centered">
          <LoadingBlock label="正在准备听写" />
        </main>
      </div>
    )
  }



  if (showResults) {
    const accuracy = attempt.total ? Math.round((attempt.score / attempt.total) * 100) : 0
    const wrongAnswers = attempt.answers.filter((item) => !item.correct)
    const totalDuration = attempt.answers.reduce((sum, item) => sum + item.durationMs, 0)
    return (
      <div className="practice-shell">
        <main className="practice-main practice-result-page">
          <section className="practice-result-card">
            <span className="result-kicker">{isWrongPractice ? '错题复习完成' : '听写完成'}</span>
            <h1>
              {isWrongPractice
                ? '本次错题练习结果已保存'
                : isOffline
                  ? '线下听写自查已提交'
                  : '听写结果已保存'}
            </h1>
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
    api.practice.saveExit(attempt.id)
    navigate(`/tasks/${task.id}`)
  }

  if (isOffline) {
    const submitOffline = async () => {
      setBusy(true)
      try {
        const result = await api.practice.submitOfflineAttempt(
          task.id,
          currentUser.id,
          wrongEntryIds,
          isWrongPractice ? 'wrong' : 'regular',
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
          current={practiceEntries.length}
          total={attempt.total}
          onExit={exit}
          centered
          contextLabel={isWrongPractice ? '错题复习' : undefined}
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
                <p>共 {practiceEntries.length} 个词语，已标记 {wrongEntryIds.length} 个错误。</p>
              </div>
            </div>
            <div className="offline-review-list">
              {practiceEntries.map((word, index) => (
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
        total={practiceEntries.length}
        onExit={exit}
        centered
        groupProgress={offlineGroupProgress}
        contextLabel={
          isWrongPractice && offlineGroupIndex
            ? `错题复习 · 第 ${offlineGroupIndex} 组`
            : wrongContextLabel
        }
      >
        <section className="dictation-practice-card">
          <div className="practice-question-meta">
            <Badge>线下听写</Badge>
            <span>
              {speechEnabled ? '在纸上完成听写，全部播放后进入自查核对。' : '不朗读模式：按页面提示自行默写，完成后进入自查核对。'}
            </span>
          </div>
          <div className="offline-dictation-progress">
            <span>当前第 {offlineIndex + 1} / {practiceEntries.length} 个词</span>
            <Badge tone={speechEnabled && config.playbackMode === 'auto' ? 'info' : 'neutral'}>
              {!speechEnabled
                ? '不朗读'
                : config.playbackMode === 'auto'
                  ? `自动播放 · ${config.intervalSeconds} 秒 · 朗读 ${config.repeatCount} 次`
                  : `手动播放 · 朗读 ${config.repeatCount} 次`}
            </Badge>
          </div>
          {speechEnabled ? (
            <div className="dictation-audio-area offline-audio-area">
              <button
                type="button"
                className={`audio-play-button ${playing ? 'is-playing' : ''}`}
                onClick={() => offlineEntry && speakEntry(offlineEntry)}
              >
                {playing ? <Volume2 size={30} /> : <Play size={30} fill="currentColor" />}
              </button>
              <div>
                <h1>{playing ? '正在播放…' : '进入词语后自动朗读'}</h1>
                <p>播放内容不会在页面直接显示，请根据提示在纸上书写。</p>
              </div>
              <Button
                size="sm"
                icon={RotateCcw}
                onClick={() => offlineEntry && speakEntry(offlineEntry)}
              >
                重播
              </Button>
            </div>
          ) : null}
          <div className="dictation-hint-card">
            <span>
              {speechEnabled
                ? `朗读内容：${
                    task.subject === 'chinese'
                      ? '词语发音（直接读出）'
                      : config.hint === 'phonetic'
                        ? '英语单词'
                        : '中文含义'
                  }`
                : '页面提示'}
            </span>
            <div className={`dictation-hint-values ${showPhonetic ? '' : 'is-single'}`}>
              {showPhonetic ? (
                <div>
                  <small>{task.subject === 'english' ? '英语音标' : '语文拼音'}</small>
                  <strong>{offlineEntry?.phonetic || '暂无'}</strong>
                </div>
              ) : null}
              <div>
                <small>中文含义</small>
                <strong>{offlineEntry?.meanings.join('；') || '暂无'}</strong>
              </div>
            </div>
          </div>
          {speechEnabled && config.playbackMode === 'auto' ? (
            <div className={`auto-play-countdown ${autoPaused ? 'is-paused' : ''}`}>
              {autoPaused ? <Pause size={15} /> : <Clock3 size={15} />}
              <span>
                {autoPaused
                  ? '自动播放已暂停'
                  : offlineIndex + 1 < practiceEntries.length
                    ? `${countdown ?? config.intervalSeconds} 秒后自动播放下一个词`
                    : `${countdown ?? config.intervalSeconds} 秒后进入自查核对`}
              </span>
              <button type="button" className="auto-play-toggle" onClick={toggleAutoPause}>
                {autoPaused ? '继续自动播放' : '暂停自动播放'}
              </button>
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
                  if (offlineIndex + 1 < practiceEntries.length) {
                    setOfflineIndex((current) => current + 1)
                  } else {
                    setOfflineReview(true)
                  }
                }}
              >
                {offlineIndex + 1 < practiceEntries.length ? '下一个词' : '进入核对'}
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
      <PracticeLayout
        task={task}
        current={attempt.currentIndex}
        total={attempt.total}
        onExit={exit}
        contextLabel={wrongContextLabel}
      >
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
      const result = await api.practice.submitAnswer(task.id, currentUser.id, {
        prompt: entry.word,
        expected: entry.word,
        given: answer,
        durationMs: Math.round(performance.now() - startedAtRef.current),
      }, isWrongPractice ? 'wrong' : 'regular')
      setAttempt(result.attempt)
      const streak = streakFor(result.attempt, entry)
      // 强制答对模式下，只有连续拼对两次才算过关；普通模式答错也放行到下一个词。
      const passed = !requiresStreak || (result.isCorrect && streak >= REQUIRED_CORRECT_STREAK)
      setFeedback({ given: answer.trim(), correct: result.isCorrect, streak, passed })
      clearAutoAdvance()
      // 只有答对且过关才自动继续；其余情况停在原地，等用户点按钮。
      if (passed && result.isCorrect) {
        autoAdvanceTimer.current = window.setTimeout(
          () => advanceTo(result.attempt),
          AUTO_ADVANCE_DELAY_MS,
        )
      }
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '提交失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const advanceTo = (source: PracticeAttempt) => {
    clearAutoAdvance()
    if (source.status === 'completed') {
      setShowResults(true)
      return
    }
    setActiveIndex(source.currentIndex)
    setAnswer('')
    setFeedback(null)
    setReplayToken((token) => token + 1)
    startedAtRef.current = performance.now()
  }

  // 本词还没连对够次数：清空反馈重新拼同一个词，并重新朗读一遍。
  const retryCurrent = () => {
    clearAutoAdvance()
    setAnswer('')
    setFeedback(null)
    setReplayToken((token) => token + 1)
    startedAtRef.current = performance.now()
  }

  const advance = () => advanceTo(attempt)

  return (
      <PracticeLayout
        task={task}
        current={activeIndex}
        total={attempt.total}
        onExit={exit}
        centered
        groupProgress={currentGroupProgress}
        contextLabel={isWrongPractice ? '错题复习' : undefined}
      >
      <section className="dictation-practice-card">
        <div className="practice-question-meta">
          <Badge>
            {isWrongPractice
              ? `错题练习${currentGroupIndex ? ` · 第 ${currentGroupIndex} 组` : ''} · `
              : ''}
            线上听写
          </Badge>
          <span>
            {requiresStreak
              ? `答对才能进下一题 · 每词连续拼对 ${REQUIRED_CORRECT_STREAK} 次${speechEnabled ? ` · 每次朗读 ${config.repeatCount} 次` : ' · 不朗读'}`
              : !speechEnabled
                ? '不朗读 · 按提示自行拼写'
                : config.playbackMode === 'auto'
                  ? `自动播放 · 每 ${config.intervalSeconds} 秒进入下一个词 · 每次朗读 ${config.repeatCount} 次`
                  : `手动播放 · 进入词语自动朗读 ${config.repeatCount} 次`}
          </span>
        </div>

        {requiresStreak && currentStreak > 0 && !feedback ? (
          <div className="practice-streak-note">
            <ListChecks size={15} />
            本词已连续拼对 {currentStreak} 次，再拼对 {REQUIRED_CORRECT_STREAK - currentStreak} 次进入下一个词
          </div>
        ) : null}

        {speechEnabled ? (
          <div className="dictation-audio-area">
            <button type="button" className={`audio-play-button ${playing ? 'is-playing' : ''}`} onClick={() => speakEntry(entry)}>
              {playing ? <Volume2 size={30} /> : <Play size={30} fill="currentColor" />}
            </button>
            <div>
              <h1>{playing ? '正在播放…' : '进入词语后自动朗读'}</h1>
              <p>按任务设置朗读单词或中文含义，页面同时显示音标和中文含义</p>
            </div>
            <Button size="sm" icon={RotateCcw} onClick={() => speakEntry(entry)}>重播</Button>
          </div>
        ) : null}

        <div className="dictation-hint-card">
          <span>
            {speechEnabled
              ? `朗读内容：${
                  config.hint === 'phonetic'
                    ? task.subject === 'english'
                      ? '英语单词'
                      : '语文拼音'
                    : '中文含义'
                }`
              : '页面提示'}
          </span>
          <div className={`dictation-hint-values ${showPhonetic ? '' : 'is-single'}`}>
            {showPhonetic ? (
              <div>
                <small>{task.subject === 'english' ? '英语音标' : '语文拼音'}</small>
                <strong>{entry.phonetic || '暂无'}</strong>
              </div>
            ) : null}
            <div>
              <small>中文含义</small>
              <strong>{entry.meanings.join('；') || '暂无'}</strong>
            </div>
          </div>
        </div>

        {speechEnabled && config.playbackMode === 'auto' && !requiresStreak ? (
          <div className={`auto-play-countdown ${autoPaused ? 'is-paused' : ''}`}>
            {autoPaused ? <Pause size={15} /> : <Clock3 size={15} />}
            <span>
              {autoPaused
                ? '自动播放已暂停'
                : activeIndex + 1 < practiceEntries.length
                  ? `${countdown ?? config.intervalSeconds} 秒后自动播放下一个词`
                  : `${countdown ?? config.intervalSeconds} 秒后回到第一个未作答的词`}
            </span>
            <button type="button" className="auto-play-toggle" onClick={toggleAutoPause}>
              {autoPaused ? '继续自动播放' : '暂停自动播放'}
            </button>
          </div>
        ) : null}

        <div className="dictation-answer-area">
          <label htmlFor="dictation-answer">
            {speechEnabled ? '输入你听到的词语' : '输入这个词的拼写'}
          </label>
          <input
            id="dictation-answer"
            ref={answerInputRef}
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submit()
            }}
            disabled={Boolean(feedback) || busy}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
          />
        </div>

        {feedback ? (
          <div className={`answer-feedback ${feedback.correct ? 'feedback-correct' : 'feedback-wrong'}`}>
            <div className="feedback-heading">
              {feedback.correct ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              <strong>
                {feedback.correct
                  ? feedback.passed
                    ? '拼写正确'
                    : '拼写正确 · 还要再拼一次'
                  : '拼写需要修正'}
              </strong>
            </div>
            <div className="dictation-answer-reveal">
              <span>正确答案</span>
              <strong>{entry.word}</strong>
              <small>
                {showPhonetic ? `${entry.phonetic} · ` : ''}
                {entry.meanings.join('；')}
              </small>
            </div>
            {!feedback.correct ? (
              <div className="feedback-answer-row">
                <p>你的答案：{feedback.given}</p>
                {/* 英语答错后才给出音标，此时也允许直接听一遍正确读音。 */}
                <Button size="sm" icon={Volume2} onClick={() => speakEntry(entry)}>
                  朗读
                </Button>
              </div>
            ) : null}
            {requiresStreak ? (
              <p className="feedback-streak">
                {feedback.passed
                  ? `本词已连续拼对 ${feedback.streak} 次，过关`
                  : `本词连续拼对 ${feedback.streak}/${REQUIRED_CORRECT_STREAK} 次，再拼对 ${
                      REQUIRED_CORRECT_STREAK - feedback.streak
                    } 次才能进入下一个词`}
              </p>
            ) : null}
            <blockquote>
              {entry.example}
              <small>{entry.exampleTranslation}</small>
            </blockquote>
          </div>
        ) : null}

        <footer className="practice-card-footer">
          <span className="practice-hint">
            {feedback
              ? feedback.passed
                ? feedback.correct
                  ? `答对了，${AUTO_ADVANCE_DELAY_MS / 1000} 秒后自动继续`
                  : '本题已保存，可继续下一题'
                : `本词还没连对 ${REQUIRED_CORRECT_STREAK} 次，继续拼这个词`
              : '按 Enter 也可以提交'}
          </span>
          {feedback ? (
            <Button
              variant="primary"
              icon={feedback.passed ? ArrowRight : RotateCcw}
              onClick={feedback.passed ? advance : retryCurrent}
            >
              {feedback.passed
                ? attempt.status === 'completed'
                  ? '查看听写结果'
                  : '下一题'
                : '再拼一次'}
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
