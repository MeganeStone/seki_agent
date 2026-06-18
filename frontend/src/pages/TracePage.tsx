import { useEffect, useState } from 'react'
import { getTraceRunDetail, listTraceRuns } from '../api/agentTrace'
import type { AgentTraceEvent, AgentTraceRun } from '../api/agentTrace'

type TracePageProps = {
  accessToken: string | null
}

function formatDate(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function statusLabel(status: string): string {
  if (status === 'succeeded') return '成功'
  if (status === 'failed') return '失败'
  if (status === 'cancelled') return '已停止'
  if (status === 'running') return '运行中'
  return status
}

function TracePage({ accessToken }: TracePageProps) {
  const [runs, setRuns] = useState<AgentTraceRun[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expandedRunId, setExpandedRunId] = useState('')
  const [events, setEvents] = useState<AgentTraceEvent[]>([])
  const [eventsLoading, setEventsLoading] = useState(false)

  useEffect(() => {
    if (!accessToken) return

    let isCurrent = true
    const token = accessToken

    async function loadRuns() {
      setLoading(true)
      setError('')
      try {
        const result = await listTraceRuns(token)
        if (isCurrent) setRuns(result)
      } catch (error) {
        if (isCurrent) setError(error instanceof Error ? error.message : '运行追踪加载失败')
      } finally {
        if (isCurrent) setLoading(false)
      }
    }

    void loadRuns()

    return () => {
      isCurrent = false
    }
  }, [accessToken])

  async function refreshRuns() {
    if (!accessToken) return
    setLoading(true)
    setError('')
    try {
      setRuns(await listTraceRuns(accessToken))
    } catch (error) {
      setError(error instanceof Error ? error.message : '运行追踪加载失败')
    } finally {
      setLoading(false)
    }
  }

  async function toggleRun(runId: string) {
    if (expandedRunId === runId) {
      setExpandedRunId('')
      setEvents([])
      return
    }
    if (!accessToken) return
    setExpandedRunId(runId)
    setEvents([])
    setEventsLoading(true)
    try {
      const detail = await getTraceRunDetail(accessToken, runId)
      setEvents(detail.events)
    } catch (error) {
      setError(error instanceof Error ? error.message : '运行追踪详情加载失败')
    } finally {
      setEventsLoading(false)
    }
  }

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>运行追踪</h2>
          <p>请先登录。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  return (
    <section className="files-page" aria-labelledby="trace-title">
      <div className="files-toolbar">
        <div>
          <h2 id="trace-title">Agent 运行追踪</h2>
          <p>{loading ? '正在刷新' : `最近 ${runs.length} 次运行（每轮对话一条，含工具调用和 token 用量）`}</p>
        </div>
        <button type="button" onClick={refreshRuns} disabled={loading}>
          刷新
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="file-table" role="table" aria-label="agent 运行列表">
        <div className="file-row trace-head" role="row">
          <span role="columnheader">时间</span>
          <span role="columnheader">输入</span>
          <span role="columnheader">状态</span>
          <span role="columnheader">tokens</span>
          <span role="columnheader">耗时</span>
        </div>

        {runs.map((run) => (
          <div key={run.run_id}>
            <button
              type="button"
              className={`file-row trace-row ${expandedRunId === run.run_id ? 'expanded' : ''}`}
              onClick={() => void toggleRun(run.run_id)}
            >
              <span>{formatDate(run.started_at)}</span>
              <span title={run.input_preview}>{run.input_preview || '-'}</span>
              <span className={`status-badge ${run.status}`}>{statusLabel(run.status)}</span>
              <span>{run.total_tokens.toLocaleString()}</span>
              <span>{run.duration_ms !== null ? `${run.duration_ms}ms` : '-'}</span>
            </button>

            {expandedRunId === run.run_id && (
              <div className="trace-detail">
                {run.answer_preview && <p>回答：{run.answer_preview}</p>}
                {run.error && <p className="form-error">错误：{run.error}</p>}
                {eventsLoading && <p>事件加载中...</p>}
                {!eventsLoading && events.length === 0 && <p>本次运行没有记录到工具/模型事件。</p>}
                {events.map((event) => (
                  <div className="trace-event" key={event.event_id}>
                    <span className="trace-event-type">
                      {event.event_type === 'model_call' ? '模型调用' : '工具调用'}
                    </span>
                    <span>{event.name}</span>
                    <span className={`status-badge ${event.status}`}>{statusLabel(event.status)}</span>
                    {event.input_tokens !== null && (
                      <span>
                        in {event.input_tokens} / out {event.output_tokens ?? 0}
                      </span>
                    )}
                    {event.duration_ms !== null && <span>{event.duration_ms}ms</span>}
                    {event.preview && <span className="trace-event-preview">{event.preview}</span>}
                    {event.error && <span className="form-error">{event.error}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {!loading && runs.length === 0 && <div className="empty-state">暂无运行记录</div>}
      </div>
    </section>
  )
}

export default TracePage
