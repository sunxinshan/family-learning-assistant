import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Clock3,
  FileSpreadsheet,
  LoaderCircle,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
  Wrench,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Badge, Button } from '../../components/ui'
import type {
  ChatMessage,
  PendingAction,
  ToolExecution,
  Vocabulary,
  VocabularyDraft,
} from '../../types/domain'
import { TaskActionEditor } from './TaskActionEditor'
import { VocabularyActionEditor } from './VocabularyActionEditor'
import { formatFileSize } from '../../utils/format'

export const AgentAvatar = () => (
  <span className="agent-avatar" aria-hidden="true">
    <Sparkles size={15} />
  </span>
)

export const UserAvatar = ({ name }: { name: string }) => (
  <span className="user-avatar" aria-hidden="true">
    {name.slice(0, 1)}
  </span>
)

const redact = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(redact)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        /key|token|cookie|password|secret/i.test(key) ? '[已脱敏]' : redact(item),
      ]),
    )
  }
  return value
}

const ExecutionCard = ({ execution }: { execution: ToolExecution }) => {
  const [open, setOpen] = useState(false)
  const statusIcon =
    execution.status === 'running' ? (
      <LoaderCircle className="spin" size={14} />
    ) : execution.status === 'success' ? (
      <CheckCircle2 size={14} />
    ) : (
      <XCircle size={14} />
    )

  return (
    <div className={`execution-card execution-${execution.status}`}>
      <button type="button" className="execution-head" onClick={() => setOpen((value) => !value)}>
        <span className="execution-status-icon">
          {statusIcon}
        </span>
        <span className="execution-name">
          <strong>{execution.label}</strong>
          <code>{execution.tool}</code>
        </span>
        <span className="execution-meta">
          {execution.durationMs !== undefined ? `${execution.durationMs} ms` : '执行中'}
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open ? (
        <div className="execution-body">
          <div className="execution-block">
            <span className="execution-label">执行状态</span>
            <span>{execution.status === 'running' ? '执行中' : execution.status === 'success' ? '成功' : '失败'}</span>
          </div>
          <div className="execution-block">
            <span className="execution-label">Tool 参数</span>
            <pre>{JSON.stringify(redact(execution.args), null, 2)}</pre>
          </div>
          {execution.result ? (
            <div className="execution-block">
              <span className="execution-label">执行结果</span>
              <pre>{execution.result}</pre>
            </div>
          ) : null}
          {execution.error ? (
            <div className="execution-block execution-error">
              <span className="execution-label">错误信息</span>
              <pre>{execution.error}</pre>
            </div>
          ) : null}
          <span className="execution-security">
            <ShieldAlert size={12} />
            敏感字段已自动脱敏
          </span>
        </div>
      ) : null}
    </div>
  )
}

