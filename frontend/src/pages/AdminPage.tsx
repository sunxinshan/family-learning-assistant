import {
  Activity,
  BarChart3,
  BookOpenText,
  CheckCircle2,
  KeyRound,
  ListChecks,
  Plus,
  ScrollText,
  ShieldCheck,
  Trash2,
  Users,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { adminApi, vocabularyApi } from '../api/mockApi'
import {
  Badge,
  Button,
  EmptyState,
  Modal,
  PageHeader,
} from '../components/ui'
import { useAppStore } from '../stores/AppStore'
import type { LearningStats, User, Vocabulary } from '../types/domain'
import { formatDateTime } from '../utils/format'

type Tab = 'users' | 'vocabularies' | 'logs'

type AdminUser = User & { practiceCount: number; accuracy: number }

const roleBadge = (role: User['role']) =>
  role === 'admin' ? <Badge tone="info">管理员</Badge> : <Badge>普通用户</Badge>

export const AdminPage = () => {
  const { currentUser, publicLibraries, refresh, showToast } = useAppStore()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('users')
  const [statsUser, setStatsUser] = useState<AdminUser | null>(null)
  const [resetUser, setResetUser] = useState<AdminUser | null>(null)
  const [passwordResult, setPasswordResult] = useState<{ user: string; password: string } | null>(null)
  const [deleteLibrary, setDeleteLibrary] = useState<Vocabulary | null>(null)
  const [busy, setBusy] = useState(false)

  const users = useMemo<AdminUser[]>(
    () => (currentUser ? adminApi.listUsers(currentUser.id) : []),
    [currentUser, publicLibraries],
  )
  const logs = useMemo(
    () => (currentUser ? adminApi.listLogs(currentUser.id) : []),
    [currentUser, publicLibraries],
  )
  const stats = useMemo<LearningStats | null>(() => {
    if (!currentUser || !statsUser) return null
    return adminApi.getUserStats(currentUser.id, statsUser.id)
  }, [currentUser, statsUser, publicLibraries])

  if (!currentUser || currentUser.role !== 'admin') return null

  const togglePublish = async (library: Vocabulary) => {
    setBusy(true)
    try {
      await vocabularyApi.togglePublish(currentUser.id, library.id)
      refresh()
      showToast(library.published ? '公共词库已撤回' : '公共词库已发布', 'success')
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '更新失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const removePublicLibrary = async () => {
    if (!deleteLibrary) return
    setBusy(true)
    try {
      await vocabularyApi.removePublic(currentUser.id, deleteLibrary.id)
      refresh()
      setDeleteLibrary(null)
      showToast('公共词库已删除', 'success')
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '删除失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const confirmReset = async () => {
    if (!resetUser) return
    setBusy(true)
    try {
      const password = await adminApi.resetPassword(currentUser.id, resetUser.id)
      setPasswordResult({ user: resetUser.nickname, password })
      setResetUser(null)
      refresh()
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : '重置失败', 'danger')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page-container admin-page">
      <PageHeader
        eyebrow="Administration"
        title="管理后台"
        description="管理用户账户和公共词库，并查看关键操作日志。管理员不能代替用户修改学习结果。"
        actions={
          <>
            <Link className="button button-secondary button-md" to="/tasks/new">
              <ListChecks size={16} />
              页面创建任务
            </Link>
            {tab === 'vocabularies' ? (
              <Link className="button button-primary button-md" to="/vocabulary/new?scope=public">
                <Plus size={16} />
                新建公共词库
              </Link>
            ) : (
              <Badge tone="info"><ShieldCheck size={12} />管理员权限</Badge>
            )}
          </>
        }
      />

      <div className="admin-boundary-note">
        <ShieldCheck size={16} />
        <span>
          管理员可以查看所有用户数据，但不能代替用户创建、修改、删除任务，也不能修改答题结果或词汇掌握状态。
        </span>
      </div>

      <div className="section-tabs admin-tabs" role="tablist">
        <button type="button" className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}>
          <Users size={15} />
          用户管理
        </button>
        <button type="button" className={tab === 'vocabularies' ? 'active' : ''} onClick={() => setTab('vocabularies')}>
          <BookOpenText size={15} />
          公共词库
        </button>
        <button type="button" className={tab === 'logs' ? 'active' : ''} onClick={() => setTab('logs')}>
          <ScrollText size={15} />
          操作日志
        </button>
      </div>

      {tab === 'users' ? (
        <section className="table-panel">
          <div className="admin-table-heading">
            <div>
              <h2>全部用户</h2>
              <p>共 {users.length} 个账户，普通用户与管理员数据隔离规则一致。</p>
            </div>
          </div>
          <div className="data-table-wrap">
            <table className="data-table admin-table">
              <thead>
                <tr>
                  <th>用户</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th>完成练习</th>
                  <th>平均正确率</th>
                  <th>最近活跃</th>
                  <th className="actions-cell">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <div className="admin-user-cell">
                        <span className="account-avatar">{user.nickname.slice(0, 1)}</span>
                        <div>
                          <strong>{user.nickname}</strong>
                          <span>{user.id}</span>
                        </div>
                      </div>
                    </td>
                    <td>{roleBadge(user.role)}</td>
                    <td><Badge tone={user.status === 'active' ? 'success' : 'danger'}>{user.status === 'active' ? '正常' : '停用'}</Badge></td>
                    <td>{user.practiceCount}</td>
                    <td>{user.accuracy}%</td>
                    <td>{formatDateTime(user.lastActiveAt)}</td>
                    <td className="actions-cell">
                      <div className="table-actions">
                        <Button size="sm" icon={BarChart3} onClick={() => setStatsUser(user)}>
                          学习概况
                        </Button>
                        <Button size="sm" icon={KeyRound} onClick={() => setResetUser(user)}>
                          重置密码
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {tab === 'vocabularies' ? (
        <section className="table-panel">
          <div className="admin-table-heading">
            <div>
              <h2>公共词库</h2>
              <p>创建草稿、编辑词条、发布或撤回。发布后普通用户可以浏览和复制。</p>
            </div>
          </div>
          <div className="data-table-wrap">
            <table className="data-table admin-table public-library-table">
              <thead>
                <tr>
                  <th>词库</th>
                  <th>学科</th>
                  <th>分类</th>
                  <th>词条数</th>
                  <th>状态</th>
                  <th>更新时间</th>
                  <th className="actions-cell">操作</th>
                </tr>
              </thead>
              <tbody>
                {publicLibraries.map((library) => (
                  <tr key={library.id}>
                    <td>
                      <div className="admin-library-cell">
                        <strong>{library.name}</strong>
                        <span>{library.description}</span>
                      </div>
                    </td>
                    <td>{library.subject === 'english' ? '英语' : '语文'}</td>
                    <td>{library.category}</td>
                    <td>{library.entries.length}</td>
                    <td>
                      <Badge tone={library.published ? 'success' : 'warning'}>
                        {library.published ? '已发布' : '草稿'}
                      </Badge>
                    </td>
                    <td>{formatDateTime(library.updatedAt)}</td>
                    <td className="actions-cell">
                      <div className="table-actions">
                        <Button size="sm" onClick={() => navigate(`/vocabulary/${library.id}`)}>编辑词条</Button>
                        <Button
                          size="sm"
                          loading={busy}
                          onClick={() => void togglePublish(library)}
                        >
                          {library.published ? '撤回' : '发布'}
                        </Button>
                        <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDeleteLibrary(library)}>
                          删除
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!publicLibraries.length ? (
            <EmptyState
              icon={BookOpenText}
              title="还没有公共词库"
              description="创建第一份公共词库草稿，添加词条后即可发布。"
              action={<Link className="button button-primary button-md" to="/vocabulary/new?scope=public">新建公共词库</Link>}
            />
          ) : null}
        </section>
      ) : null}

      {tab === 'logs' ? (
        <section className="table-panel">
          <div className="admin-table-heading">
            <div>
              <h2>关键操作日志</h2>
              <p>记录重要写操作，不包含普通页面浏览和答题细节。</p>
            </div>
          </div>
          <div className="data-table-wrap">
            <table className="data-table admin-table log-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>操作人</th>
                  <th>操作</th>
                  <th>目标对象</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>{formatDateTime(log.createdAt)}</td>
                    <td>{log.actorName}</td>
                    <td>{log.action}</td>
                    <td>{log.target}</td>
                    <td>
                      <Badge tone={log.result === 'success' ? 'success' : 'danger'}>
                        {log.result === 'success' ? '成功' : '失败'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <Modal
        open={Boolean(statsUser)}
        title={statsUser ? `${statsUser.nickname} 的学习概况` : '学习概况'}
        description="管理员只读视图。统计从该用户的答题事实重新计算。"
        width="lg"
        onClose={() => setStatsUser(null)}
        footer={<Button onClick={() => setStatsUser(null)}>关闭</Button>}
      >
        {stats ? (
          <div className="admin-stats-grid">
            <div><Activity size={17} /><span>完成练习</span><strong>{stats.practiceCount} 次</strong></div>
            <div><CheckCircle2 size={17} /><span>平均正确率</span><strong>{stats.averageAccuracy}%</strong></div>
            <div><BookOpenText size={17} /><span>已掌握词数</span><strong>{stats.masteredCount}</strong></div>
            <div><BarChart3 size={17} /><span>待复习错题</span><strong>{stats.reviewCount}</strong></div>
          </div>
        ) : null}
        <p className="modal-copy admin-readonly-copy">
          管理员不能修改任务、答题结果或掌握状态。如需更正数据，应按照正式业务的审计与纠错流程处理。
        </p>
      </Modal>

      <Modal
        open={Boolean(resetUser)}
        title="重置用户密码"
        description="将生成一次性演示密码。该操作会记录到关键操作日志。"
        width="sm"
        onClose={() => setResetUser(null)}
        footer={
          <>
            <Button onClick={() => setResetUser(null)}>取消</Button>
            <Button variant="primary" loading={busy} onClick={() => void confirmReset()}>
              确认重置
            </Button>
          </>
        }
      >
        <div className="reset-warning">
          <KeyRound size={20} />
          <div>
            <strong>{resetUser?.nickname}</strong>
            <p>重置后请将新密码安全地交给用户。</p>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(passwordResult)}
        title="密码已重置"
        description="原型会直接展示生成的临时密码。"
        width="sm"
        onClose={() => setPasswordResult(null)}
        footer={<Button variant="primary" onClick={() => setPasswordResult(null)}>我已记录</Button>}
      >
        {passwordResult ? (
          <div className="password-result">
            <span>{passwordResult.user}</span>
            <code>{passwordResult.password}</code>
            <small>正式系统不应在界面中永久展示明文密码。</small>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(deleteLibrary)}
        title="删除公共词库"
        description="删除后普通用户将无法继续浏览或复制该词库。"
        width="sm"
        danger
        onClose={() => setDeleteLibrary(null)}
        footer={
          <>
            <Button onClick={() => setDeleteLibrary(null)}>取消</Button>
            <Button variant="danger" loading={busy} onClick={() => void removePublicLibrary()}>
              确认删除
            </Button>
          </>
        }
      >
        <div className="danger-summary">
          <strong>{deleteLibrary?.name}</strong>
          <p>该操作只影响公共资源，不会删除普通用户已经复制的个人副本。</p>
        </div>
      </Modal>
    </main>
  )
}
