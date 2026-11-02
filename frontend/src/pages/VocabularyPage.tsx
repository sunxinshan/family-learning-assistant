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
  Field,
  InlineError,
  Modal,
  PageHeader,
  TextInput,
} from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import type { Vocabulary } from '../types/domain'
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
      <span>{library.category}</span>
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
  const [createOpen, setCreateOpen] = useState(false)
  const [copyingId, setCopyingId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState({ name: '', description: '', category: '' })

  const source = tab === 'personal' ? libraries : publicLibraries
  const filtered = useMemo(
    () =>
      source.filter((library) =>
        `${library.name} ${library.description} ${library.category} ${library.tags.join(' ')}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [source, query],
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

  const createLibrary = async () => {
    if (!currentUser) return
    if (!draft.name.trim()) {
      setError('请输入词库名称')
      return
    }
    setBusy(true)
    setError('')
    try {
      const library = await vocabularyApi.create(currentUser.id, {
        name: draft.name,
        description: draft.description,
        category: draft.category,
        tags: [],
        entries: [],
      })
      refresh()
      setCreateOpen(false)
      setDraft({ name: '', description: '', category: '' })
      showToast('个人词库已创建', 'success')
      navigate(`/vocabulary/${library.id}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '创建失败')
    } finally {
      setBusy(false)
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
            <Button variant="primary" icon={Plus} onClick={() => setCreateOpen(true)}>
              新建词库
            </Button>
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
        <div className="search-field">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索名称、分类或标签"
            aria-label="搜索词库"
          />
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
                  <Button variant="primary" icon={Plus} onClick={() => setCreateOpen(true)}>
                    新建个人词库
                  </Button>
                ) : undefined
              }
            />
          </div>
        )}
      </section>

      <Modal
        open={createOpen}
        title="新建个人词库"
        description="创建后可以添加词条，也可以让 Agent 继续整理内容。"
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button onClick={() => setCreateOpen(false)}>取消</Button>
            <Button variant="primary" loading={busy} onClick={() => void createLibrary()}>
              创建词库
            </Button>
          </>
        }
      >
        <div className="form-stack">
          {error ? <InlineError>{error}</InlineError> : null}
          <Field label="词库名称">
            <TextInput
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="例如：家庭阅读 · 十一月"
              autoFocus
            />
          </Field>
          <Field label="分类">
            <TextInput
              value={draft.category}
              onChange={(event) => setDraft({ ...draft, category: event.target.value })}
              placeholder="例如：日常表达"
            />
          </Field>
          <Field label="描述">
            <textarea
              className="text-area"
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              placeholder="说明词库的用途或来源"
              rows={3}
            />
          </Field>
        </div>
      </Modal>
    </main>
  )
}
