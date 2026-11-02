import { CheckCircle2, Info, LoaderCircle, TriangleAlert } from 'lucide-react'
import { lazy, Suspense, useEffect } from 'react'
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom'
import { AppShell } from '../layouts/AppShell'
import { useAppStore } from '../stores/AppStoreContext'

const LoginPage = lazy(() => import('../pages/LoginPage').then((module) => ({ default: module.LoginPage })))
const ChatPage = lazy(() => import('../pages/ChatPage').then((module) => ({ default: module.ChatPage })))
const TasksPage = lazy(() => import('../pages/TasksPage').then((module) => ({ default: module.TasksPage })))
const TaskCreatePage = lazy(() => import('../pages/TaskCreatePage').then((module) => ({ default: module.TaskCreatePage })))
const TaskDetailPage = lazy(() => import('../pages/TaskDetailPage').then((module) => ({ default: module.TaskDetailPage })))
const VocabularyPage = lazy(() => import('../pages/VocabularyPage').then((module) => ({ default: module.VocabularyPage })))
const VocabularyCreatePage = lazy(() => import('../pages/VocabularyCreatePage').then((module) => ({ default: module.VocabularyCreatePage })))
const VocabularyDetailPage = lazy(() => import('../pages/VocabularyDetailPage').then((module) => ({ default: module.VocabularyDetailPage })))
const DictationPracticePage = lazy(() => import('../pages/DictationPracticePage').then((module) => ({ default: module.DictationPracticePage })))
const LearningPage = lazy(() => import('../pages/LearningPage').then((module) => ({ default: module.LearningPage })))
const AdminPage = lazy(() => import('../pages/AdminPage').then((module) => ({ default: module.AdminPage })))

const ProtectedRoute = () => {
  const { currentUser } = useAppStore()
  const location = useLocation()
  return currentUser ? (
    <Outlet />
  ) : (
    <Navigate to="/login" replace state={{ from: location.pathname }} />
  )
}

const AdminRoute = () => {
  const { currentUser } = useAppStore()
  return currentUser?.role === 'admin' ? <Outlet /> : <Navigate to="/" replace />
}

const ScrollToTop = () => {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [pathname])
  return null
}

const ToastViewport = () => {
  const { toast } = useAppStore()
  if (!toast) return null
  const Icon = toast.tone === 'success' ? CheckCircle2 : toast.tone === 'danger' ? TriangleAlert : Info
  return (
    <div className={`toast toast-${toast.tone}`} key={toast.id} role="status">
      <Icon size={17} />
      <span>{toast.message}</span>
    </div>
  )
}

const RouteFallback = () => (
  <div className="route-fallback">
    <LoaderCircle className="spin" size={18} />
    <span>正在加载页面</span>
  </div>
)

const AppRoutes = () => (
  <>
    <ScrollToTop />
    <Suspense fallback={<RouteFallback />}>
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/practice/dictation/:taskId" element={<DictationPracticePage />} />
        <Route path="/practice/dictation/:taskId/wrong" element={<DictationPracticePage />} />
        <Route element={<AppShell />}>
          <Route index element={<ChatPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/tasks/new" element={<TaskCreatePage />} />
          <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
          <Route path="/vocabulary" element={<VocabularyPage />} />
          <Route path="/vocabulary/new" element={<VocabularyCreatePage />} />
          <Route path="/vocabulary/:libraryId" element={<VocabularyDetailPage />} />
          <Route path="/learning" element={<LearningPage />} />
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>
        </Route>
      </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
    <ToastViewport />
  </>
)

export const AppRouter = () => <AppRoutes />
