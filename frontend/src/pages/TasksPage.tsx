import { MessageSquarePlus, Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, EmptyState, PageHeader } from '../components/ui'
import { TaskCard } from '../features/task/TaskCard'
import { useAppStore } from '../stores/AppStoreContext'
import type { TaskStatus, TaskType } from '../types/domain'

type StatusFilter = 'all' | TaskStatus
type TypeFilter = 'all' | TaskType

export const TasksPage = () => {
  const { tasks } = useAppStore()
  const [status, setStatus] = useState<StatusFilter>('all')
  const [type, setType] = useState<TypeFilter>('all')
  const [query, setQuery] = useState('')

  const filtered = useMemo(
    () =>
      tasks.filter((task) => {
        if (status !== 'all' && task.status !== status) return false
        if (type !== 'all' && task.type !== type) return false
        if (query && !`${task.name} ${task.libraryName}`.toLowerCase().includes(query.toLowerCase())) {
          return false
        }
        return true
      }),
    [tasks, status, type, query],
  )

  const inProgress = tasks.filter((task) => task.status === 'in_progress').length
  const completed = tasks.filter((task) => task.status === 'completed').length

  return (
    <main className="page-container tasks-page">
      <PageHeader
        eyebrow="学习计划"
        title="学习任务"
        description="从任务进入独立练习页面，继续未完成的进度或回顾已完成内容。"
        actions={
          <>
            <Link className="button button-primary button-md" to="/tasks/new">
              <Plus size={16} />
              页面创建
            </Link>
            <Link className="button button-secondary button-md" to="/">
              <MessageSquarePlus size={16} />
              通过 Agent 创建
            </Link>
          </>
        }
      />

      <section className="page-summary-strip" aria-label="任务概况">
        <div>
          <span>全部任务</span>
          <strong>{tasks.length}</strong>
        </div>
        <div>
          <span>进行中</span>
          <strong>{inProgress}</strong>
        </div>
        <div>
          <span>已完成</span>
          <strong>{completed}</strong>
        </div>
        <div className="summary-strip-note">任务状态只有进行中与已完成，不设置暂停状态。</div>
      </section>

      <div className="list-toolbar">
        <div className="filter-group" aria-label="任务状态筛选">
          {([
            ['all', '全部'],
            ['in_progress', '进行中'],
            ['completed', '已完成'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={status === value ? 'active' : ''}
              onClick={() => setStatus(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <div className="compact-select-wrap">
            <select
              aria-label="学习类型筛选"
              value={type}
              onChange={(event) => setType(event.target.value as TypeFilter)}
            >
              <option value="all">全部类型</option>
              <option value="dictation">听写练习</option>
            </select>
          </div>
          <div className="search-field compact-search">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索任务或词库"
              aria-label="搜索任务"
            />
          </div>
        </div>
      </div>

      <section className="task-list">
        {filtered.length ? (
          filtered.map((task) => <TaskCard key={task.id} task={task} />)
        ) : (
          <EmptyState
            icon={MessageSquarePlus}
            title="没有匹配的任务"
            description="调整筛选条件，或回到学习助手通过自然语言创建新任务。"
            action={
              <div className="empty-actions">
                <Button
                  onClick={() => {
                    setStatus('all')
                    setType('all')
                    setQuery('')
                  }}
                >
                  清除筛选
                </Button>
                <Link className="button button-primary button-md" to="/tasks/new">
                  页面创建任务
                </Link>
              </div>
            }
          />
        )}
      </section>
    </main>
  )
}
