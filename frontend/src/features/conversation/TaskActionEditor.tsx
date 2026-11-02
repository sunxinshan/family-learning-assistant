import { ListChecks } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  Badge,
  Checkbox,
  Field,
  InlineError,
  SelectInput,
  TextInput,
} from '../../components/ui'
import type {
  DictationHint,
  DictationMode,
  PlaybackMode,
  PendingAction,
  Subject,
  TaskDraft,
  Vocabulary,
} from '../../types/domain'
import { formatEntrySelection, parseEntrySelection } from '../../utils/selection'

export const TaskActionEditor = ({
  action,
  libraries,
  onChange,
  onValidityChange,
}: {
  action: PendingAction
  libraries: Vocabulary[]
  onChange: (draft: TaskDraft) => void
  onValidityChange: (valid: boolean) => void
}) => {
  const draft = action.payload.taskDraft
  const initialSubject = libraries.find((library) => library.id === draft?.libraryId)?.subject ?? 'all'
  const [subjectFilter, setSubjectFilter] = useState<'all' | Subject>(initialSubject)
  const [selectionText, setSelectionText] = useState('')

  const filteredLibraries = useMemo(
    () => libraries.filter((library) => subjectFilter === 'all' || library.subject === subjectFilter),
    [libraries, subjectFilter],
  )
  const selectedLibrary =
    filteredLibraries.find((library) => library.id === draft?.libraryId) ?? filteredLibraries[0]

  useEffect(() => {
    if (!selectedLibrary || !draft) return
    setSubjectFilter(selectedLibrary.subject)
    setSelectionText(formatEntrySelection(draft.selectedEntryIds, selectedLibrary.entries))
  }, [selectedLibrary?.id])

  const selection = selectedLibrary && draft
    ? parseEntrySelection(selectionText, selectedLibrary.entries)
    : { entries: [], invalidTokens: [] as string[] }
  const selectedIds = new Set(selection.entries.map((entry) => entry.id))
  const fixed = draft?.mode === 'fixed'
  const allSelected = Boolean(
    selectedLibrary && selection.entries.length === selectedLibrary.entries.length,
  )
  const invalid =
    !draft ||
    !draft.name.trim() ||
    !selectedLibrary ||
    !selection.entries.length ||
    selection.invalidTokens.length > 0 ||
    (!fixed && draft.wordsPerGroup < 1) ||
    (!fixed && draft.wordsPerGroup > selection.entries.length)

  useEffect(() => {
    onValidityChange(!invalid)
  }, [invalid, onValidityChange])

  if (!draft) return null

  const update = (changes: Partial<TaskDraft>) => {
    onChange({ ...draft, ...changes })
  }

  const updateSelection = (expression: string) => {
    setSelectionText(expression)
    if (!selectedLibrary) return
    const parsed = parseEntrySelection(expression, selectedLibrary.entries)
    const count = parsed.entries.length
    onChange({
      ...draft,
      selectedEntryIds: parsed.entries.map((entry) => entry.id),
      targetCount: count,
      wordsPerGroup: fixed ? count : Math.min(Math.max(draft.wordsPerGroup, 1), Math.max(count, 1)),
    })
  }

  const applyLibrary = (libraryId: string) => {
    const library = libraries.find((item) => item.id === libraryId)
    if (!library) return
    const count = library.entries.length
    setSelectionText('')
    setSubjectFilter(library.subject)
    onChange({
      ...draft,
      libraryId,
      selectedEntryIds: [],
      targetCount: 0,
      wordsPerGroup: fixed ? count : Math.min(Math.max(draft.wordsPerGroup, 1), count),
      dictation: draft.dictation
        ? {
            ...draft.dictation,
            hint:
              draft.dictation.hint === 'phonetic' || library.subject === 'english'
                ? draft.dictation.hint
                : 'phonetic',
          }
        : draft.dictation,
    })
  }

  const toggleEntry = (entryId: string) => {
    if (!selectedLibrary) return
    const next = new Set(selectedIds)
    if (next.has(entryId)) next.delete(entryId)
    else next.add(entryId)
    const ids = selectedLibrary.entries.filter((entry) => next.has(entry.id)).map((entry) => entry.id)
    setSelectionText(formatEntrySelection(ids, selectedLibrary.entries))
    update({
      selectedEntryIds: ids,
      targetCount: ids.length,
      wordsPerGroup: fixed ? ids.length : Math.min(draft.wordsPerGroup, Math.max(ids.length, 1)),
    })
  }

  const setAll = () => {
    if (!selectedLibrary) return
    if (allSelected) {
      updateSelection('')
    } else {
      updateSelection(
        selectedLibrary.entries.length <= 1 ? '1' : `1-${selectedLibrary.entries.length}`,
      )
    }
  }

  return (
    <div className="task-action-editor">
      <div className="form-stack">
        <Field label="任务名称">
          <TextInput
            value={draft.name}
            onChange={(event) => update({ name: event.target.value })}
          />
        </Field>

        <div className="form-grid-two">
          <Field label="学习类型">
            <SelectInput value={draft.type} disabled aria-readonly="true">
              <option value="dictation">听写练习（V1 唯一正式类型）</option>
            </SelectInput>
          </Field>
          <Field label="任务模式">
            <SelectInput
              value={draft.mode}
              onChange={(event) => {
                const mode = event.target.value as 'fixed' | 'long_term'
                update({
                  mode,
                  wordsPerGroup:
                    mode === 'fixed'
                      ? selectedIds.size
                      : Math.min(draft.wordsPerGroup, Math.max(selectedIds.size, 1)),
                })
              }}
            >
              <option value="long_term">长期任务</option>
              <option value="fixed">固定任务</option>
            </SelectInput>
          </Field>
        </div>

        <div className="form-grid-two">
          <Field label="学科筛选">
            <SelectInput
              value={subjectFilter}
              onChange={(event) => {
                const value = event.target.value as 'all' | Subject
                setSubjectFilter(value)
                const next = libraries.filter(
                  (library) => value === 'all' || library.subject === value,
                )[0]
                if (next) applyLibrary(next.id)
              }}
            >
              <option value="all">全部学科</option>
              <option value="english">英语</option>
              <option value="chinese">语文</option>
            </SelectInput>
          </Field>
          <Field label="内容来源">
            <SelectInput
              value={selectedLibrary?.id ?? ''}
              onChange={(event) => applyLibrary(event.target.value)}
            >
              {filteredLibraries.map((library) => (
                <option key={library.id} value={library.id}>
                  {library.subject === 'english' ? '英语' : '语文'} · {library.name}
                </option>
              ))}
            </SelectInput>
          </Field>
        </div>

        <div className="task-action-word-picker">
          <div className="task-action-word-heading">
            <div>
              <strong>选择词库词条</strong>
              <span>输入序号或直接勾选，两种方式实时同步。</span>
            </div>
            <Badge tone={allSelected ? 'success' : 'neutral'}>
              已选 {selection.entries.length} / {selectedLibrary?.entries.length ?? 0}
            </Badge>
          </div>
          <div className="word-selection-row">
            <TextInput
              value={selectionText}
              onChange={(event) => updateSelection(event.target.value)}
              placeholder="例如：2-10, 4, 8"
              aria-label="确认面板选择词条序号"
            />
            <button type="button" className="button button-secondary button-sm" onClick={setAll}>
              <ListChecks size={14} />
              {allSelected ? '取消全选' : '全选'}
            </button>
          </div>
          {selection.invalidTokens.length ? (
            <InlineError>
              无法识别：{selection.invalidTokens.join('、')}
            </InlineError>
          ) : null}
          <div className="task-action-word-list">
            {selectedLibrary?.entries.map((entry, index) => (
              <label
                key={entry.id}
                className={`task-action-word-row ${selectedIds.has(entry.id) ? 'is-selected' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={selectedIds.has(entry.id)}
                  onChange={() => toggleEntry(entry.id)}
                />
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{entry.word}</strong>
                <small>{entry.meanings.join('；')}</small>
              </label>
            ))}
          </div>
        </div>

        {draft.mode === 'long_term' ? (
          <Field label="每组数量" hint={`学习数量自动等于已选 ${selection.entries.length} 项`}>
            <TextInput
              type="number"
              min={1}
              max={Math.max(selection.entries.length, 1)}
              value={draft.wordsPerGroup}
              onChange={(event) => update({ wordsPerGroup: Number(event.target.value) })}
            />
          </Field>
        ) : null}

        {draft.type === 'dictation' && draft.dictation ? (
          <div className="dictation-config-box compact-dictation-config">
            <div className="form-grid-two">
              <Field label="听写方式">
                <SelectInput
                  value={draft.dictation.mode}
                  onChange={(event) =>
                    update({
                      dictation: {
                        ...draft.dictation!,
                        mode: event.target.value as DictationMode,
                      },
                    })
                  }
                >
                  <option value="online">线上听写</option>
                  <option value="offline">线下听写</option>
                </SelectInput>
              </Field>
              <Field label="播放方式">
                <SelectInput
                  value={draft.dictation.playbackMode}
                  onChange={(event) =>
                    update({
                      dictation: {
                        ...draft.dictation!,
                        playbackMode: event.target.value as PlaybackMode,
                      },
                    })
                  }
                >
                  <option value="manual">手动播放</option>
                  <option value="auto">自动播放</option>
                </SelectInput>
              </Field>
            </div>
            <div className="form-grid-three">
              {draft.dictation.playbackMode === 'auto' ? (
                <Field label="播放间隔">
                  <TextInput
                    type="number"
                    min={2}
                    max={60}
                    value={draft.dictation.intervalSeconds}
                    onChange={(event) =>
                      update({
                        dictation: {
                          ...draft.dictation!,
                          intervalSeconds: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
              ) : <div />}
              <Field label="朗读次数">
                <TextInput
                  type="number"
                  min={1}
                  max={5}
                  value={draft.dictation.repeatCount}
                  onChange={(event) =>
                    update({
                      dictation: {
                        ...draft.dictation!,
                        repeatCount: Number(event.target.value),
                      },
                    })
                  }
                />
              </Field>
              <Field label="朗读内容">
                <SelectInput
                  value={draft.dictation.hint}
                  onChange={(event) =>
                    update({
                      dictation: {
                        ...draft.dictation!,
                        hint: event.target.value as DictationHint,
                      },
                    })
                  }
                >
                  <option value="phonetic">
                    {selectedLibrary?.subject === 'chinese' ? '语文拼音' : '英语音标'}
                  </option>
                  <option value="meaning">中文释义</option>
                </SelectInput>
              </Field>
            </div>
          </div>
        ) : null}

        <Checkbox
          checked={draft.repeatUntilCorrect}
          onChange={(checked) => update({ repeatUntilCorrect: checked })}
          label="强制重做：答对后才能进入下一组"
        />
      </div>
    </div>
  )
}
