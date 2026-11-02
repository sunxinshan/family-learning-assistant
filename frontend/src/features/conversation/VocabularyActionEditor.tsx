import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  Button,
  Field,
  IconButton,
  InlineError,
  SelectInput,
  TagInput,
  TextInput,
} from '../../components/ui'
import type { PendingAction, Subject, VocabularyDraft, WordEntry } from '../../types/domain'

const blankEntry = (): WordEntry => ({
  id: `word-${crypto.randomUUID()}`,
  word: '',
  phonetic: '',
  partOfSpeech: '',
  meanings: [''],
  example: '',
  exampleTranslation: '',
})

export const VocabularyActionEditor = ({
  action,
  onChange,
  onValidityChange,
}: {
  action: PendingAction
  onChange: (draft: VocabularyDraft) => void
  onValidityChange: (valid: boolean) => void
}) => {
  const draft = action.payload.vocabularyDraft
  const [entryDraft, setEntryDraft] = useState<WordEntry | null>(null)
  const [entryEditingId, setEntryEditingId] = useState<string | null>(null)
  const [entryError, setEntryError] = useState('')

  const entries = draft?.entries ?? []
  const invalid =
    !draft ||
    !draft.name.trim() ||
    entries.length === 0 ||
    entries.some((entry) => !entry.word.trim() || !entry.meanings.some((meaning) => meaning.trim())) ||
    new Set(entries.map((entry) => entry.word.trim().toLowerCase())).size !== entries.length

  useEffect(() => {
    onValidityChange(!invalid)
  }, [invalid, onValidityChange])

  if (!draft) return null

  const update = (changes: Partial<VocabularyDraft>) => {
    onChange({ ...draft, ...changes })
  }

  const openNewEntry = () => {
    setEntryDraft(blankEntry())
    setEntryEditingId(null)
    setEntryError('')
  }

  const openEditEntry = (entry: WordEntry) => {
    setEntryDraft({ ...entry, meanings: [...entry.meanings] })
    setEntryEditingId(entry.id)
    setEntryError('')
  }

  const saveEntry = () => {
    if (!entryDraft) return
    const word = entryDraft.word.trim()
    const meanings = entryDraft.meanings.map((meaning) => meaning.trim()).filter(Boolean)
    if (!word || !meanings.length) {
      setEntryError('单词和至少一个词义为必填项')
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
    const normalized = {
      ...entryDraft,
      word,
      meanings,
      phonetic: entryDraft.phonetic.trim(),
      partOfSpeech: entryDraft.partOfSpeech.trim(),
      example: entryDraft.example.trim(),
      exampleTranslation: entryDraft.exampleTranslation.trim(),
    }
    update({
      entries: entryEditingId
        ? entries.map((entry) => (entry.id === entryEditingId ? normalized : entry))
        : [...entries, normalized],
    })
    setEntryDraft(null)
    setEntryEditingId(null)
  }

  return (
    <div className="task-action-editor vocabulary-action-editor">
      <div className="form-stack">
        <div className="form-grid-two">
          <Field label="学科">
            <SelectInput
              value={draft.subject}
              onChange={(event) => update({ subject: event.target.value as Subject })}
            >
              <option value="english">英语</option>
              <option value="chinese">语文</option>
            </SelectInput>
          </Field>
          <Field label="词库名称">
            <TextInput
              value={draft.name}
              onChange={(event) => update({ name: event.target.value })}
            />
          </Field>
        </div>
        <Field label="描述">
          <textarea
            className="text-area"
            rows={2}
            value={draft.description}
            onChange={(event) => update({ description: event.target.value })}
          />
        </Field>
        <Field label="标签" hint="按 Enter 或逗号添加自定义标签">
          <TagInput
            value={draft.tags}
            onChange={(tags) => update({ tags })}
          />
        </Field>

        <div className="task-action-vocab-heading">
          <div>
            <strong>词条内容</strong>
            <span>可添加、编辑或删除所有词条字段。</span>
          </div>
          <Button size="sm" icon={Plus} onClick={openNewEntry}>添加词条</Button>
        </div>

        <div className="task-action-vocab-list">
          {entries.map((entry, index) => (
            <div className="task-action-vocab-row" key={entry.id}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <div>
                <strong>{entry.word || '未命名词条'}</strong>
                <small>{entry.phonetic} {entry.partOfSpeech}</small>
                <p>{entry.meanings.join('；') || '缺少词义'}</p>
              </div>
              <div className="task-action-vocab-actions">
                <IconButton label="编辑词条" icon={Pencil} size="sm" onClick={() => openEditEntry(entry)} />
                <IconButton
                  label="删除词条"
                  icon={Trash2}
                  size="sm"
                  onClick={() => update({ entries: entries.filter((item) => item.id !== entry.id) })}
                />
              </div>
            </div>
          ))}
          {!entries.length ? (
            <div className="task-action-vocab-empty">还没有词条，请添加至少一个词条。</div>
          ) : null}
        </div>

        {entryDraft ? (
          <div className="task-action-entry-editor">
            <div className="task-action-editor-note">
              {entryEditingId ? '编辑词条' : '添加词条'}
            </div>
            {entryError ? <InlineError>{entryError}</InlineError> : null}
            <div className="form-grid-three">
              <Field label="单词">
                <TextInput
                  value={entryDraft.word}
                  onChange={(event) => setEntryDraft({ ...entryDraft, word: event.target.value })}
                  autoFocus
                />
              </Field>
              <Field label="音标/拼音">
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
                rows={2}
                value={entryDraft.meanings.join('\n')}
                onChange={(event) => setEntryDraft({ ...entryDraft, meanings: event.target.value.split('\n') })}
              />
            </Field>
            <div className="form-grid-two">
              <Field label="例句">
                <textarea
                  className="text-area"
                  rows={2}
                  value={entryDraft.example}
                  onChange={(event) => setEntryDraft({ ...entryDraft, example: event.target.value })}
                />
              </Field>
              <Field label="例句翻译">
                <textarea
                  className="text-area"
                  rows={2}
                  value={entryDraft.exampleTranslation}
                  onChange={(event) => setEntryDraft({ ...entryDraft, exampleTranslation: event.target.value })}
                />
              </Field>
            </div>
            <div className="task-action-entry-footer">
              <Button size="sm" onClick={() => setEntryDraft(null)}>取消编辑</Button>
              <Button size="sm" variant="primary" onClick={saveEntry}>应用词条</Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