export const ActionPreview = ({
  action,
  libraries,
  onConfirm,
  onCancel,
  disabled = false,
}: {
  action: PendingAction
  libraries: Vocabulary[]
  onConfirm: (action: PendingAction) => void
  onCancel: (action: PendingAction) => void
  disabled?: boolean
}) => {
  const [editedDraft, setEditedDraft] = useState(action.payload.taskDraft)
  const [editedVocabulary, setEditedVocabulary] = useState<VocabularyDraft | undefined>(
    action.payload.vocabularyDraft,
  )
  const [taskEditorValid, setTaskEditorValid] = useState(true)
  const [vocabularyEditorValid, setVocabularyEditorValid] = useState(true)
  const editableTask = action.operation === 'create_task' && Boolean(editedDraft)
  const editableVocabulary =
    (action.operation === 'create_vocabulary' || action.operation === 'import_vocabulary') &&
    Boolean(editedVocabulary)

  useEffect(() => {
    setEditedDraft(action.payload.taskDraft)
    setEditedVocabulary(action.payload.vocabularyDraft)
    setTaskEditorValid(true)
    setVocabularyEditorValid(true)
  }, [action.id])

  const effectiveAction: PendingAction =
    editableTask && editedDraft
      ? {
          ...action,
          target: editedDraft.name,
          payload: { ...action.payload, taskDraft: editedDraft },
        }
      : editableVocabulary && editedVocabulary
        ? {
            ...action,
            target: editedVocabulary.name,
            payload: { ...action.payload, vocabularyDraft: editedVocabulary },
          }
        : action

  return (
    <section className={`action-preview ${action.danger ? 'action-danger' : ''}`}>
      <header className="action-preview-head">
        <div className="action-preview-icon">
          {action.danger ? <ShieldAlert size={17} /> : <Wrench size={17} />}
        </div>
        <div className="action-preview-title">
          <div>
            {action.executed ? (
              <Badge tone="success">已处理</Badge>
            ) : (
              <Badge tone={action.danger ? 'danger' : 'neutral'}>
                {action.stage === 2 ? '二次确认' : '等待确认'}
              </Badge>
            )}
          </div>
          <h3>{action.title}</h3>
          <p>{action.description}</p>
        </div>
      </header>

      <div className="action-target">
        <span>目标对象</span>
        <strong>{effectiveAction.target}</strong>
      </div>

      {editableTask && editedDraft ? (
        <div className="task-action-editor-wrap">
          <div className="task-action-editor-note">
            任务确认前可继续修改全部配置；勾选与序号输入保持同步。
          </div>
          <TaskActionEditor
            action={effectiveAction}
            libraries={libraries}
            onChange={setEditedDraft}
            onValidityChange={setTaskEditorValid}
          />
        </div>
      ) : editableVocabulary && editedVocabulary ? (
        <div className="task-action-editor-wrap">
          <div className="task-action-editor-note">
            词库确认前可继续修改学科、名称、描述、标签和全部词条。
          </div>
          <VocabularyActionEditor
            action={effectiveAction}
            onChange={setEditedVocabulary}
            onValidityChange={setVocabularyEditorValid}
          />
        </div>
      ) : (
        <>
          {action.fields.length > 0 ? (
            <dl className="action-fields">
              {action.fields.map((field) => (
                <div key={field.label}>
                  <dt>{field.label}</dt>
                  <dd>{field.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {action.diff?.length ? (
            <div className="action-diff">
              <div className="diff-column diff-before">
                <span>修改前</span>
                {action.diff.map((item) => (
                  <div key={item.label}>
                    <small>{item.label}</small>
                    <strong>{item.before}</strong>
                  </div>
                ))}
              </div>
              <div className="diff-arrow">→</div>
              <div className="diff-column diff-after">
                <span>修改后</span>
                {action.diff.map((item) => (
                  <div key={item.label}>
                    <small>{item.label}</small>
                    <strong>{item.after}</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}

      <div className="action-impact">
        <AlertCircle size={15} />
        <span>{action.impact}</span>
      </div>

      <footer className="action-footer">
        <span>确认前不会写入业务数据</span>
        <div>
          <Button size="sm" onClick={() => onCancel(action)} disabled={disabled || action.executed}>
            取消
          </Button>
          <Button
            size="sm"
            variant={action.danger ? 'danger' : 'primary'}
            onClick={() => onConfirm(effectiveAction)}
            disabled={
              disabled ||
              action.executed ||
              (editableTask && !taskEditorValid) ||
              (editableVocabulary && !vocabularyEditorValid)
            }
            icon={action.danger ? ShieldAlert : Check}
          >
            {action.confirmLabel}
          </Button>
        </div>
      </footer>
    </section>
  )
}

const FileMessage = ({ message }: { message: ChatMessage }) => (
  <div className="chat-file-card">
    <div className="chat-file-icon">
      <FileSpreadsheet size={18} />
    </div>
    <div>
      <strong>{message.file?.name}</strong>
      <span>
        {message.file ? formatFileSize(message.file.size) : ''}
        {message.file?.type ? ` · ${message.file.type}` : ''}
      </span>
    </div>
    <Badge tone="success">已上传</Badge>
  </div>
)

export const ChatMessageItem = ({
  message,
  userName,
  libraries,
  busy,
  onConfirm,
  onCancel,
  onQuickReply,
}: {
  message: ChatMessage
  userName: string
  libraries: Vocabulary[]
  busy: boolean
  onConfirm: (action: PendingAction) => void
  onCancel: (action: PendingAction) => void
  onQuickReply: (text: string) => void
}) => {
  const time = useMemo(
    () =>
      new Intl.DateTimeFormat('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date(message.createdAt)),
    [message.createdAt],
  )

  if (message.role === 'user') {
    return (
      <article className="chat-row chat-row-user">
        <div className="chat-user-content">
          {message.kind === 'file' ? <FileMessage message={message} /> : <p>{message.content}</p>}
          <span className="message-time">{time}</span>
        </div>
        <UserAvatar name={userName} />
      </article>
    )
  }

  // tool_call 与 tool_result 成对保存，界面只渲染 tool_result 的执行卡片。
  if (message.kind === 'tool_call') return null

  if (message.kind === 'execution' && message.execution) {
    return (
      <article className="chat-row chat-row-agent chat-row-tool">
        <span className="tool-avatar">
          <TerminalSquare size={14} />
        </span>
        <div className="chat-agent-content">
          <ExecutionCard execution={message.execution} />
        </div>
      </article>
    )
  }

  if (message.kind === 'action_preview' && message.action) {
    return (
      <article className="chat-row chat-row-agent">
        <AgentAvatar />
        <div className="chat-agent-content">
          <ActionPreview
            action={message.action}
            libraries={libraries}
            onConfirm={onConfirm}
            onCancel={onCancel}
            disabled={busy}
          />
          <span className="message-time">{time}</span>
        </div>
      </article>
    )
  }

  if (message.kind === 'error') {
    return (
      <article className="chat-row chat-row-agent">
        <span className="agent-avatar agent-avatar-error">
          <AlertCircle size={15} />
        </span>
        <div className="chat-agent-content">
          <div className="chat-error-card">
            <strong>操作提示</strong>
            <p>{message.content}</p>
          </div>
          <span className="message-time">{time}</span>
        </div>
      </article>
    )
  }

  if (message.kind === 'progress') {
    return (
      <article className="chat-progress-line">
        {message.content.includes('完成') ? <Check size={14} /> : <Circle size={8} className="progress-dot" />}
        <span>{message.content}</span>
        <small>{time}</small>
      </article>
    )
  }

  return (
    <article className="chat-row chat-row-agent">
      <AgentAvatar />
      <div className="chat-agent-content">
        <div className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
        {message.links?.length ? (
          <div className="message-links">
            {message.links.map((link) => (
              <Link key={`${link.to}-${link.label}`} to={link.to} className="message-link">
                {link.label}
                <ChevronRight size={14} />
              </Link>
            ))}
          </div>
        ) : null}
        {message.quickReplies?.length ? (
          <div className="quick-replies">
            {message.quickReplies.map((reply) => (
              <button key={reply} type="button" onClick={() => onQuickReply(reply)} disabled={busy}>
                {reply}
              </button>
            ))}
          </div>
        ) : null}
        <span className="message-time">
          <Clock3 size={11} />
          {time}
        </span>
      </div>
    </article>
  )
}
