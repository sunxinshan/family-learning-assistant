import {
  ArrowUp,
  BookOpenCheck,
  FileSpreadsheet,
  ListChecks,
  LoaderCircle,
  Paperclip,
  RotateCcw,
  Settings2,
  Sparkles,
  Trash2,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react'
import { conversationApi } from '../api/mockApi'
import { mockAgent } from '../api/mockAgent'
import { AgentAvatar, ChatMessageItem } from '../features/conversation/MessageComponents'
import { Badge, Button, IconButton, Modal } from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import type {
  AgentEvent,
  ChatMessage,
  PendingAction,
  ToolExecution,
} from '../types/domain'

const messageId = () => `message-${crypto.randomUUID()}`
const now = () => new Date().toISOString()

const suggestions = [
  {
    icon: ListChecks,
    title: '创建学习任务',
    description: '按词库和数量生成可执行任务',
    prompt: '创建一个固定的词汇任务，每天 8 个词',
  },
  {
    icon: FileSpreadsheet,
    title: '导入 Excel 词库',
    description: '解析字段、预览词条并确认保存',
    prompt: '我想导入一份 Excel 学习资料',
    upload: true,
  },
  {
    icon: BookOpenCheck,
    title: '查看学习记录',
    description: '了解正确率、错题和掌握情况',
    prompt: '查看我的学习记录和错题情况',
  },
]

export const ChatPage = () => {
  const { currentUser, showToast, refresh } = useAppStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [hydrated, setHydrated] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [busyStatus, setBusyStatus] = useState('正在理解你的需求')
  const [clearOpen, setClearOpen] = useState(false)
  const messagesRef = useRef<ChatMessage[]>([])
  const endRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const mountedUserIdRef = useRef<string | null>(null)
  const executionMessagesRef = useRef(new Map<string, string>())

  useEffect(() => {
    if (!currentUser) return
    const conversation = conversationApi.get(currentUser.id)
    setMessages(conversation.messages)
    messagesRef.current = conversation.messages
    setHydrated(true)
    mountedUserIdRef.current = currentUser.id
  }, [currentUser])

  useEffect(() => {
    if (!hydrated || !currentUser || mountedUserIdRef.current !== currentUser.id) return
    conversationApi.save(currentUser.id, messages)
  }, [messages, hydrated, currentUser])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy, busyStatus])

  useEffect(() => {
    if (!textareaRef.current) return
    textareaRef.current.style.height = 'auto'
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 152)}px`
  }, [input])

  const appendMessage = useCallback((message: ChatMessage) => {
    const next = [...messagesRef.current, message]
    messagesRef.current = next
    setMessages(next)
  }, [])

  const patchMessage = useCallback((targetId: string, updater: (message: ChatMessage) => ChatMessage) => {
    const next = messagesRef.current.map((message) =>
      message.id === targetId ? updater(message) : message,
    )
    messagesRef.current = next
    setMessages(next)
  }, [])

  const handleEvent = useCallback(
    (event: AgentEvent) => {
      if (event.type === 'progress') {
        setBusyStatus(event.data.message)
        return
      }
      if (event.type === 'message') {
        appendMessage({
          id: messageId(),
          role: 'assistant',
          kind: 'text',
          content: event.data.content,
          createdAt: now(),
          quickReplies: event.data.quickReplies,
          links: event.data.links,
        })
        return
      }
      if (event.type === 'tool_status') {
        const execution: ToolExecution = event.data
        const existingMessageId = executionMessagesRef.current.get(execution.id)
        if (existingMessageId) {
          patchMessage(existingMessageId, (message) => ({ ...message, execution }))
        } else {
          const newMessage: ChatMessage = {
            id: messageId(),
            role: 'tool',
            kind: 'execution',
            content: execution.label,
            createdAt: now(),
            execution,
          }
          executionMessagesRef.current.set(execution.id, newMessage.id)
          appendMessage(newMessage)
        }
        setBusyStatus(execution.label)
        return
      }
      if (event.type === 'confirmation_required') {
        appendMessage({
          id: messageId(),
          role: 'assistant',
          kind: 'action_preview',
          content: event.data.title,
          createdAt: now(),
          action: event.data,
        })
        setBusyStatus('等待你的确认')
        return
      }
      if (event.type === 'error') {
        appendMessage({
          id: messageId(),
          role: 'assistant',
          kind: 'error',
          content: event.data.message,
          createdAt: now(),
        })
        return
      }
      if (event.type === 'done') {
        setBusy(false)
      }
    },
    [appendMessage, patchMessage],
  )

  const runAgentRequest = useCallback(
    async (payload: { text: string; fileName?: string; fileSize?: number; fileType?: string }) => {
      if (!currentUser || busy) return
      setBusy(true)
      setBusyStatus('正在理解你的需求')
      executionMessagesRef.current.clear()
      await mockAgent.run(payload, currentUser.id, handleEvent)
      refresh()
      setBusy(false)
    },
    [busy, currentUser, handleEvent, refresh],
  )

  const sendMessage = useCallback(
    async (rawText: string) => {
      const text = rawText.trim()
      if (!text || busy || !currentUser) return
      appendMessage({
        id: messageId(),
        role: 'user',
        kind: 'text',
        content: text,
        createdAt: now(),
      })
      setInput('')
      await runAgentRequest({ text })
    },
    [appendMessage, busy, currentUser, runAgentRequest],
  )

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !currentUser || busy) return
    appendMessage({
      id: messageId(),
      role: 'user',
      kind: 'file',
      content: file.name,
      createdAt: now(),
      file: { name: file.name, size: file.size, type: file.type || '表格文件' },
    })
    await runAgentRequest({
      text: `导入文件 ${file.name}`,
      fileName: file.name,
      fileSize: file.size,
      fileType: file.type,
    })
  }

  const handleConfirm = async (action: PendingAction) => {
    if (!currentUser || busy) return
    const message = messagesRef.current.find(
      (candidate) => candidate.action?.id === action.id,
    )
    if (message) {
      patchMessage(message.id, (candidate) => ({
        ...candidate,
        action: candidate.action
          ? { ...candidate.action, executed: true }
          : candidate.action,
      }))
    }
    setBusy(true)
    setBusyStatus(action.stage === 1 ? '正在校验删除条件' : '正在执行已确认的操作')
    executionMessagesRef.current.clear()
    await mockAgent.confirm(action, currentUser.id, handleEvent)
    refresh()
    setBusy(false)
  }

  const handleCancel = (action: PendingAction) => {
    const message = messagesRef.current.find(
      (candidate) => candidate.action?.id === action.id,
    )
    if (message) {
      patchMessage(message.id, (candidate) => ({
        ...candidate,
        action: candidate.action
          ? { ...candidate.action, executed: true }
          : candidate.action,
      }))
    }
    appendMessage({
      id: messageId(),
      role: 'assistant',
      kind: 'text',
      content: '已取消本次操作，没有写入任何业务数据。你仍然可以继续调整需求。',
      createdAt: now(),
    })
    showToast('操作已取消', 'default')
  }

  const handleClear = () => {
    if (!currentUser) return
    conversationApi.clear(currentUser.id)
    setMessages([])
    messagesRef.current = []
    setClearOpen(false)
    showToast('当前对话已清空')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendMessage(input)
    }
  }

  if (!currentUser) return null

  return (
    <div className="chat-page">
      <header className="chat-header">
        <div className="chat-header-title">
          <h1>学习助手</h1>
          <Badge tone="success">本地已同步</Badge>
        </div>
        <div className="chat-header-actions">
          <span className="chat-header-caption">Agent 可调用任务、词库和记录能力</span>
          <IconButton label="清空当前对话" icon={Trash2} onClick={() => setClearOpen(true)} />
        </div>
      </header>

      <div className="chat-scroll-area">
        <div className="chat-column">
          {messages.length === 0 ? (
            <section className="chat-welcome">
              <div className="welcome-mark">
                <Sparkles size={22} />
              </div>
              <h2>今天想学点什么？</h2>
              <p>
                用自然语言描述目标。我会先整理配置、展示预览，重要操作确认后才会执行。
              </p>
              <div className="suggestion-grid">
                {suggestions.map((suggestion) => {
                  const Icon = suggestion.icon
                  return (
                    <button
                      key={suggestion.title}
                      type="button"
                      className="suggestion-card"
                      onClick={() => {
                        if ('upload' in suggestion && suggestion.upload) {
                          fileInputRef.current?.click()
                        } else {
                          void sendMessage(suggestion.prompt)
                        }
                      }}
                      disabled={busy}
                    >
                      <span className="suggestion-icon">
                        <Icon size={18} />
                      </span>
                      <strong>{suggestion.title}</strong>
                      <span>{suggestion.description}</span>
                    </button>
                  )
                })}
              </div>
              <div className="welcome-boundary">
                <Settings2 size={14} />
                练习会打开独立页面，不会在聊天窗口中答题
              </div>
            </section>
          ) : null}

          {messages.map((message) => (
            <ChatMessageItem
              key={message.id}
              message={message}
              userName={currentUser.nickname}
              busy={busy}
              onConfirm={(action) => void handleConfirm(action)}
              onCancel={handleCancel}
              onQuickReply={(text) => void sendMessage(text)}
            />
          ))}

          {busy ? (
            <div className="agent-working">
              <AgentAvatar />
              <div>
                <span className="working-dots">
                  <i />
                  <i />
                  <i />
                </span>
                <span>{busyStatus}</span>
              </div>
            </div>
          ) : null}
          <div ref={endRef} />
        </div>
      </div>

      <div className="chat-composer-wrap">
        <div className={`chat-composer ${busy ? 'is-busy' : ''}`}>
          <textarea
            ref={textareaRef}
            value={input}
            rows={1}
            placeholder="描述你的学习目标，或继续刚才的对话…"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={busy}
            aria-label="给学习助手发送消息"
          />
          <div className="composer-toolbar">
            <div className="composer-tools">
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                hidden
                onChange={(event) => void handleFile(event)}
              />
              <IconButton
                label="上传 Excel 或 CSV"
                icon={Paperclip}
                onClick={() => fileInputRef.current?.click()}
                disabled={busy}
              />
              <span className="composer-hint">Enter 发送 · Shift + Enter 换行</span>
            </div>
            <button
              type="button"
              className="send-button"
              aria-label="发送消息"
              disabled={!input.trim() || busy}
              onClick={() => void sendMessage(input)}
            >
              {busy ? <LoaderCircle className="spin" size={17} /> : <ArrowUp size={18} />}
            </button>
          </div>
        </div>
        <p className="composer-disclaimer">
          Agent 的重要写操作都会先展示预览并等待确认
        </p>
      </div>

      <Modal
        open={clearOpen}
        title="清空当前对话"
        description="消息历史会被移除，但已创建的任务、词库和练习记录不会受影响。"
        width="sm"
        onClose={() => setClearOpen(false)}
        footer={
          <>
            <Button onClick={() => setClearOpen(false)}>取消</Button>
            <Button variant="danger" icon={RotateCcw} onClick={handleClear}>
              清空对话
            </Button>
          </>
        }
      >
        <p className="modal-copy">这是原型中的单会话模式。清空后仍可立即开始新的对话。</p>
      </Modal>
    </div>
  )
}
