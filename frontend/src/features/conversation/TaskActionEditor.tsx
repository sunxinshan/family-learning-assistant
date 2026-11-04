import { Info, ListChecks } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Badge, Field, InlineError, SelectInput, TextInput } from '../../components/ui'
import { TaskAdvancedSettings, TaskDictationSettings } from '../task/TaskSettingsFields'
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
  const unselectedEntries = selectedLibrary
    ? selectedLibrary.entries.filter((entry) => !selectedIds.has(entry.id))
    : []
  const groupSize = fixed ? Math.max(selectedEntries.length, 1) : Math.max(draft.wordsPerGroup, 1)
  const selectedGroups = Array.from(
    { length: Math.ceil(selectedEntries.length / groupSize) },
    (_, groupIndex) => {
      const entries = selectedEntries.slice(
        groupIndex * groupSize,
        (groupIndex + 1) * groupSize,
      )
      return {
        groupIndex: groupIndex + 1,
        entries,
        start: groupIndex * groupSize + 1,
        end: groupIndex * groupSize + entries.length,
      }
    },
  )
  const originalIndex = (entryId: string) =>
    (selectedLibrary?.entries.findIndex((entry) => entry.id === entryId) ?? -1) + 1
  const hintEntry = selectedEntries[0]
  const hintPreview = !draft?.dictation
    ? ''
    : !hintEntry
      ? '勾选词条后可预览朗读时显示的提示'
      : draft.dictation.hint === 'phonetic'
        ? hintEntry.phonetic || '该词条暂未填写拼音/音标'
        : hintEntry.meanings.join('；')

  const entryRow = (entry: NonNullable<typeof selectedLibrary>['entries'][number]) => (
    <label
      key={entry.id}
      className={`task-action-word-row ${selectedIds.has(entry.id) ? 'is-selected' : ''}`}
    >
      <input
        type="checkbox"
        checked={selectedIds.has(entry.id)}
        onChange={() => toggleEntry(entry.id)}
      />
      <span>{String(originalIndex(entry.id)).padStart(2, '0')}</span>
      <strong>{entry.word}</strong>
      <small>{entry.meanings.join('；')}</small>
    </label>
  )

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
            {selectedGroups.map((group) => (
              <section className="task-action-group-section" key={group.groupIndex}>
                <header className="task-action-group-heading">
                  <strong>第 {group.groupIndex} 组</strong>
                  <span>
                    词条 {group.start}-{group.end} · 组内 {group.entries.length}/{groupSize}
                  </span>
                </header>
                <div>{group.entries.map((entry) => entryRow(entry))}</div>
              </section>
            ))}
            {unselectedEntries.length ? (
              <details className="task-action-unselected" open={!selectedEntries.length}>
                <summary>未选择词条 · {unselectedEntries.length} 项</summary>
                <div>{unselectedEntries.map((entry) => entryRow(entry))}</div>
              </details>
            ) : null}
            {!selectedEntries.length && !unselectedEntries.length ? (
              <div className="task-action-word-empty">当前词库没有词条。</div>
            ) : null}
          </div>
        </div>

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

        <div className="info-note">
          <Info size={15} />
          {fixed
            ? '固定任务创建后不能修改学习内容；需要调整时请删除并重新创建。'
            : '长期任务会保存创建时的词库快照，后续修改原词库不会影响已有任务。'}
        </div>
      </div>
    </div>
  )
}
