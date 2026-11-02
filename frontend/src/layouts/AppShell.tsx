import {
  BookOpenText,
  ChartNoAxesCombined,
  ChevronDown,
  LibraryBig,
  ListChecks,
  LogOut,
  Menu,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../stores/AppStoreContext'
import { IconButton } from '../components/ui'

const baseNav = [
  { to: '/', label: '学习助手', icon: MessageSquare, end: true },
  { to: '/vocabulary', label: '词库', icon: LibraryBig },
  { to: '/tasks', label: '学习任务', icon: ListChecks },
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
  const { currentUser, logout } = useAppStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
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
          <strong>正式服务</strong>
          <span>数据由后端实时同步</span>
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

    </div>
  )
}
