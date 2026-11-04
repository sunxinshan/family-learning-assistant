import { ChevronDown, Headphones, Info, Settings2 } from 'lucide-react'
import { Checkbox, Field, SelectInput, TextInput } from '../../components/ui'
import type { DictationConfig, Subject, TaskMode, TaskType } from '../../types/domain'
import { taskModeLabel, taskTypeLabel } from '../../utils/format'

/**
 * 任务创建（页面 / Agent 确认面板）共用的高级设置与听写设置。
 * 两处必须保持同一套字段、文案和顺序，避免同一个任务在不同入口看到不同配置。
 */
export const TaskAdvancedSettings = ({
  type,
  mode,
  selectedCount,
  wordsPerGroup,
  repeatUntilCorrect,
  onModeChange,
  onWordsPerGroupChange,
  onRepeatUntilCorrectChange,
}: {
  type: TaskType
  mode: TaskMode
  selectedCount: number
  wordsPerGroup: number
  repeatUntilCorrect: boolean
  onModeChange: (mode: TaskMode) => void
  onWordsPerGroupChange: (value: number) => void
  onRepeatUntilCorrectChange: (checked: boolean) => void
}) => {
  const fixed = mode === 'fixed'
  const effectiveWordsPerGroup = Math.min(
    Math.max(wordsPerGroup, 1),
    Math.max(selectedCount, 1),
  )
  const totalGroups = selectedCount > 0 ? Math.ceil(selectedCount / effectiveWordsPerGroup) : 0

  return (
    <details className="advanced-settings">
      <summary>
        <span className="advanced-settings-title">
          <Settings2 size={16} />
          高级设置
        </span>
        <span className="advanced-settings-summary">
          {taskTypeLabel(type)} · {taskModeLabel(mode)} ·{' '}
          {fixed ? '固定内容' : `${totalGroups} 组`} · 强制重做{repeatUntilCorrect ? '开' : '关'}
        </span>
        <ChevronDown size={16} className="advanced-settings-chevron" />
      </summary>
      <div className="advanced-settings-body">
        <div className="form-grid-two">
          <Field label="学习类型">
            <SelectInput value={type} disabled aria-readonly="true">
              <option value="dictation">听写练习（V1 唯一正式类型）</option>
            </SelectInput>
          </Field>
          <Field label="任务模式">
            <SelectInput
              value={mode}
              onChange={(event) => onModeChange(event.target.value as TaskMode)}
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
              value={wordsPerGroup}
              onChange={(event) => onWordsPerGroupChange(Number(event.target.value))}
            />
          </Field>
        )}
        <Checkbox
          checked={repeatUntilCorrect}
          onChange={onRepeatUntilCorrectChange}
          label="开启强制重做：每个词连续拼对 2 次才进入下一个词，错题留在本组继续练"
        />
      </div>
    </details>
  )
}

export const TaskDictationSettings = ({
  subject,
  dictation,
  hintPreview,
  onChange,
}: {
  subject: Subject
  dictation: DictationConfig
  hintPreview: string
  onChange: (changes: Partial<DictationConfig>) => void
}) => {
  const speechEnabled = dictation.speechEnabled !== false
  const english = subject === 'english'

  return (
    <div className="dictation-config-box">
      <div className="dictation-config-heading">
        <Headphones size={16} />
        <div>
          <strong>听写设置</strong>
          <span>这些设置会随任务保存，并作用于听写练习页面。</span>
        </div>
      </div>
      <Checkbox
        checked={speechEnabled}
        onChange={(checked) => onChange({ speechEnabled: checked })}
        label="开启朗读：练习时自动读出词语；关闭后练习页不发声，只在答错时提供朗读按钮"
      />
      <div className="form-grid-two">
        <Field label="听写方式">
          <SelectInput
            value={dictation.mode}
            onChange={(event) => onChange({ mode: event.target.value as DictationConfig['mode'] })}
          >
            <option value="online">线上听写 · 页面输入并自动判分</option>
            <option value="offline">线下听写 · 用户勾选错误项</option>
          </SelectInput>
        </Field>
        <Field label="播放方式">
          <SelectInput
            value={dictation.playbackMode}
            disabled={!speechEnabled}
            onChange={(event) =>
              onChange({ playbackMode: event.target.value as DictationConfig['playbackMode'] })
            }
          >
            <option value="manual">手动播放</option>
            <option value="auto">自动播放</option>
          </SelectInput>
        </Field>
      </div>
      <div className="form-grid-three">
        {dictation.playbackMode === 'auto' && speechEnabled ? (
          <Field label="自动播放间隔" hint="练习页面显示倒计时">
            <TextInput
              type="number"
              min={2}
              max={60}
              value={dictation.intervalSeconds}
              onChange={(event) => onChange({ intervalSeconds: Number(event.target.value) })}
            />
          </Field>
        ) : <div />}
        <Field label="朗读次数">
          <TextInput
            type="number"
            min={1}
            max={5}
            disabled={!speechEnabled}
            value={dictation.repeatCount}
            onChange={(event) => onChange({ repeatCount: Number(event.target.value) })}
          />
        </Field>
        <Field label="朗读内容">
          <SelectInput
            value={dictation.hint}
            disabled={!speechEnabled || !english}
            onChange={(event) => onChange({ hint: event.target.value as DictationConfig['hint'] })}
          >
            <option value="phonetic">
              {english ? '英语单词' : '词语发音（直接读出）'}
            </option>
            {english ? <option value="meaning">中文释义</option> : null}
          </SelectInput>
        </Field>
      </div>
      <div className="hint-preview">
        <span>页面提示预览</span>
        <strong>{hintPreview}</strong>
      </div>
    </div>
  )
}
