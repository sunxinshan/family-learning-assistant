import {
  BookOpenText,
  CheckCircle2,
  KeyRound,
  Sparkles,
} from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Badge, Button, Field, InlineError, TextInput } from '../components/ui'
import { useAppStore } from '../stores/AppStoreContext'

export const LoginPage = () => {
  const { currentUser, login, register } = useAppStore()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

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
            通过 Agent 整理资料、创建词库和学习任务；在独立练习页面专注完成听写。
          </p>
          <div className="login-flow-preview">
            <div className="login-flow-line">
              <span className="login-flow-icon"><Sparkles size={15} /></span>
              <div>
                <small>你</small>
                <p>选择所有单词，创建一个线下听写任务</p>
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
          <span>正式开发版</span>
          <span>HTTP API · SSE · MySQL Ready</span>
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
            <h2>{mode === 'login' ? '登录你的学习空间' : '创建账户'}</h2>
            <p>{mode === 'login' ? '继续与学习助手协作。' : '账户数据由后端安全保存，密码不会返回前端。'}</p>
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
            {mode === 'login' ? '没有账户？创建账户' : '已有账户？返回登录'}
          </button>


        </div>
      </section>

    </div>
  )
}
