import { ChevronLeft, ChevronRight, Database, Eye, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../api'
import { Button, EmptyState, Modal } from '../../components/ui'
import { useAppStore } from '../../stores/AppStoreContext'
import type { CheckpointDetail, CheckpointList, CheckpointListItem } from '../../types/domain'

const PAGE_SIZE = 20

const formatBytes = (bytes: number) =>
  bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`

const shortId = (value: string) => value.slice(0, 8)

export const CheckpointPanel = () => {
  const { currentUser, showToast } = useAppStore()
  const [threadId, setThreadId] = useState('')
  const [offset, setOffset] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)
  const [data, setData] = useState<CheckpointList | null>(null)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<CheckpointDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    if (!currentUser) return
    let cancelled = false
    setLoading(true)
    void api.admin
      .listCheckpoints(currentUser.id, {
        threadId: threadId || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      .then((value) => {
        if (!cancelled) setData(value)
      })
      .catch((cause) => {
        if (!cancelled) {
          showToast(cause instanceof Error ? cause.message : 'Checkpoint 加载失败', 'danger')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentUser, threadId, offset, reloadKey, showToast])

  const openDetail = async (item: CheckpointListItem) => {
    if (!currentUser) return
    setDetail(null)
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      const value = await api.admin.getCheckpoint(
        currentUser.id,
        item.threadId,
        item.checkpointId,
      )
      setDetail(value)
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : 'Checkpoint 读取失败', 'danger')
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  return (
    <>
      <section className="table-panel">
        <div className="admin-table-heading checkpoint-heading">
          <div>
            <h2>Agent Checkpoint</h2>
            <p>
              LangGraph 状态快照（只读）。列表只取元信息，点「查看内容」时才反序列化
              channel_values，凭证类字段已脱敏。
            </p>
          </div>
          <div className="checkpoint-toolbar">
            <select
              className="checkpoint-select"
              value={threadId}
              onChange={(event) => {
                setThreadId(event.target.value)
                setOffset(0)
              }}
            >
              <option value="">全部线程（{data?.threads.length ?? 0}）</option>
              {(data?.threads ?? []).map((thread) => (
                <option key={thread.threadId} value={thread.threadId}>
                  {shortId(thread.threadId)} · {thread.checkpointCount} 条 · step{' '}
                  {thread.latestStep ?? '—'}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              icon={RefreshCw}
              loading={loading}
              onClick={() => setReloadKey((value) => value + 1)}
            >
              刷新
            </Button>
          </div>
        </div>

        <div className="data-table-wrap">
          <table className="data-table admin-table checkpoint-table">
            <thead>
              <tr>
                <th>Thread</th>
                <th>Checkpoint</th>
                <th>Step</th>
                <th>Source</th>
                <th>大小</th>
                <th className="actions-cell">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={`${item.threadId}:${item.checkpointNs}:${item.checkpointId}`}>
                  <td>
                    <div className="checkpoint-thread-cell">
                      <code>{shortId(item.threadId)}</code>
                      <span>{item.checkpointNs || 'main'}</span>
                    </div>
                  </td>
                  <td>
                    <code className="checkpoint-code">{item.checkpointId.slice(0, 13)}</code>
                  </td>
                  <td>{item.step ?? '—'}</td>
                  <td>{item.source ?? '—'}</td>
                  <td>{formatBytes(item.sizeBytes)}</td>
                  <td className="actions-cell">
                    <Button size="sm" icon={Eye} onClick={() => void openDetail(item)}>
                      查看内容
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!items.length && !loading ? (
          <EmptyState
            icon={Database}
            title="没有 checkpoint 记录"
            description="当前筛选条件下没有状态快照。可以切换线程或刷新后再看。"
          />
        ) : null}

        <div className="checkpoint-pager">
          <span>
            共 {total} 条{threadId ? '（已按线程筛选）' : ''}
            {total ? ` · 当前第 ${offset + 1}-${Math.min(offset + items.length, total)} 条` : ''}
          </span>
          <div className="table-actions">
            <Button
              size="sm"
              icon={ChevronLeft}
              disabled={!hasPrev}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              上一页
            </Button>
            <Button
              size="sm"
              icon={ChevronRight}
              disabled={!hasNext}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              下一页
            </Button>
          </div>
        </div>
      </section>

      <Modal
        open={detailOpen}
        title={detail ? `Checkpoint ${shortId(detail.checkpointId)}` : 'Checkpoint 详情'}
        description="channel_values 是反序列化后的图状态；writes 是该检查点之前的节点写入。"
        width="xl"
        onClose={() => setDetailOpen(false)}
        footer={<Button onClick={() => setDetailOpen(false)}>关闭</Button>}
      >
        {detailLoading ? <p className="checkpoint-loading">正在读取 checkpoint…</p> : null}
        {detail ? (
          <div className="checkpoint-detail">
            <div className="checkpoint-meta-grid">
              <div>
                <span>Thread</span>
                <code>{detail.threadId}</code>
              </div>
              <div>
                <span>Checkpoint</span>
                <code>{detail.checkpointId}</code>
              </div>
              <div>
                <span>Step</span>
                <strong>{detail.step ?? '—'}</strong>
              </div>
              <div>
                <span>Source</span>
                <strong>{detail.source ?? '—'}</strong>
              </div>
              <div>
                <span>大小</span>
                <strong>{formatBytes(detail.sizeBytes)}</strong>
              </div>
              <div>
                <span>Writes</span>
                <strong>{detail.writes.length}</strong>
              </div>
            </div>
            <h3 className="checkpoint-section-title">
              channel_values · {Object.keys(detail.channelValues).length} 个
            </h3>
            <pre className="checkpoint-json">{JSON.stringify(detail.channelValues, null, 2)}</pre>
            {detail.writes.length ? (
              <>
                <h3 className="checkpoint-section-title">writes · {detail.writes.length} 条</h3>
                <pre className="checkpoint-json">{JSON.stringify(detail.writes, null, 2)}</pre>
              </>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  )
}
