import {
  ArrowRight,
  BookOpenText,
  CheckCircle2,
  KeyRound,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Badge, Button, Field, InlineError, Modal, TextInput } from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'

export const LoginPage = () => {
  const { currentUser, login, register, resetDemo } = useAppStore()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [nickname, setNickname] = useState('Alice')
  const [password, setPassword] = useState('demo123')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)

  if (currentUser) return <Navigate to="/" replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (mode === 'login') {
        await login(nickname, password)
      } else {
        await register(nickname, password)
      }
      navigate('/', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const demoLogin = async (demoNickname: string, demoPassword: string) => {
    setBusy(true)
    setError('')
    try {
      await login(demoNickname, demoPassword)
      navigate('/', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '演示登录失败')
    } finally {
      setBusy(false)
    }
  }

  const handleReset = () => {
    resetDemo()
    setResetOpen(false)
    setMode('login')
    setNickname('Alice')
    setPassword('demo123')
    setError('')
  }

  return (
    <div className="login-page">
      <section className="login-brand-panel">
        <div className="login-brand">
          <span className="brand-mark brand-mark-light">
            <BookOpenText size={19} />
          </span>
          <strong>家庭学习助手</strong>
        </div>
        <div className="login-brand-copy">
          <Badge tone="info"><Sparkles size={12} />Agent-first Learning</Badge>
          <h1>让学习计划从一句话开始。</h1>
          <p>
            通过 Agent 整理资料、创建词库和学习任务；在独立练习页面专注完成词汇与听写。
          </p>
          <div className="login-flow-preview">
            <div className="login-flow-line">
              <span className="login-flow-icon"><Sparkles size={15} /></span>
              <div>
                <small>你</small>
                <p>创建一个词汇任务，每天 8 个词</p>
              </div>
            </div>
            <div className="login-flow-line">
              <span className="login-flow-icon"><CheckCircle2 size={15} /></span>
              <div>
                <small>Agent</small>
                <p>配置预览 · 确认后写入 · 进入独立练习</p>
              </div>
            </div>
          </div>
        </div>
        <div className="login-brand-footer">
          <span>Phase 0 交互原型</span>
          <span>Mock API · LocalStorage</span>
        </div>
      </section>

      <section className="login-form-panel">
        <div className="login-form-wrap">
          <div>
            <div className="login-mobile-brand">
              <span className="brand-mark"><BookOpenText size={17} /></span>
              家庭学习助手
            </div>
          </div>
          <div className="login-heading">
            <h2>{mode === 'login' ? '登录你的学习空间' : '创建演示账户'}</h2>
            <p>{mode === 'login' ? '继续与学习助手协作，或从下方直接进入演示。' : '原型账户会保存在当前浏览器 LocalStorage 中。'}</p>
          </div>

          <form className="login-form" onSubmit={(event) => void submit(event)}>
            {error ? <InlineError>{error}</InlineError> : null}
            <Field label="昵称">
              <TextInput
                value={nickname}
                onChange={(event) => setNickname(event.target.value)}
                placeholder="输入昵称"
                autoComplete="username"
              />
            </Field>
            <Field label="密码" hint={mode === 'register' ? '至少 6 个字符' : undefined}>
              <TextInput
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="输入密码"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />
            </Field>
            <Button type="submit" variant="primary" size="lg" loading={busy} icon={KeyRound}>
              {mode === 'login' ? '登录' : '创建并登录'}
            </Button>
          </form>

          <button
            type="button"
            className="auth-mode-switch"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              setError('')
              if (mode === 'login') {
                setNickname('')
                setPassword('')
              }
            }}
          >
            {mode === 'login' ? '没有账户？创建一个演示账户' : '已有账户？返回登录'}
          </button>

          <div className="login-divider"><span>或使用演示账户</span></div>

          <div className="demo-login-grid">
            <button type="button" className="demo-login-card" disabled={busy} onClick={() => void demoLogin('Alice', 'demo123')}>
              <span className="demo-login-icon"><UserRound size={18} /></span>
              <span>
                <strong>普通用户</strong>
                <small>Alice · 词汇与听写学习</small>
              </span>
              <ArrowRight size={15} />
            </button>
            <button type="button" className="demo-login-card" disabled={busy} onClick={() => void demoLogin('Admin', 'admin123')}>
              <span className="demo-login-icon"><ShieldCheck size={18} /></span>
              <span>
                <strong>管理员 · Admin</strong>
                <small>公共词库、任务与用户管理</small>
              </span>
              <ArrowRight size={15} />
            </button>
            <button type="button" className="demo-login-card" disabled={busy} onClick={() => void demoLogin('Manager', 'manager123')}>
              <span className="demo-login-icon"><ShieldCheck size={18} /></span>
              <span>
                <strong>管理员 · Manager</strong>
                <small>第二个管理员演示账号</small>
              </span>
              <ArrowRight size={15} />
            </button>
          </div>

          <button type="button" className="reset-demo-link" onClick={() => setResetOpen(true)}>
            <RotateCcw size={13} />
            重置演示数据
          </button>
        </div>
      </section>

      <Modal
        open={resetOpen}
        title="重置演示数据"
        description="将恢复所有初始 Mock 数据并退出当前账户。"
        width="sm"
        danger
        onClose={() => setResetOpen(false)}
        footer={
          <>
            <Button onClick={() => setResetOpen(false)}>取消</Button>
            <Button variant="danger" onClick={handleReset}>确认重置</Button>
          </>
        }
      >
        <div className="reset-warning">
          <RotateCcw size={20} />
          <div>
            <strong>所有本地修改都会被清除</strong>
            <p>包括对话、任务、词库、练习记录和操作日志。</p>
          </div>
        </div>
      </Modal>
    </div>
  )
}
