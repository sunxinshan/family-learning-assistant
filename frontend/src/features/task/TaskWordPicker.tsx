import { ListChecks } from 'lucide-react'
import { Badge, Button, InlineError, TextInput } from '../../components/ui'
import type { Vocabulary } from '../../types/domain'

/**
 * 任务创建（页面 / Agent 确认面板）共用的词条选择区。
 * 保持同一套标题、计数、输入方式、扁平列表和序号展示。
 */
export const TaskWordPicker = ({
  library,
  selectionText,
  selectedIds,
  invalidTokens,
  ariaLabel = '选择词条序号',
  onSelectionTextChange,
  onToggleEntry,
  onToggleAll,
}: {
  library: Vocabulary
  selectionText: string
  selectedIds: Set<string>
  invalidTokens: string[]
  ariaLabel?: string
  onSelectionTextChange: (value: string) => void
  onToggleEntry: (entryId: string) => void
  onToggleAll: () => void
}) => {
  const allSelected =
    library.entries.length > 0 && selectedIds.size === library.entries.length

  return (
    <div className="word-picker-panel">
      <div className="word-picker-heading">
        <div>
          <h3>选择词库词条</h3>
          <p>序号输入与勾选状态实时同步；支持 all、2-10、4,8 等表达。</p>
        </div>
        <Badge tone={allSelected ? 'success' : 'neutral'}>
          已选 {selectedIds.size} / {library.entries.length}
        </Badge>
      </div>
      <div className="word-selection-row">
        <TextInput
          value={selectionText}
          onChange={(event) => onSelectionTextChange(event.target.value)}
          placeholder="例如：2-10, 4, 8"
          aria-label={ariaLabel}
        />
        <Button size="sm" icon={ListChecks} onClick={onToggleAll}>
          {allSelected ? '取消全选' : '全选'}
        </Button>
      </div>
      {invalidTokens.length ? (
        <InlineError>
          无法识别：{invalidTokens.join('、')}。请输入有效序号，例如 2-10, 4, 8。
        </InlineError>
      ) : null}
      <div className="word-picker-list">
        {library.entries.map((entry, index) => (
          <label
            key={entry.id}
            className={`word-picker-row ${selectedIds.has(entry.id) ? 'is-selected' : ''}`}
          >
            <input
              type="checkbox"
              checked={selectedIds.has(entry.id)}
              onChange={() => onToggleEntry(entry.id)}
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
  )
}
