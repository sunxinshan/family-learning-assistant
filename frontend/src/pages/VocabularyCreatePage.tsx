import {
  ArrowLeft,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Pencil,
  Plus,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { useRef, useState, type ChangeEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import {
  Button,
  Field,
  IconButton,
  InlineError,
  Modal,
  PageHeader,
  SelectInput,
  TagInput,
  TextInput,
} from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'
import type { Subject, WordEntry } from '../types/domain'

const blankEntry = (): WordEntry => ({
  id: `word-${crypto.randomUUID()}`,
  word: '',
  phonetic: '',
  partOfSpeech: '',
  meanings: [''],
  example: '',
  exampleTranslation: '',
})

export const VocabularyCreatePage = () => {
  const { currentUser, refresh, showToast, upsertLibrary } = useAppStore()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isAdmin = currentUser?.role === 'admin'
  const [visibility, setVisibility] = useState<'personal' | 'public'>(
    isAdmin && searchParams.get('scope') === 'public' ? 'public' : 'personal',
  )
  const [form, setForm] = useState({
    subject: 'english' as Subject,
    name: '',
    description: '',
    tags: [] as string[],
  })
  const [entries, setEntries] = useState<WordEntry[]>([])
  const [fileName, setFileName] = useState('')
  const [headers, setHeaders] = useState<string[]>([])
  const [parseErrors, setParseErrors] = useState<string[]>([])
  const [extraction, setExtraction] = useState<{ id: string; version: number } | null>(null)
  const [mappingSummary, setMappingSummary] = useState('')
  const [parsing, setParsing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [entryDraft, setEntryDraft] = useState<WordEntry | null>(null)
  const [entryError, setEntryError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  if (!currentUser) return null

  const handleTemplate = async () => {
    setDownloading(true)
    try {
      const blob = await api.materials.downloadTemplate(form.subject)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'vocabulary-template.xlsx'
      link.click()
      URL.revokeObjectURL(url)
      showToast('Excel 模板已下载', 'success')
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '模板下载失败', 'danger')
    } finally {
      setDownloading(false)
    }
  }

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setParsing(true)
    setFileName(file.name)
    setError('')
    setExtraction(null)
    setMappingSummary('')
    try {
      const material = await api.materials.upload(file)
      const result = await api.content.extract(material.id, form.subject)
      const parsedEntries = result.extractedJson.entries.map((entry) => ({
        ...entry,
        id: `word-${crypto.randomUUID()}`,
      }))
      setForm({
        subject: result.extractedJson.subject,
        name: result.extractedJson.name,
        description: result.extractedJson.description,
        tags: result.extractedJson.tags,
      })
      setEntries(parsedEntries)
      setHeaders(
        form.subject === 'chinese'
          ? ['词语', '拼音', '词性', '释义', '例句', '例句翻译']
          : ['单词', '音标', '词性', '词义', '例句', '例句翻译'],
      )
      setParseErrors(result.errorsJson.map((item) => item.message ?? `第 ${item.row ?? '?'} 行解析失败`))
      setExtraction({ id: result.id, version: result.version })
      const labels = Object.entries(result.mapping.fields)
        .filter(([, value]) => value.index >= 0)
        .map(([field, value]) => `${field} ← ${value.header}`)
        .join('，')
      const enrichment = result.mapping.enrichment
      const enrichmentLabel = enrichment?.requested
        ? `；自动补充 ${enrichment.completed}/${enrichment.requested} 项`
        : ''
      setMappingSummary(
        `${result.mappingSource === 'llm' ? '模型识别' : '规则识别'}：${labels}${enrichmentLabel}`,
      )
      if (parsedEntries.length) {
        showToast(`服务端已解析 ${parsedEntries.length} 个词条`, 'success')
      }
    } catch (cause) {
      setEntries([])
      setParseErrors([cause instanceof Error ? cause.message : '文件解析失败'])
    } finally {
      setParsing(false)
    }
  }

  const openNewEntry = () => {
    setEntryDraft(blankEntry())
    setEntryError('')
  }

  const openEditEntry = (entry: WordEntry) => {
    setEntryDraft({ ...entry, meanings: [...entry.meanings] })
    setEntryError('')
  }

  const saveEntry = () => {
    if (!entryDraft) return
    const word = entryDraft.word.trim()
    const meanings = entryDraft.meanings.map((item) => item.trim()).filter(Boolean)
    if (!word) {
      setEntryError('单词不能为空')
      return
    }
    if (!meanings.length) {
      setEntryError('至少填写一个词义')
      return
    }
    if (
      entries.some(
        (entry) => entry.id !== entryDraft.id && entry.word.toLowerCase() === word.toLowerCase(),
      )
    ) {
      setEntryError('同一词库中不能出现重复词条')
      return
    }
    const normalized = { ...entryDraft, word, meanings }
    setEntries((current) =>
      current.some((entry) => entry.id === normalized.id)
        ? current.map((entry) => (entry.id === normalized.id ? normalized : entry))
        : [...current, normalized],
    )
    setEntryDraft(null)
  }

  const saveLibrary = async () => {
    if (!form.name.trim()) {
      setError('请输入词库名称')
      return
    }
    if (parseErrors.length && !entries.length) {
      setError('请先修复文件解析问题或手动添加词条')
      return
    }
    setSaving(true)
    setError('')
    try {
      const draft = {
        subject: form.subject,
        name: form.name,
        description: form.description,
        tags: form.tags,
        entries,
      }
      const library =
        visibility === 'public'
          ? await api.vocabulary.createPublic(currentUser.id, draft)
          : extraction
            ? await api.content
                .update(extraction.id, extraction.version, draft)
                .then((updated) => api.content.confirm(updated.id, updated.version))
            : await api.vocabulary.create(currentUser.id, draft)
      upsertLibrary(library)
      await refresh()
      showToast(
        visibility === 'public' ? '公共词库草稿已创建' : '个人词库已创建',
        'success',
      )
      navigate(`/vocabulary/${library.id}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '词库创建失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="page-container vocabulary-create-page">
      <Link to="/vocabulary" className="back-link">
        <ArrowLeft size={15} />
        返回词库列表
      </Link>
      <PageHeader
        eyebrow={visibility === 'public' ? 'Public Library' : 'Personal Library'}
        title={visibility === 'public' ? '新建公共词库' : '新建词库'}
        description="可在页面上完整配置词库信息、标签和词条，也可以从 Excel / CSV 批量导入。"
        actions={
          <Button variant="primary" loading={saving} onClick={() => void saveLibrary()}>
            创建词库
          </Button>
        }
      />

      {isAdmin ? (
        <div className="scope-switch-row">
          <span>创建位置</span>
          <div className="filter-group">
            <button
              type="button"
              className={visibility === 'personal' ? 'active' : ''}
              onClick={() => setVisibility('personal')}
            >
              我的个人词库
            </button>
            <button
              type="button"
              className={visibility === 'public' ? 'active' : ''}
              onClick={() => setVisibility('public')}
            >
              公共词库
            </button>
          </div>
          <small>公共词库创建后为草稿，可在后台或详情页继续编辑并发布。</small>
        </div>
      ) : null}

      <div className="creation-layout">
        <div className="creation-main">
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>基本信息</h2>
                <p>词库名称、学科和标签均可自定义，后续仍可继续编辑。</p>
              </div>
            </div>
            <div className="form-stack">
              {error ? <InlineError>{error}</InlineError> : null}
              <div className="form-grid-two">
                <Field label="学科">
                  <SelectInput
                    value={form.subject}
                    onChange={(event) => setForm({ ...form, subject: event.target.value as Subject })}
                  >
                    <option value="english">英语</option>
                    <option value="chinese">语文</option>
                  </SelectInput>
                </Field>
                <Field label="词库名称">
                  <TextInput
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                    placeholder="例如：家庭阅读 · 十一月"
                  />
                </Field>
              </div>
              <Field label="描述">
                <textarea
                  className="text-area"
                  rows={3}
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                  placeholder="说明词库的用途、来源或学习目标"
                />
              </Field>
              <Field label="标签" hint="支持自定义多个标签；按 Enter、逗号添加">
                <TagInput
                  value={form.tags}
                  onChange={(tags) => setForm({ ...form, tags })}
                  placeholder="例如：亲子共学、周末复习"
                />
              </Field>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>词条内容</h2>
                <p>可以手动添加，也可以上传 Excel / CSV 批量导入后再逐条调整。</p>
              </div>
              <div className="panel-header-actions">
                <Button size="sm" icon={Plus} onClick={openNewEntry}>手动添加</Button>
              </div>
            </div>

            <div className="import-zone">
              <div className="import-zone-copy">
                <span className="import-icon"><FileSpreadsheet size={20} /></span>
                <div>
                  <strong>从表格导入词条</strong>
                  <p>支持 `.xlsx` 和 `.csv`，第一行必须是字段表头。</p>
                </div>
              </div>
              <div className="import-zone-actions">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.csv,text/csv"
                  hidden
                  onChange={(event) => void handleFile(event)}
                />
                <Button
                  variant="primary"
                  icon={UploadCloud}
                  loading={parsing}
                  onClick={() => fileInputRef.current?.click()}
                >
                  选择文件
                </Button>
                <Button
                  icon={Download}
                  loading={downloading}
                  onClick={() => void handleTemplate()}
                >
                  下载 Excel 模板
                </Button>
              </div>
            </div>

            {fileName ? (
              <div className="import-result-bar">
                <div>
                  <CheckCircle2 size={15} />
                  <strong>{fileName}</strong>
                  <span>{entries.length} 个可导入词条</span>
                </div>
                {headers.length ? (
                  <span className="import-headers">识别字段：{headers.join(' / ')}</span>
                ) : null}
                {mappingSummary ? (
                  <span className="import-headers">列名映射：{mappingSummary}</span>
                ) : null}
              </div>
            ) : null}

            {parseErrors.length ? (
              <div className="parse-errors">
                <strong>解析提示</strong>
                <ul>
                  {parseErrors.map((message) => <li key={message}>{message}</li>)}
                </ul>
              </div>
            ) : null}

            <div className="create-entry-list">
              {entries.length ? (
                entries.map((entry, index) => (
                  <div className="create-entry-row" key={entry.id}>
                    <span className="create-entry-index">{String(index + 1).padStart(2, '0')}</span>
                    <div className="create-entry-word">
                      <strong>{entry.word}</strong>
                      <span>{entry.phonetic} {entry.partOfSpeech}</span>
                    </div>
                    <p>{entry.meanings.join('；')}</p>
                    <div className="create-entry-actions">
                      <IconButton label="编辑词条" icon={Pencil} size="sm" onClick={() => openEditEntry(entry)} />
                      <IconButton
                        label="删除词条"
                        icon={Trash2}
                        size="sm"
                        onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))}
                      />
                    </div>
                  </div>
                ))
              ) : (
                <div className="create-entry-empty">
                  <FileSpreadsheet size={22} />
                  <strong>还没有词条</strong>
                  <p>上传表格或手动添加。也可以先创建空词库，再进入详情页继续维护。</p>
                </div>
              )}
            </div>
          </section>
        </div>

        <aside className="creation-side">
          <section className="panel compact-panel">
            <div className="panel-header">
              <div>
                <h2>创建摘要</h2>
                <p>保存前请检查词库配置。</p>
              </div>
            </div>
            <dl className="create-summary-list">
              <div><dt>学科</dt><dd>{form.subject === 'english' ? '英语' : '语文'}</dd></div>
              <div><dt>类型</dt><dd>{visibility === 'public' ? '公共词库草稿' : '个人词库'}</dd></div>
              <div><dt>名称</dt><dd>{form.name || '未填写'}</dd></div>
              <div><dt>词条</dt><dd>{entries.length} 个</dd></div>
              <div><dt>标签</dt><dd>{form.tags.length ? form.tags.join('、') : '暂无标签'}</dd></div>
            </dl>
            <div className="template-format">
              <strong>Excel 字段规范</strong>
              <p>单词、音标、词性、词义、例句、例句翻译。单词和词义为必填列。</p>
            </div>
          </section>
        </aside>
      </div>

      <Modal
        open={Boolean(entryDraft)}
        title="编辑导入词条"
        description="词形在同一词库内不能重复。"
        width="lg"
        onClose={() => setEntryDraft(null)}
        footer={
          <>
            <Button onClick={() => setEntryDraft(null)}>取消</Button>
            <Button variant="primary" onClick={saveEntry}>应用词条</Button>
          </>
        }
      >
        {entryDraft ? (
          <div className="form-stack">
            {entryError ? <InlineError>{entryError}</InlineError> : null}
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
                />
              </Field>
              <Field label="词性">
                <TextInput
                  value={entryDraft.partOfSpeech}
                  onChange={(event) => setEntryDraft({ ...entryDraft, partOfSpeech: event.target.value })}
                />
              </Field>
            </div>
            <Field label="词义" hint="多个词义使用换行分隔">
              <textarea
                className="text-area"
                rows={3}
                value={entryDraft.meanings.join('\n')}
                onChange={(event) => setEntryDraft({ ...entryDraft, meanings: event.target.value.split('\n') })}
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
                  onChange={(event) => setEntryDraft({ ...entryDraft, exampleTranslation: event.target.value })}
                />
              </Field>
            </div>
          </div>
        ) : null}
      </Modal>
    </main>
  )
}
