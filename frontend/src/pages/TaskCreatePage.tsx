import {
  ArrowLeft,
  BookOpenText,
  CheckCircle2,
  Headphones,
  Info,
  Play,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { taskApi } from '../api/mockApi'
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Field,
  InlineError,
  PageHeader,
  SelectInput,
  TextInput,
} from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import type { TaskType } from '../types/domain'
import { taskModeLabel, taskTypeLabel } from '../utils/format'

export const TaskCreatePage = () => {
  const { currentUser, libraries, publicLibraries, refresh, showToast } = useAppStore()
  const navigate = useNavigate()
  const availableLibraries = useMemo(() => {
    const usablePersonal = libraries.filter((library) => library.entries.length > 0)
    const usablePublic = publicLibraries.filter(
      (library) => library.published && library.entries.length > 0,
    )
    return [...usablePersonal, ...usablePublic].filter(
      (library, index, all) => all.findIndex((item) => item.id === library.id) === index,
    )
  }, [libraries, publicLibraries])

  const [form, setForm] = useState({
    name: '',
    type: 'vocabulary' as TaskType,
    mode: 'long_term' as 'fixed' | 'long_term',
    libraryId: availableLibraries[0]?.id ?? '',
    targetCount: Math.min(10, availableLibraries[0]?.entries.length ?? 0),
    wordsPerGroup: Math.min(5, availableLibraries[0]?.entries.length ?? 0),
    repeatUntilCorrect: false,
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (availableLibraries.length && !availableLibraries.some((library) => library.id === form.libraryId)) {
      const library = availableLibraries[0]
      const count = Math.min(10, library.entries.length)
      setForm((current) => ({
        ...current,
        libraryId: library.id,
        targetCount: count,
        wordsPerGroup: Math.min(5, count),
        name: current.name || `${current.type === 'vocabulary' ? '词汇学习' : '听写练习'} · ${library.name}`,
      }))
    }
  }, [availableLibraries, form.libraryId])

  if (!currentUser) return null

  const selectedLibrary =
    availableLibraries.find((library) => library.id === form.libraryId) ?? availableLibraries[0]
  const maxEntries = selectedLibrary?.entries.length ?? 0
  const previewEntries = selectedLibrary?.entries.slice(0, Math.min(form.targetCount, 5)) ?? []
  const totalGroups =
    form.targetCount > 0 && form.wordsPerGroup > 0
      ? Math.ceil(form.targetCount / form.wordsPerGroup)
      : 0

  const selectLibrary = (libraryId: string) => {
    const library = availableLibraries.find((item) => item.id === libraryId)
    const count = Math.min(10, library?.entries.length ?? 0)
    setForm({
      ...form,
      libraryId,
      targetCount: count,
      wordsPerGroup: Math.min(5, count),
      name:
        form.name ||
        `${form.type === 'vocabulary' ? '词汇学习' : '听写练习'} · ${library?.name ?? ''}`,
    })
  }

  const submit = async () => {
    if (!selectedLibrary) {
      setError('请先创建或复制一个词库')
      return
    }
    if (!form.name.trim()) {
      setError('请输入任务名称')
      return
    }
    if (form.targetCount < 1 || form.targetCount > maxEntries) {
      setError(`学习数量需要在 1 到 ${maxEntries} 之间`)
      return
    }
    if (form.wordsPerGroup < 1 || form.wordsPerGroup > form.targetCount) {
      setError('每组数量不能大于学习数量')
      return
    }
    setSaving(true)
    setError('')
    try {
      const task = await taskApi.create(currentUser.id, {
        name: form.name,
        type: form.type,
        mode: form.mode,
        targetCount: form.targetCount,
        libraryId: selectedLibrary.id,
        wordsPerGroup: form.wordsPerGroup,
        repeatUntilCorrect: form.repeatUntilCorrect,
      })
      refresh()
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
        description="无需通过 Agent，直接配置学习类型、内容来源、任务模式和练习参数。"
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
                <p>所有参数都会在创建前写入任务配置和内容快照。</p>
              </div>
            </div>

            <div className="form-stack">
              {error ? <InlineError>{error}</InlineError> : null}
              <Field label="任务名称">
                <TextInput
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  placeholder="例如：晨间词汇 · Week 45"
                />
              </Field>

              <div className="form-grid-two">
                <Field label="学习类型">
                  <SelectInput
                    value={form.type}
                    onChange={(event) => {
                      const type = event.target.value as TaskType
                      setForm({
                        ...form,
                        type,
                        name: form.name || `${type === 'vocabulary' ? '词汇学习' : '听写练习'} · ${selectedLibrary.name}`,
                      })
                    }}
                  >
                    <option value="vocabulary">词汇练习</option>
                    <option value="dictation">听写练习</option>
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

              <Field label="内容来源" hint="个人词库或已发布的公共词库">
                <SelectInput value={form.libraryId} onChange={(event) => selectLibrary(event.target.value)}>
                  {availableLibraries.map((library) => (
                    <option key={library.id} value={library.id}>
                      {library.name} · {library.entries.length} 个词条
                      {library.visibility === 'public' ? ' · 公共' : ' · 个人'}
                    </option>
                  ))}
                </SelectInput>
              </Field>

              <div className="form-grid-two">
                <Field label="学习数量" hint={`最多 ${maxEntries} 项`}>
                  <TextInput
                    type="number"
                    min={1}
                    max={maxEntries}
                    value={form.targetCount}
                    onChange={(event) => setForm({ ...form, targetCount: Number(event.target.value) })}
                  />
                </Field>
                <Field label="每组数量">
                  <TextInput
                    type="number"
                    min={1}
                    max={form.targetCount}
                    value={form.wordsPerGroup}
                    onChange={(event) => setForm({ ...form, wordsPerGroup: Number(event.target.value) })}
                  />
                </Field>
              </div>

              <Checkbox
                checked={form.repeatUntilCorrect}
                onChange={(checked) => setForm({ ...form, repeatUntilCorrect: checked })}
                label="开启强制重做：答对后才能进入下一组"
              />

              <div className="info-note">
                <Info size={15} />
                {form.mode === 'fixed'
                  ? '固定任务创建后不能修改学习内容；需要调整时请删除并重新创建。'
                  : '长期任务会保存创建时的词库快照，后续修改原词库不会影响已有任务。'}
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>内容预览</h2>
                <p>前 {previewEntries.length} 个词条预览，实际任务将保存 {form.targetCount} 个词条快照。</p>
              </div>
            </div>
            <div className="task-preview-list">
              {previewEntries.map((entry, index) => (
                <div key={entry.id}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <strong>{entry.word}</strong>
                  <small>{entry.phonetic}</small>
                  <p>{entry.meanings.join('；')}</p>
                </div>
              ))}
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
            <p>{selectedLibrary.name}</p>
            <dl className="create-summary-list">
              <div><dt>任务模式</dt><dd>{taskModeLabel(form.mode)}</dd></div>
              <div><dt>学习数量</dt><dd>{form.targetCount} 项</dd></div>
              <div><dt>分组</dt><dd>{totalGroups} 组 · 每组 {form.wordsPerGroup} 项</dd></div>
              <div><dt>强制重做</dt><dd>{form.repeatUntilCorrect ? '开启' : '关闭'}</dd></div>
              <div><dt>归属</dt><dd>{currentUser.nickname}</dd></div>
            </dl>
            <Button variant="primary" loading={saving} icon={CheckCircle2} onClick={() => void submit()}>
              创建并保存快照
            </Button>
            {form.mode === 'fixed' ? (
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
