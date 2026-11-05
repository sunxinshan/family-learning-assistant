import { useEffect, useMemo, useState } from 'react'
import { Field, SelectInput, TextInput } from '../../components/ui'
import { TaskAdvancedSettings, TaskDictationSettings } from '../task/TaskSettingsFields'
import { TaskWordPicker } from '../task/TaskWordPicker'
import type {
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
    // 词库先以摘要形式到达（entries 为空），完整词条加载后需要重新按草稿回填勾选。
  }, [selectedLibrary?.id, selectedLibrary?.entries.length])

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

  const selectedEntries = selectedLibrary
    ? selectedLibrary.entries.filter((entry) => selectedIds.has(entry.id))
    : []
  const hintEntry = selectedEntries[0]
  const hintPreview = !draft?.dictation
    ? ''
    : !hintEntry
      ? '勾选词条后可预览朗读时显示的提示'
      : draft.dictation.hint === 'phonetic'
        ? hintEntry.phonetic || '该词条暂未填写拼音/音标'
        : hintEntry.meanings.join('；')

  return (
    <div className="task-action-editor">
      <div className="form-stack">
        <Field label="任务名称">
          <TextInput
            value={draft.name}
            onChange={(event) => update({ name: event.target.value })}
            placeholder="例如：语文词语听写 · 第三单元"
          />
        </Field>

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
          <Field label="内容来源" hint="个人词库或已发布的公共词库">
            <SelectInput
              value={selectedLibrary?.id ?? ''}
              onChange={(event) => applyLibrary(event.target.value)}
            >
              {filteredLibraries.map((library) => (
                <option key={library.id} value={library.id}>
                  {library.subject === 'english' ? '英语' : '语文'} · {library.name} ·{' '}
                  {library.entries.length} 个词条
                  {library.visibility === 'public' ? ' · 公共' : ' · 个人'}
                </option>
              ))}
            </SelectInput>
          </Field>
        </div>

        {selectedLibrary ? (
          <TaskWordPicker
            library={selectedLibrary}
            selectionText={selectionText}
            selectedIds={selectedIds}
            invalidTokens={selection.invalidTokens}
            ariaLabel="确认面板选择词条序号"
            onSelectionTextChange={updateSelection}
            onToggleEntry={toggleEntry}
            onToggleAll={setAll}
          />
        ) : null}

        <TaskAdvancedSettings
          type={draft.type}
          mode={draft.mode}
          selectedCount={selection.entries.length}
          wordsPerGroup={draft.wordsPerGroup}
          repeatUntilCorrect={draft.repeatUntilCorrect}
          onModeChange={(mode) =>
            update({
              mode,
              wordsPerGroup:
                mode === 'fixed'
                  ? selectedIds.size
                  : Math.min(draft.wordsPerGroup, Math.max(selectedIds.size, 1)),
            })
          }
          onWordsPerGroupChange={(wordsPerGroup) => update({ wordsPerGroup })}
          onRepeatUntilCorrectChange={(repeatUntilCorrect) => update({ repeatUntilCorrect })}
        />

        {draft.type === 'dictation' && draft.dictation ? (
          <TaskDictationSettings
            subject={selectedLibrary?.subject ?? 'english'}
            dictation={draft.dictation}
            hintPreview={hintPreview}
            onChange={(changes) => update({ dictation: { ...draft.dictation!, ...changes } })}
          />
        ) : null}

      </div>
    </div>
  )
}
