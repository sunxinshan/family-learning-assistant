import {
  ArrowLeft,
  BookCopy,
  BookOpenText,
  CheckSquare,
  Download,
  Pencil,
  Plus,
  Search,
  Square,
  Trash2,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { vocabularyApi } from '../api/mockApi'
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Field,
  IconButton,
  InlineError,
  Modal,
  PageHeader,
  TextInput,
} from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import type { WordEntry } from '../types/domain'
import { formatDateTime } from '../utils/format'

const blankEntry = (): WordEntry => ({
  id: `word-${crypto.randomUUID()}`,
  word: '',
  phonetic: '',
  partOfSpeech: '',
  meanings: [''],
  example: '',
  exampleTranslation: '',
})

export const VocabularyDetailPage = () => {
  const { libraryId } = useParams()
  const navigate = useNavigate()
  const {
    libraries,
    publicLibraries,
    currentUser,
    refresh,
    showToast,
  } = useAppStore()
  const library = [...libraries, ...publicLibraries].find((candidate) => candidate.id === libraryId)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [entryDraft, setEntryDraft] = useState<WordEntry | null>(null)
  const [isNew, setIsNew] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [batchEditOpen, setBatchEditOpen] = useState(false)
  const [batchPartOfSpeech, setBatchPartOfSpeech] = useState('')

  const editable = Boolean(
    library &&
      currentUser &&
      (library.ownerId === currentUser.id ||
        (currentUser.role === 'admin' && library.visibility === 'public')),
  )
  const filtered = useMemo(
    () =>
      library?.entries.filter((entry) =>
        `${entry.word} ${entry.phonetic} ${entry.meanings.join(' ')} ${entry.example}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ) ?? [],
    [library, query],
  )

  if (!library || !currentUser) {
    return (
      <main className="page-container">
        <EmptyState
          icon={BookOpenText}
          title="词库不存在"
          description="它可能已经被删除，或者你没有访问权限。"
          action={<Link className="button button-primary button-md" to="/vocabulary">返回词库列表</Link>}
        />
      </main>
    )
  }

  const allSelected = filtered.length > 0 && filtered.every((entry) => selected.includes(entry.id))
  const selectedEntries = library.entries.filter((entry) => selected.includes(entry.id))

  const openNew = () => {
    setEntryDraft(blankEntry())
    setIsNew(true)
    setError('')
  }

  const openEdit = (entry: WordEntry) => {
    setEntryDraft({ ...entry, meanings: [...entry.meanings] })
    setIsNew(false)
    setError('')
  }

  const saveEntry = async () => {
    if (!entryDraft) return
    if (!entryDraft.word.trim()) {
      setError('单词不能为空')
      return
    }
    const normalized: WordEntry = {
      ...entryDraft,
      word: entryDraft.word.trim(),
      phonetic: entryDraft.phonetic.trim(),
      partOfSpeech: entryDraft.partOfSpeech.trim(),
      meanings: entryDraft.meanings.map((meaning) => meaning.trim()).filter(Boolean),
      example: entryDraft.example.trim(),
      exampleTranslation: entryDraft.exampleTranslation.trim(),
    }
    if (normalized.meanings.length === 0) {
      setError('至少填写一个词义')
      return
    }
    setBusy(true)
    setError('')
    try {
      if (isNew) {
        await vocabularyApi.insertEntries(currentUser.id, library.id, [normalized])
      } else {
        await vocabularyApi.updateEntry(currentUser.id, library.id, normalized)
      }
      refresh()
      setEntryDraft(null)
      showToast(isNew ? '词条已添加' : '词条已更新', 'success')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const removeSelected = async () => {
    setBusy(true)
    try {
      await vocabularyApi.removeEntries(currentUser.id, library.id, selected)
      refresh()
      setSelected([])
      setDeleteOpen(false)
      showToast(`已删除 ${selected.length} 个词条`, 'success')
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '删除失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const saveBatchEdit = async () => {
    if (!batchPartOfSpeech.trim() || selectedEntries.length === 0) return
    setBusy(true)
    try {
      for (const entry of selectedEntries) {
        await vocabularyApi.updateEntry(currentUser.id, library.id, {
          ...entry,
          partOfSpeech: batchPartOfSpeech.trim(),
        })
      }
      refresh()
      setSelected([])
      setBatchEditOpen(false)
      showToast(`已批量更新 ${selectedEntries.length} 个词条`, 'success')
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '批量编辑失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const copyLibrary = async () => {
    setBusy(true)
    try {
      const copy = await vocabularyApi.copy(currentUser.id, library.id)
      refresh()
      showToast('公共词库已复制为个人副本', 'success')
      navigate(`/vocabulary/${copy.id}`)
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '复制失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const toggleSelection = (entryId: string) => {
    setSelected((current) =>
      current.includes(entryId)
        ? current.filter((id) => id !== entryId)
        : [...current, entryId],
    )
  }

  return (
    <main className="page-container vocabulary-detail-page">
      <Link to="/vocabulary" className="back-link">
        <ArrowLeft size={15} />
        返回词库列表
      </Link>
      <PageHeader
        eyebrow={library.visibility === 'public' ? '公共词库' : '个人词库'}
        title={library.name}
        description={library.description || '暂无描述'}
        actions={
          editable ? (
            <Button variant="primary" icon={Plus} onClick={openNew}>添加词条</Button>
          ) : (
            <Button variant="primary" icon={Download} loading={busy} onClick={() => void copyLibrary()}>
              复制为个人词库
            </Button>
          )
        }
      />

      <section className="library-detail-meta">
        <div>
          <span className="meta-label">分类</span>
          <strong>{library.category}</strong>
        </div>
        <div>
          <span className="meta-label">词条</span>
          <strong>{library.entries.length} 个</strong>
        </div>
        <div>
          <span className="meta-label">最近更新</span>
          <strong>{formatDateTime(library.updatedAt)}</strong>
        </div>
        <div className="library-detail-tags">
          {library.tags.map((tag) => <Badge key={tag}>{tag}</Badge>)}
          {!editable ? <Badge tone="info">只读</Badge> : null}
        </div>
      </section>

      <div className="list-toolbar">
        <div className="search-field">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索单词、音标、词义或例句"
            aria-label="搜索词条"
          />
        </div>
        {editable && selected.length ? (
          <div className="selection-toolbar">
            <span>已选 {selected.length} 项</span>
            <Button size="sm" icon={Pencil} onClick={() => setBatchEditOpen(true)}>
              批量编辑
            </Button>
            <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDeleteOpen(true)}>
              批量删除
            </Button>
          </div>
        ) : (
          <span className="toolbar-count">{filtered.length} 个词条</span>
        )}
      </div>

      <section className="table-panel">
        <div className="data-table-wrap">
          <table className="data-table vocabulary-table">
            <thead>
              <tr>
                {editable ? (
                  <th className="checkbox-cell">
                    <button
                      type="button"
                      className="table-check-button"
                      aria-label={allSelected ? '取消全选' : '全选当前结果'}
                      onClick={() => {
                        if (allSelected) {
                          setSelected((current) =>
                            current.filter((id) => !filtered.some((entry) => entry.id === id)),
                          )
                        } else {
                          setSelected((current) => [
                            ...new Set([...current, ...filtered.map((entry) => entry.id)]),
                          ])
                        }
                      }}
                    >
                      {allSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                    </button>
                  </th>
                ) : null}
                <th>单词</th>
                <th>词义</th>
                <th>例句</th>
                <th className="actions-cell">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <tr key={entry.id} className={selected.includes(entry.id) ? 'row-selected' : ''}>
                  {editable ? (
                    <td className="checkbox-cell">
                      <button
                        type="button"
                        className="table-check-button"
                        aria-label={selected.includes(entry.id) ? '取消选择' : '选择词条'}
                        onClick={() => toggleSelection(entry.id)}
                      >
                        {selected.includes(entry.id) ? <CheckSquare size={16} /> : <Square size={16} />}
                      </button>
                    </td>
                  ) : null}
                  <td>
                    <div className="word-cell">
                      <strong>{entry.word}</strong>
                      <span>{entry.phonetic}</span>
                      <small>{entry.partOfSpeech}</small>
                    </div>
                  </td>
                  <td>
                    <div className="meaning-cell">
                      {entry.meanings.map((meaning) => <span key={meaning}>{meaning}</span>)}
                    </div>
                  </td>
                  <td>
                    <div className="example-cell">
                      <span>{entry.example}</span>
                      <small>{entry.exampleTranslation}</small>
                    </div>
                  </td>
                  <td className="actions-cell">
                    {editable ? (
                      <IconButton label="编辑词条" icon={Pencil} size="sm" onClick={() => openEdit(entry)} />
                    ) : (
                      <Badge tone="info">只读</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!filtered.length ? (
          <EmptyState
            icon={BookOpenText}
            title={query ? '没有匹配的词条' : '词库还是空的'}
            description={query ? '尝试更换搜索关键词。' : '添加第一个词条后，就可以用它创建学习任务。'}
            action={!query && editable ? <Button icon={Plus} onClick={openNew}>添加词条</Button> : undefined}
          />
        ) : null}
      </section>

      {!editable ? (
        <div className="public-note">
          <BookCopy size={15} />
          这是公共词库的只读视图。复制后可独立添加、编辑或删除词条，不影响公共源。
        </div>
      ) : null}

      <Modal
        open={Boolean(entryDraft)}
        title={isNew ? '添加词条' : '编辑词条'}
        description="同一个词库中词形不能重复，一个词条允许保存多个词义。"
        width="lg"
        onClose={() => setEntryDraft(null)}
        footer={
          <>
            <Button onClick={() => setEntryDraft(null)}>取消</Button>
            <Button variant="primary" loading={busy} onClick={() => void saveEntry()}>
              {isNew ? '添加词条' : '保存修改'}
            </Button>
          </>
        }
      >
        {entryDraft ? (
          <div className="form-stack">
            {error ? <InlineError>{error}</InlineError> : null}
            <div className="form-grid-three">
              <Field label="单词">
                <TextInput
                  value={entryDraft.word}
                  onChange={(event) => setEntryDraft({ ...entryDraft, word: event.target.value })}
                  autoFocus
                />
              </Field>
              <Field label="音标">
                <TextInput
                  value={entryDraft.phonetic}
                  onChange={(event) => setEntryDraft({ ...entryDraft, phonetic: event.target.value })}
                  placeholder="/ˈwɜːd/"
                />
              </Field>
              <Field label="词性">
                <TextInput
                  value={entryDraft.partOfSpeech}
                  onChange={(event) => setEntryDraft({ ...entryDraft, partOfSpeech: event.target.value })}
                  placeholder="n. / v. / adj."
                />
              </Field>
            </div>
            <Field label="词义" hint="多个词义请使用换行分隔">
              <textarea
                className="text-area"
                rows={3}
                value={entryDraft.meanings.join('\n')}
                onChange={(event) =>
                  setEntryDraft({ ...entryDraft, meanings: event.target.value.split('\n') })
                }
              />
            </Field>
            <div className="form-grid-two">
              <Field label="英文例句">
                <textarea
                  className="text-area"
                  rows={3}
                  value={entryDraft.example}
                  onChange={(event) => setEntryDraft({ ...entryDraft, example: event.target.value })}
                />
              </Field>
              <Field label="例句翻译">
                <textarea
                  className="text-area"
                  rows={3}
                  value={entryDraft.exampleTranslation}
                  onChange={(event) =>
                    setEntryDraft({ ...entryDraft, exampleTranslation: event.target.value })
                  }
                />
              </Field>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={batchEditOpen}
        title="批量编辑词条"
        description={`将统一更新已选的 ${selected.length} 个词条。`}
        width="sm"
        onClose={() => setBatchEditOpen(false)}
        footer={
          <>
            <Button onClick={() => setBatchEditOpen(false)}>取消</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={!batchPartOfSpeech.trim()}
              onClick={() => void saveBatchEdit()}
            >
              应用修改
            </Button>
          </>
        }
      >
        <Field label="统一词性">
          <TextInput
            value={batchPartOfSpeech}
            onChange={(event) => setBatchPartOfSpeech(event.target.value)}
            placeholder="例如：n."
            autoFocus
          />
        </Field>
        <Checkbox checked onChange={() => undefined} label="仅修改词性，其他字段保持不变" disabled />
      </Modal>

      <Modal
        open={deleteOpen}
        title="删除选中词条"
        description="删除词条不会影响已经创建的任务，因为任务使用创建时快照。"
        width="sm"
        danger
        onClose={() => setDeleteOpen(false)}
        footer={
          <>
            <Button onClick={() => setDeleteOpen(false)}>取消</Button>
            <Button variant="danger" loading={busy} onClick={() => void removeSelected()}>
              确认删除 {selected.length} 项
            </Button>
          </>
        }
      >
        <p className="modal-copy">确定从「{library.name}」中删除已选词条吗？</p>
      </Modal>
    </main>
  )
}
