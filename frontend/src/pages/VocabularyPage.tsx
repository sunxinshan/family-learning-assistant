import {
  ArrowRight,
  BookCopy,
  BookOpenText,
  Download,
  LibraryBig,
  Plus,
  Search,
  Sparkles,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { vocabularyApi } from '../api/mockApi'
import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
} from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'
import type { Subject, Vocabulary } from '../types/domain'
import { formatShortDate } from '../utils/format'

type Tab = 'personal' | 'public'

const LibraryCard = ({
  library,
  publicView,
  onCopy,
  copying,
}: {
  library: Vocabulary
  publicView: boolean
  onCopy?: (library: Vocabulary) => void
  copying?: boolean
}) => (
  <article className="library-card">
    <div className="library-card-top">
      <span className={`library-icon ${publicView ? 'library-icon-public' : ''}`}>
        {publicView ? <LibraryBig size={19} /> : <BookOpenText size={19} />}
      </span>
      <div className="library-card-badges">
        <Badge tone="info">{library.subject === 'english' ? '英语' : '语文'}</Badge>
        {publicView ? (
          <Badge tone={library.published ? 'success' : 'warning'}>
            {library.published ? '已发布' : '草稿'}
          </Badge>
        ) : (
          <Badge>{library.entries.length} 个词条</Badge>
        )}
      </div>
    </div>
    <div className="library-card-content">
      <h3>{library.name}</h3>
      <p>{library.description || '暂无描述'}</p>
    </div>
    <div className="library-chip-row">
      {library.tags.slice(0, 2).map((tag) => (
        <span key={tag}>{tag}</span>
      ))}
    </div>
    <div className="library-card-footer">
      <span>
        {publicView ? `${library.entries.length} 个词条` : `更新于 ${formatShortDate(library.updatedAt)}`}
      </span>
      {publicView ? (
        <div className="library-card-footer-actions">
          <Link to={`/vocabulary/${library.id}`} className="library-open-link">
            预览
            <ArrowRight size={14} />
          </Link>
          <Button
            size="sm"
            icon={Download}
            loading={copying}
            onClick={() => onCopy?.(library)}
            disabled={!library.published}
          >
            复制
          </Button>
        </div>
      ) : (
        <Link to={`/vocabulary/${library.id}`} className="library-open-link">
          查看词库
          <ArrowRight size={14} />
        </Link>
      )}
    </div>
  </article>
)

export const VocabularyPage = () => {
  const { libraries, publicLibraries, currentUser, refresh, showToast } = useAppStore()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('personal')
  const [query, setQuery] = useState('')
  const [subject, setSubject] = useState<'all' | Subject>('all')
  const [copyingId, setCopyingId] = useState<string | null>(null)

  const source = tab === 'personal' ? libraries : publicLibraries
  const filtered = useMemo(
    () =>
      source.filter((library) => {
        if (subject !== 'all' && library.subject !== subject) return false
        return `${library.name} ${library.description} ${library.category} ${library.tags.join(' ')}`
          .toLowerCase()
          .includes(query.toLowerCase())
      }),
    [source, query, subject],
  )

  const handleCopy = async (library: Vocabulary) => {
    if (!currentUser) return
    setCopyingId(library.id)
    try {
      const copy = await vocabularyApi.copy(currentUser.id, library.id)
      refresh()
      showToast('已复制为独立个人词库', 'success')
      navigate(`/vocabulary/${copy.id}`)
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '复制失败', 'danger')
    } finally {
      setCopyingId(null)
    }
  }

  return (
    <main className="page-container vocabulary-page">
      <PageHeader
        eyebrow="学习内容"
        title="词库"
        description="管理独立个人词库，或从公共词库复制一份可自由编辑的副本。"
        actions={
          <>
            <Link to="/" className="button button-secondary button-md">
              <Sparkles size={16} />
              从 Agent 整理
            </Link>
            <Link className="button button-primary button-md" to="/vocabulary/new">
              <Plus size={16} />
              新建词库
            </Link>
          </>
        }
      />

      <div className="section-tabs-row">
        <div className="section-tabs" role="tablist" aria-label="词库类型">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'personal'}
            className={tab === 'personal' ? 'active' : ''}
            onClick={() => setTab('personal')}
          >
            我的词库
            <span>{libraries.length}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'public'}
            className={tab === 'public' ? 'active' : ''}
            onClick={() => setTab('public')}
          >
            公共词库
            <span>{publicLibraries.filter((library) => library.published).length}</span>
          </button>
        </div>
        <div className="toolbar-right">
          <div className="compact-select-wrap">
            <select
              aria-label="按学科筛选词库"
              value={subject}
              onChange={(event) => setSubject(event.target.value as 'all' | Subject)}
            >
              <option value="all">全部学科</option>
              <option value="english">英语</option>
              <option value="chinese">语文</option>
            </select>
          </div>
          <div className="search-field">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索名称、学科或标签"
              aria-label="搜索词库"
            />
          </div>
        </div>
      </div>

      {tab === 'public' ? (
        <div className="public-note">
          <BookCopy size={15} />
          公共词库复制后会生成完全独立的个人副本，原词库后续更新不会影响副本。
        </div>
      ) : null}

      <section className="library-grid">
        {filtered.length ? (
          filtered.map((library) => (
            <LibraryCard
              key={library.id}
              library={library}
              publicView={tab === 'public'}
              onCopy={(item) => void handleCopy(item)}
              copying={copyingId === library.id}
            />
          ))
        ) : (
          <div className="full-span">
            <EmptyState
              icon={LibraryBig}
              title={query ? '没有匹配的词库' : tab === 'personal' ? '还没有个人词库' : '暂无公共词库'}
              description={
                query
                  ? '尝试更换关键词。'
                  : tab === 'personal'
                    ? '可以新建空词库、从 Agent 导入，或复制一个公共词库。'
                    : '管理员发布公共词库后会显示在这里。'
              }
              action={
                !query && tab === 'personal' ? (
                  <Link className="button button-primary button-md" to="/vocabulary/new">
                    <Plus size={16} />
                    新建个人词库
                  </Link>
                ) : undefined
              }
            />
          </div>
        )}
      </section>
    </main>
  )
}
