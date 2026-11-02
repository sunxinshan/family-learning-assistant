import {
  ArrowLeft,
  BookOpenText,
  CheckCircle2,
  ChevronDown,
  Headphones,
  Info,
  ListChecks,
  Play,
  Settings2,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Field,
  InlineError,
  LoadingBlock,
  PageHeader,
  SelectInput,
  TextInput,
} from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'
import type {
  DictationHint,
  DictationMode,
  PlaybackMode,
  Subject,
  TaskType,
} from '../types/domain'
import { taskModeLabel, taskTypeLabel } from '../utils/format'
import { formatEntrySelection, parseEntrySelection } from '../utils/selection'
import { hasVocabularyDetails } from '../utils/vocabulary'

export const TaskCreatePage = () => {
  const {
    currentUser,
    libraries,
    publicLibraries,
    isLoading,
    loadFullLibraries,
    upsertTask,
    showToast,
  } = useAppStore()
  const navigate = useNavigate()
  const [librariesLoading, setLibrariesLoading] = useState(true)
  const [libraryLoadError, setLibraryLoadError] = useState('')
  const availableLibraries = useMemo(() => {
    const usablePersonal = libraries.filter((library) => library.entries.length > 0)
    const usablePublic = publicLibraries.filter(
      (library) => library.published && library.entries.length > 0,
    )
    return [...usablePersonal, ...usablePublic].filter(
      (library, index, all) => all.findIndex((item) => item.id === library.id) === index,
    )
  }, [libraries, publicLibraries])

  const defaultLibrary = availableLibraries.find((library) => library.subject === 'english')
  const [subjectFilter, setSubjectFilter] = useState<'all' | Subject>('english')
  const subjectLibraries = useMemo(
    () =>
      availableLibraries.filter(
        (library) => subjectFilter === 'all' || library.subject === subjectFilter,
      ),
    [availableLibraries, subjectFilter],
  )
  const [form, setForm] = useState({
    name: '',
    type: 'dictation' as TaskType,
    mode: 'fixed' as 'fixed' | 'long_term',
    libraryId: defaultLibrary?.id ?? '',
    wordSelection: '',
    wordsPerGroup: Math.min(5, defaultLibrary?.entries.length ?? 0),
    repeatUntilCorrect: false,
    dictationMode: 'online' as DictationMode,
    playbackMode: 'manual' as PlaybackMode,
    intervalSeconds: 8,
    repeatCount: 2,
    hint: 'phonetic' as DictationHint,
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const librariesReady = [...libraries, ...publicLibraries].every(hasVocabularyDetails)

  useEffect(() => {
    if (!currentUser) return
    if (librariesReady) {
      setLibrariesLoading(false)
      setLibraryLoadError('')
      return
    }
    let cancelled = false
    setLibrariesLoading(true)
    setLibraryLoadError('')
    void loadFullLibraries()
      .catch((cause) => {
        if (!cancelled) {
          setLibraryLoadError(cause instanceof Error ? cause.message : '词库加载失败')
        }
      })
      .finally(() => {
        if (!cancelled) setLibrariesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentUser, librariesReady, loadFullLibraries])

  const applyLibrary = (libraryId: string) => {
    const library = availableLibraries.find((item) => item.id === libraryId)
    if (!library) return
    setSubjectFilter(library.subject)
    setForm((current) => ({
      ...current,
      libraryId,
      wordSelection: '',
      wordsPerGroup: Math.min(5, library.entries.length),
      name:
        current.name ||
        `${current.type === 'dictation' ? '听写练习' : '词汇学习'} · ${library.name}`,
    }))
  }

  useEffect(() => {
    if (!subjectLibraries.some((library) => library.id === form.libraryId) && subjectLibraries[0]) {
      applyLibrary(subjectLibraries[0].id)
    }
  }, [subjectLibraries, form.libraryId])

  if (!currentUser) return null

  if ((isLoading || librariesLoading) && !availableLibraries.length) {
    return (
      <main className="page-container">
        <LoadingBlock label="正在加载可用词库" />
      </main>
    )
  }

  const selectedLibrary =
    subjectLibraries.find((library) => library.id === form.libraryId) ?? subjectLibraries[0]
  if (!selectedLibrary) {
    return (
      <main className="page-container">
        <Link to="/tasks" className="back-link">
          <ArrowLeft size={15} />
          返回任务列表
        </Link>
        <EmptyState
          icon={BookOpenText}
          title={availableLibraries.length ? '该学科暂无可用词库' : '还没有可用词库'}
          description={
            libraryLoadError
              ? `词库加载失败：${libraryLoadError}`
              : '请创建包含词条的个人词库，或使用已发布的公共词库。'
          }
          action={
            <div className="empty-actions">
              <Link className="button button-primary button-md" to="/vocabulary/new">新建词库</Link>
              <Button onClick={() => setSubjectFilter('all')}>查看全部学科</Button>
            </div>
          }
        />
      </main>
    )
  }

  const selection = parseEntrySelection(form.wordSelection, selectedLibrary.entries)
  const selectedEntries = selection.entries
  const selectedIds = new Set(selectedEntries.map((entry) => entry.id))
  const fixed = form.mode === 'fixed'
  const selectedCount = selectedEntries.length
  const effectiveWordsPerGroup = fixed
    ? Math.max(selectedCount, 1)
    : Math.min(Math.max(form.wordsPerGroup, 1), Math.max(selectedCount, 1))
  const totalGroups = fixed
    ? 1
    : selectedCount > 0
      ? Math.ceil(selectedCount / effectiveWordsPerGroup)
      : 0
  const allSelected = selectedCount === selectedLibrary.entries.length && selectedCount > 0
  const hintPreview = (() => {
    const entry = selectedEntries[0]
    if (!entry) return '勾选词条后可预览朗读时显示的提示'
    if (form.hint === 'phonetic') return entry.phonetic || '该词条暂未填写拼音/音标'
    return entry.meanings.join('；')
  })()

  const changeSubjectFilter = (value: 'all' | Subject) => {
    setSubjectFilter(value)
    const candidates = availableLibraries.filter(
      (library) => value === 'all' || library.subject === value,
    )
    if (candidates.length) applyLibrary(candidates[0].id)
  }

  const setSelection = (ids: string[]) => {
    setForm({
      ...form,
      wordSelection: formatEntrySelection(ids, selectedLibrary.entries),
    })
  }

  const toggleEntry = (entryId: string) => {
    const next = new Set(selectedIds)
    if (next.has(entryId)) next.delete(entryId)
    else next.add(entryId)
    setSelection(selectedLibrary.entries.filter((entry) => next.has(entry.id)).map((entry) => entry.id))
  }

  const submit = async () => {
    if (!form.name.trim()) {
      setError('请输入任务名称')
      return
    }
    if (selection.invalidTokens.length) {
      setError(`词条序号格式无效：${selection.invalidTokens.join('、')}。示例：2-10, 4, 8`)
      return
    }
    if (!selectedEntries.length) {
      setError('请至少勾选一个词条')
      return
    }
    if (!fixed && (form.wordsPerGroup < 1 || form.wordsPerGroup > selectedCount)) {
      setError('每组数量不能大于已选词条数量')
      return
    }
    setSaving(true)
    setError('')
    try {
      const task = await api.task.create(currentUser.id, {
        name: form.name,
        type: form.type,
        mode: form.mode,
        targetCount: selectedCount,
        libraryId: selectedLibrary.id,
        selectedEntryIds: selectedEntries.map((entry) => entry.id),
        wordsPerGroup: effectiveWordsPerGroup,
        repeatUntilCorrect: form.repeatUntilCorrect,
        ...(form.type === 'dictation'
          ? {
              dictation: {
                mode: form.dictationMode,
                playbackMode: form.playbackMode,
                intervalSeconds: form.playbackMode === 'auto' ? form.intervalSeconds : 8,
                hint: form.hint,
                repeatCount: Math.max(1, form.repeatCount),
              },
            }
          : {}),
      })
      upsertTask(task)
      showToast('学习任务已创建', 'success')
      navigate(`/tasks/${task.id}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '任务创建失败')
    } finally {
      setSaving(false)
    }
  }

  if (!availableLibraries.length) {
    return (
      <main className="page-container">
        <Link to="/tasks" className="back-link">
          <ArrowLeft size={15} />
          返回任务列表
        </Link>
        <EmptyState
          icon={BookOpenText}
          title="还没有可用词库"
          description="页面创建任务需要一个至少包含一个词条的个人词库，或已发布的公共词库。"
          action={
            <div className="empty-actions">
              <Link className="button button-primary button-md" to="/vocabulary/new">新建词库</Link>
              <Link className="button button-secondary button-md" to="/vocabulary">浏览公共词库</Link>
            </div>
          }
        />
      </main>
    )
  }

  return (
    <main className="page-container task-create-page">
      <Link to="/tasks" className="back-link">
        <ArrowLeft size={15} />
        返回任务列表
      </Link>
      <PageHeader
        eyebrow="Page Builder"
        title="新建学习任务"
        description="无需通过 Agent，直接配置学习类型、学科词库、词条勾选、任务模式和听写参数。"
        actions={
          <Button variant="primary" loading={saving} icon={Play} onClick={() => void submit()}>
            创建任务
          </Button>
        }
      />

      {currentUser.role === 'admin' ? (
        <div className="admin-boundary-note">
          <ShieldCheck size={16} />
          <span>管理员通过页面创建任务时，任务只会归属于当前管理员账户，不能代替其他用户创建任务。</span>
        </div>
      ) : null}

      <div className="creation-layout task-builder-layout">
        <div className="creation-main">
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>任务配置</h2>
                <p>听写练习为默认类型；任务数量完全取决于下方勾选的词条。</p>
              </div>
            </div>

            <div className="form-stack">
              {error ? <InlineError>{error}</InlineError> : null}
              <Field label="任务名称">
                <TextInput
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  placeholder="例如：语文词语听写 · 第三单元"
                />
              </Field>

              <div className="form-grid-two">
                <Field label="学科筛选">
                  <SelectInput
                    value={subjectFilter}
                    onChange={(event) => changeSubjectFilter(event.target.value as 'all' | Subject)}
                  >
                    <option value="all">全部学科</option>
                    <option value="english">英语</option>
                    <option value="chinese">语文</option>
                  </SelectInput>
                </Field>
                <Field label="内容来源" hint="个人词库或已发布的公共词库">
                  <SelectInput value={selectedLibrary.id} onChange={(event) => applyLibrary(event.target.value)}>
                    {subjectLibraries.map((library) => (
                      <option key={library.id} value={library.id}>
                        {library.subject === 'english' ? '英语' : '语文'} · {library.name} · {library.entries.length} 个词条
                        {library.visibility === 'public' ? ' · 公共' : ' · 个人'}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
              </div>

              <div className="word-picker-panel">
                <div className="word-picker-heading">
                  <div>
                    <h3>选择词库词条</h3>
                    <p>序号输入与勾选状态实时同步；支持 all、2-10、4,8 等表达。</p>
                  </div>
                  <Badge tone={allSelected ? 'success' : 'neutral'}>
                    已选 {selectedCount} / {selectedLibrary.entries.length}
                  </Badge>
                </div>
                <div className="word-selection-row">
                  <TextInput
                    value={form.wordSelection}
                    onChange={(event) => setForm({ ...form, wordSelection: event.target.value })}
                    placeholder="例如：2-10, 4, 8"
                    aria-label="选择词条序号"
                  />
                  <Button
                    size="sm"
                    icon={ListChecks}
                    onClick={() =>
                      setForm({
                        ...form,
                        wordSelection: allSelected
                          ? ''
                          : selectedLibrary.entries.length <= 1
                            ? '1'
                            : `1-${selectedLibrary.entries.length}`,
                      })
                    }
                  >
                    {allSelected ? '取消全选' : '全选'}
                  </Button>
                </div>
                {selection.invalidTokens.length ? (
                  <InlineError>
                    无法识别：{selection.invalidTokens.join('、')}。请输入有效序号，例如 2-10, 4, 8。
                  </InlineError>
                ) : null}
                <div className="word-picker-list">
                  {selectedLibrary.entries.map((entry, index) => (
                    <label
                      key={entry.id}
                      className={`word-picker-row ${selectedIds.has(entry.id) ? 'is-selected' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(entry.id)}
                        onChange={() => toggleEntry(entry.id)}
                      />
                      <span className="word-picker-index">{String(index + 1).padStart(2, '0')}</span>
                      <div className="word-picker-word">
                        <strong>{entry.word}</strong>
                        <span>{entry.phonetic}</span>
                      </div>
                      <p>{entry.meanings.join('；')}</p>
                    </label>
                  ))}
                </div>
              </div>

              <details className="advanced-settings">
                <summary>
                  <span className="advanced-settings-title">
                    <Settings2 size={16} />
                    高级设置
                  </span>
                  <span className="advanced-settings-summary">
                    {taskTypeLabel(form.type)} · {taskModeLabel(form.mode)} ·{' '}
                    {fixed ? '固定内容' : `${totalGroups} 组`} · 强制重做{form.repeatUntilCorrect ? '开' : '关'}
                  </span>
                  <ChevronDown size={16} className="advanced-settings-chevron" />
                </summary>
                <div className="advanced-settings-body">
                  <div className="form-grid-two">
                    <Field label="学习类型">
                      <SelectInput value={form.type} disabled aria-readonly="true">
                        <option value="dictation">听写练习（V1 唯一正式类型）</option>
                      </SelectInput>
                    </Field>
                    <Field label="任务模式">
                      <SelectInput
                        value={form.mode}
                        onChange={(event) =>
                          setForm({ ...form, mode: event.target.value as 'fixed' | 'long_term' })
                        }
                      >
                        <option value="long_term">长期任务</option>
                        <option value="fixed">固定任务</option>
                      </SelectInput>
                    </Field>
                  </div>
                  {fixed ? (
                    <div className="info-note">
                      <Info size={15} />
                      固定任务直接使用已选 {selectedCount} 个词条，不需要学习数量和每组数量。
                    </div>
                  ) : (
                    <Field
                      label="每组数量"
                      hint={`已选 ${selectedCount} 项；该数量会决定 ${totalGroups} 个学习分组`}
                    >
                      <TextInput
                        type="number"
                        min={1}
                        max={Math.max(selectedCount, 1)}
                        value={form.wordsPerGroup}
                        onChange={(event) =>
                          setForm({ ...form, wordsPerGroup: Number(event.target.value) })
                        }
                      />
                    </Field>
                  )}
                  <Checkbox
                    checked={form.repeatUntilCorrect}
                    onChange={(checked) => setForm({ ...form, repeatUntilCorrect: checked })}
                    label="开启强制重做：答对后才能进入下一组"
                  />
                </div>
              </details>

              {form.type === 'dictation' ? (
                <div className="dictation-config-box">
                  <div className="dictation-config-heading">
                    <Headphones size={16} />
                    <div>
                      <strong>听写设置</strong>
                      <span>这些设置会随任务保存，并作用于听写练习页面。</span>
                    </div>
                  </div>
                  <div className="form-grid-two">
                    <Field label="听写方式">
                      <SelectInput
                        value={form.dictationMode}
                        onChange={(event) =>
                          setForm({ ...form, dictationMode: event.target.value as DictationMode })
                        }
                      >
                        <option value="online">线上听写 · 页面输入并自动判分</option>
                        <option value="offline">线下听写 · 用户勾选错误项</option>
                      </SelectInput>
                    </Field>
                    <Field label="播放方式">
                      <SelectInput
                        value={form.playbackMode}
                        onChange={(event) =>
                          setForm({ ...form, playbackMode: event.target.value as PlaybackMode })
                        }
                      >
                        <option value="manual">手动播放</option>
                        <option value="auto">自动播放</option>
                      </SelectInput>
                    </Field>
                  </div>
                  <div className="form-grid-three">
                    {form.playbackMode === 'auto' ? (
                      <Field label="自动播放间隔" hint="练习页面显示倒计时">
                        <TextInput
                          type="number"
                          min={2}
                          max={60}
                          value={form.intervalSeconds}
                          onChange={(event) =>
                            setForm({ ...form, intervalSeconds: Number(event.target.value) })
                          }
                        />
                      </Field>
                    ) : <div />}
                    <Field label="朗读次数">
                      <TextInput
                        type="number"
                        min={1}
                        max={5}
                        value={form.repeatCount}
                        onChange={(event) =>
                          setForm({ ...form, repeatCount: Number(event.target.value) })
                        }
                      />
                    </Field>
                    <Field label="朗读内容">
                      <SelectInput
                        value={form.hint}
                        disabled={selectedLibrary.subject === 'chinese'}
                        onChange={(event) =>
                          setForm({ ...form, hint: event.target.value as DictationHint })
                        }
                      >
                        <option value="phonetic">
                          {selectedLibrary.subject === 'english' ? '英语单词' : '词语发音（直接读出）'}
                        </option>
                        {selectedLibrary.subject === 'english' ? (
                          <option value="meaning">中文释义</option>
                        ) : null}
                      </SelectInput>
                    </Field>
                  </div>
                  <div className="hint-preview">
                    <span>页面提示预览</span>
                    <strong>{hintPreview}</strong>
                  </div>
                </div>
              ) : null}

              <div className="info-note">
                <Info size={15} />
                {fixed
                  ? '固定任务创建后不能修改学习内容；需要调整时请删除并重新创建。'
                  : '长期任务会保存创建时的词库快照，后续修改原词库不会影响已有任务。'}
              </div>
            </div>
          </section>
        </div>

        <aside className="creation-side">
          <section className="panel compact-panel task-summary-card">
            <div className="task-summary-icon">
              {form.type === 'vocabulary' ? <BookOpenText size={21} /> : <Headphones size={21} />}
            </div>
            <Badge tone={form.type === 'vocabulary' ? 'info' : 'neutral'}>{taskTypeLabel(form.type)}</Badge>
            <h2>{form.name || '未命名学习任务'}</h2>
            <p>{selectedLibrary.subject === 'english' ? '英语' : '语文'} · {selectedLibrary.name}</p>
            <dl className="create-summary-list">
              <div><dt>任务模式</dt><dd>{taskModeLabel(form.mode)}</dd></div>
              <div><dt>已选词条</dt><dd>{selectedCount} 项</dd></div>
              <div>
                <dt>数量/分组</dt>
                <dd>
                  {fixed
                    ? '固定内容无需设置'
                    : `${selectedCount} 项 · ${totalGroups} 组 · 每组 ${effectiveWordsPerGroup} 项`}
                </dd>
              </div>
              {form.type === 'dictation' ? (
                <>
                  <div><dt>听写方式</dt><dd>{form.dictationMode === 'online' ? '线上听写' : '线下听写'}</dd></div>
                  <div><dt>播放方式</dt><dd>{form.playbackMode === 'auto' ? `自动 · ${form.intervalSeconds} 秒` : '手动'}</dd></div>
                  <div><dt>朗读次数</dt><dd>{form.repeatCount} 次</dd></div>
                  <div><dt>朗读内容</dt><dd>{selectedLibrary.subject === 'chinese' ? '词语发音（直接读出）' : form.hint === 'phonetic' ? '英语单词' : '中文释义'}</dd></div>
                </>
              ) : null}
              <div><dt>强制重做</dt><dd>{form.repeatUntilCorrect ? '开启' : '关闭'}</dd></div>
              <div><dt>归属</dt><dd>{currentUser.nickname}</dd></div>
            </dl>
            <Button variant="primary" loading={saving} icon={CheckCircle2} onClick={() => void submit()}>
              创建并保存快照
            </Button>
            {fixed ? (
              <div className="subtle-link task-summary-link">
                <Info size={14} />
                固定任务内容不可修改
              </div>
            ) : null}
          </section>
        </aside>
      </div>
    </main>
  )
}
