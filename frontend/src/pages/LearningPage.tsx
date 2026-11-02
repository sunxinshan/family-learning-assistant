import {
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  Headphones,
  RotateCcw,
  Target,
  TrendingUp,
  TriangleAlert,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Badge, EmptyState, PageHeader, ProgressBar } from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'
import { formatDateTime, practicePath, taskTypeLabel } from '../utils/format'

type Filter = 'all' | 'dictation'

export const LearningPage = () => {
  const { currentUser, practices, tasks } = useAppStore()
  const [filter, setFilter] = useState<Filter>('all')

  const stats = useMemo(
    () => (currentUser ? api.learning.getStats(currentUser.id) : null),
    [currentUser, practices],
  )

  const attemptById = useMemo(
    () => new Map(practices.map((attempt) => [attempt.id, attempt])),
    [practices],
  )

  const answerAttemptMap = useMemo(() => {
    const map = new Map<string, string>()
    practices.forEach((attempt) => {
      attempt.answers.forEach((answer) => map.set(answer.id, attempt.id))
    })
    return map
  }, [practices])

  const recentAttempts = useMemo(
    () =>
      stats?.recentAttempts.filter(
        (attempt) => filter === 'all' || attempt.taskType === filter,
      ) ?? [],
    [stats, filter],
  )
  const wrongAnswers = useMemo(
    () =>
      stats?.wrongAnswers.filter((answer) => {
        if (filter === 'all') return true
        const attemptId = answerAttemptMap.get(answer.id)
        return attemptById.get(attemptId ?? '')?.taskType === filter
      }) ?? [],
    [stats, filter, answerAttemptMap, attemptById],
  )

  if (!currentUser || !stats) return null

  const hasAnyActivity = stats.practiceCount > 0 || practices.length > 0

  return (
    <main className="page-container learning-page">
      <PageHeader
        eyebrow="学习反馈"
        title="学习记录"
        description="从答题事实汇总正确率、掌握情况和待复习内容。数据随练习提交自动更新。"
        actions={
          <Link to="/tasks" className="button button-secondary button-md">
            <Headphones size={16} />
            查看学习任务
          </Link>
        }
      />

      <section className="metric-grid" aria-label="学习指标">
        <article className="metric-card">
          <span className="metric-icon"><BarChart3 size={18} /></span>
          <div>
            <span>练习次数</span>
            <strong>{stats.practiceCount}</strong>
            <small>已完成的独立 Attempt</small>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon"><Target size={18} /></span>
          <div>
            <span>平均正确率</span>
            <strong>{stats.averageAccuracy}%</strong>
            <small>基于全部答题事实</small>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon"><CheckCircle2 size={18} /></span>
          <div>
            <span>已掌握词数</span>
            <strong>{stats.masteredCount}</strong>
            <small>最近一次作答正确</small>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon metric-icon-warning"><RotateCcw size={18} /></span>
          <div>
            <span>待复习错题</span>
            <strong>{stats.reviewCount}</strong>
            <small>最近一次作答错误</small>
          </div>
        </article>
      </section>

      {!hasAnyActivity ? (
        <EmptyState
          icon={BarChart3}
          title="还没有学习记录"
          description="完成一次词汇或听写练习后，这里会显示正确率、最近记录和错题。"
          action={<Link className="button button-primary button-md" to="/tasks">开始练习</Link>}
        />
      ) : (
        <>
          <div className="learning-grid">
            <section className="panel activity-panel">
              <div className="panel-header">
                <div>
                  <h2>最近 7 天练习</h2>
                  <p>柱高表示每日完成的练习次数。</p>
                </div>
                <Badge tone="info">从答题事实计算</Badge>
              </div>
              <div className="weekly-chart">
                {stats.weeklyActivity.map((day) => (
                  <div className="weekly-column" key={day.label}>
                    <div className="weekly-value">{day.count}</div>
                    <div className="weekly-track">
                      <div style={{ height: `${Math.max(8, day.count * 32)}px` }} />
                    </div>
                    <span>{day.label}</span>
                    <small>{day.count ? `${day.accuracy}%` : '—'}</small>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel accuracy-panel">
              <div className="panel-header">
                <div>
                  <h2>分项正确率</h2>
                  <p>正确率完全从听写答题事实计算，不进行手工修改。</p>
                </div>
              </div>
              <div className="accuracy-item">
                <div className="accuracy-label">
                  <span><Headphones size={15} />听写练习</span>
                  <strong>{stats.dictationAccuracy}%</strong>
                </div>
                <ProgressBar value={stats.dictationAccuracy} compact />
              </div>
              <div className="accuracy-note">
                <TrendingUp size={15} />
                掌握状态由答题数据计算，不支持手动修改。
              </div>
            </section>
          </div>

          <div className="list-toolbar learning-toolbar">
            <div className="filter-group">
              {([
                ['all', '全部'],
                ['dictation', '听写'],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={filter === value ? 'active' : ''}
                  onClick={() => setFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="toolbar-count">当前筛选下的记录与错题</span>
          </div>

          <div className="learning-grid learning-bottom-grid">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>最近练习</h2>
                  <p>每次练习都是独立 Attempt。</p>
                </div>
              </div>
              <div className="recent-practice-list">
                {recentAttempts.length ? (
                  recentAttempts.map((attempt) => {
                    const task = tasks.find((candidate) => candidate.id === attempt.taskId)
                    const accuracy = Math.round((attempt.score / attempt.total) * 100)
                    return (
                      <div className="recent-practice-row" key={attempt.id}>
                        <span className={`recent-practice-icon recent-${attempt.taskType}`}>
                          <Headphones size={16} />
                        </span>
                        <div className="recent-practice-main">
                          <strong>{task?.name ?? '已删除任务'}</strong>
                          <span>
                            {taskTypeLabel(attempt.taskType)} · {formatDateTime(attempt.completedAt ?? attempt.updatedAt)}
                          </span>
                        </div>
                        <div className="recent-practice-score">
                          <strong>{accuracy}%</strong>
                          <span>{attempt.score}/{attempt.total}</span>
                        </div>
                        {task ? (
                          <Link className="icon-button icon-button-sm" to={practicePath(task)} aria-label="再练一次">
                            <RotateCcw size={14} />
                          </Link>
                        ) : null}
                      </div>
                    )
                  })
                ) : (
                  <p className="muted-copy">当前筛选下没有已完成练习。</p>
                )}
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>待复习错题</h2>
                  <p>展示最近一次作答仍然错误的词条。</p>
                </div>
                {wrongAnswers.length ? <Badge tone="warning">{wrongAnswers.length} 项</Badge> : null}
              </div>
              <div className="wrong-list">
                {wrongAnswers.length ? (
                  wrongAnswers.map((answer) => {
                    const attemptId = answerAttemptMap.get(answer.id)
                    const attempt = attemptById.get(attemptId ?? '')
                    const task = tasks.find((candidate) => candidate.id === attempt?.taskId)
                    return (
                      <div className="wrong-row" key={answer.id}>
                        <span className="wrong-icon"><TriangleAlert size={15} /></span>
                        <div>
                          <strong>{answer.prompt}</strong>
                          <p>{answer.expected}</p>
                          <small>你的答案：{answer.given}</small>
                        </div>
                        {task ? (
                          <Link to={practicePath(task)} aria-label={`进入${task.name}`}>
                            <ArrowUpRight size={15} />
                          </Link>
                        ) : null}
                      </div>
                    )
                  })
                ) : (
                  <div className="empty-inline">
                    <CheckCircle2 size={18} />
                    当前没有需要复习的错题
                  </div>
                )}
              </div>
            </section>
          </div>
        </>
      )}
    </main>
  )
}
