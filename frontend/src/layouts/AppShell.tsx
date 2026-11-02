import {
  BookOpenText,
  ChartNoAxesCombined,
  ChevronDown,
  LibraryBig,
  ListChecks,
  LogOut,
  Menu,
  MessageSquare,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../stores/AppStoreContext'
import { Button, IconButton, Modal } from '../components/ui'

const baseNav = [
  { to: '/', label: '学习助手', icon: MessageSquare, end: true },
  { to: '/tasks', label: '学习任务', icon: ListChecks },
  { to: '/vocabulary', label: '词库', icon: LibraryBig },
  { to: '/learning', label: '学习记录', icon: ChartNoAxesCombined },
]

const titleForPath = (pathname: string): string => {
  if (pathname === '/') return '学习助手'
  if (pathname === '/tasks/new') return '新建学习任务'
  if (pathname.startsWith('/tasks/')) return '任务详情'
  if (pathname === '/tasks') return '学习任务'
  if (pathname === '/vocabulary/new') return '新建词库'
  if (pathname.startsWith('/vocabulary/')) return '词库详情'
  if (pathname === '/vocabulary') return '词库'
  if (pathname === '/learning') return '学习记录'
  if (pathname === '/admin') return '管理后台'
  return '家庭学习助手'
}

export const AppShell = () => {
  const { currentUser, logout, resetDemo } = useAppStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)
  const accountRef = useRef<HTMLDivElement>(null)

  const nav = currentUser?.role === 'admin'
    ? [...baseNav, { to: '/admin', label: '管理后台', icon: ShieldCheck }]
    : baseNav

  useEffect(() => {
    setDrawerOpen(false)
    setAccountOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const handlePointer = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) {
        setAccountOpen(false)
      }
    }
    document.addEventListener('mousedown', handlePointer)
    return () => document.removeEventListener('mousedown', handlePointer)
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const handleReset = () => {
    resetDemo()
    setResetOpen(false)
    navigate('/login', { replace: true })
  }

  const sidebar = (
    <>
      <div className="sidebar-brand-row">
        <Link to="/" className="brand" aria-label="家庭学习助手首页">
          <span className="brand-mark">
            <BookOpenText size={18} />
          </span>
          <span className="brand-copy">
            <strong>家庭学习助手</strong>
            <small>Learning Companion</small>
          </span>
        </Link>
        <IconButton
          label="关闭导航"
          icon={X}
          className="mobile-only"
          onClick={() => setDrawerOpen(false)}
        />
      </div>

      <div className="sidebar-section-label">工作区</div>
      <nav className="main-nav" aria-label="主导航">
        {nav.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      <div className="sidebar-spacer" />
      <div className="prototype-note">
        <div className="prototype-note-icon">
          <Sparkles size={14} />
        </div>
        <div>
          <strong>Phase 0 原型</strong>
          <span>数据保存在当前浏览器</span>
        </div>
      </div>

      <div className="sidebar-account" ref={accountRef}>
        {accountOpen ? (
          <div className="account-popover">
            <div className="account-popover-head">
              <span className="account-avatar">{currentUser?.nickname.slice(0, 1)}</span>
              <div>
                <strong>{currentUser?.nickname}</strong>
                <span>{currentUser?.role === 'admin' ? '管理员账户' : '普通用户'}</span>
              </div>
            </div>
            <button type="button" onClick={handleLogout}>
              <LogOut size={15} />
              退出登录
            </button>
            <button type="button" onClick={() => setResetOpen(true)}>
              <RotateCcw size={15} />
              重置演示数据
            </button>
          </div>
        ) : null}
        <button
          type="button"
          className="account-trigger"
          onClick={() => setAccountOpen((open) => !open)}
          aria-expanded={accountOpen}
        >
          <span className="account-avatar">{currentUser?.nickname.slice(0, 1)}</span>
          <span className="account-copy">
            <strong>{currentUser?.nickname}</strong>
            <small>{currentUser?.role === 'admin' ? '管理员' : '普通用户'}</small>
          </span>
          <ChevronDown size={15} />
        </button>
      </div>
    </>
  )

  return (
    <div className="app-shell">
      <aside className={`sidebar desktop-sidebar ${drawerOpen ? 'drawer-open' : ''}`}>
        {sidebar}
      </aside>

      {drawerOpen ? (
        <div className="mobile-drawer-layer">
          <button
            className="drawer-backdrop"
            type="button"
            aria-label="关闭导航"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="sidebar mobile-sidebar">{sidebar}</aside>
        </div>
      ) : null}

      <div className="app-content">
        <header className="mobile-topbar">
          <IconButton label="打开导航" icon={Menu} onClick={() => setDrawerOpen(true)} />
          <span>{titleForPath(location.pathname)}</span>
          <span className="mobile-account-avatar">{currentUser?.nickname.slice(0, 1)}</span>
        </header>
        <Outlet />
      </div>

      <Modal
        open={resetOpen}
        title="重置演示数据"
        description="所有对话、任务、词库和练习记录都会被恢复为初始状态。"
        width="sm"
        danger
        onClose={() => setResetOpen(false)}
        footer={
          <>
            <Button onClick={() => setResetOpen(false)}>取消</Button>
            <Button variant="danger" onClick={handleReset}>
              确认重置
            </Button>
          </>
        }
      >
        <div className="reset-warning">
          <RotateCcw size={20} />
          <div>
            <strong>当前修改不会保留</strong>
            <p>这是原型开发工具，不会影响任何真实账户或服务端数据。</p>
          </div>
        </div>
      </Modal>
    </div>
  )
}
