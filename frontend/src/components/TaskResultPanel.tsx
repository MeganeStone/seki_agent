import type { ReactNode } from 'react'

export type TaskResultField = {
  label: string
  value: ReactNode
}

type TaskResultPanelProps = {
  title?: string
  status: string
  fields: TaskResultField[]
  error?: string | null
  preview?: string | null
  refreshLabel?: string
  refreshingLabel?: string
  refreshing?: boolean
  canDownload?: boolean
  onRefresh: () => void
  onDownload: () => void
}

function TaskResultPanel({
  title = '最近任务',
  status,
  fields,
  error,
  preview,
  refreshLabel = '查询状态',
  refreshingLabel = '查询中',
  refreshing = false,
  canDownload = false,
  onRefresh,
  onDownload,
}: TaskResultPanelProps) {
  return (
    <div className="task-result">
      <div>
        <h3>{title}</h3>
        <span className={`status-badge ${status}`}>{status}</span>
      </div>
      <dl>
        {fields.map((field) => (
          <div key={field.label}>
            <dt>{field.label}</dt>
            <dd>{field.value}</dd>
          </div>
        ))}
        {error && (
          <div>
            <dt>错误</dt>
            <dd>{error}</dd>
          </div>
        )}
      </dl>
      {preview && <pre className="result-preview">{preview}</pre>}
      <div className="task-actions">
        <button type="button" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? refreshingLabel : refreshLabel}
        </button>
        <button type="button" onClick={onDownload} disabled={!canDownload}>
          下载结果
        </button>
      </div>
    </div>
  )
}

export default TaskResultPanel
