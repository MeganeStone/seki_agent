import { useCallback, useEffect, useMemo, useState } from 'react'
import { cancelTask, listTasks } from '../api/tasks'
import type { TaskType, UnifiedTask } from '../types/tasks'

type TasksPageProps = {
  accessToken: string | null
}

const taskTypeLabels: Record<TaskType, string> = {
  translation: '文档翻译',
  spi: 'SPI 解析',
  diff: '版本差分',
}

const taskTypeRoutes: Record<TaskType, string> = {
  translation: 'translation',
  spi: 'spi',
  diff: 'diff',
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function TasksPage({ accessToken }: TasksPageProps) {
  const [tasks, setTasks] = useState<UnifiedTask[]>([])
  const [loading, setLoading] = useState(false)
  const [cancellingTaskId, setCancellingTaskId] = useState('')
  const [error, setError] = useState('')

  const succeededCount = useMemo(() => tasks.filter((task) => task.status === 'succeeded').length, [tasks])

  const refreshTasks = useCallback(async () => {
    if (!accessToken) return

    setLoading(true)
    setError('')
    try {
      const result = await listTasks(accessToken)
      setTasks(result.items)
    } catch (error) {
      setError(error instanceof Error ? error.message : '任务历史获取失败')
    } finally {
      setLoading(false)
    }
  }, [accessToken])

  async function handleCancelTask(task: UnifiedTask) {
    if (!accessToken) return

    setCancellingTaskId(task.task_id)
    setError('')
    try {
      const cancelled = await cancelTask(accessToken, task.task_id)
      setTasks((current) =>
        current.map((item) =>
          item.task_id === cancelled.task_id && item.type === cancelled.type ? cancelled : item,
        ),
      )
    } catch (error) {
      setError(error instanceof Error ? error.message : '任务取消失败')
    } finally {
      setCancellingTaskId('')
    }
  }

  useEffect(() => {
    if (!accessToken) return

    let isCurrent = true
    const token = accessToken

    async function loadTasks() {
      setLoading(true)
      setError('')
      try {
        const result = await listTasks(token)
        if (isCurrent) setTasks(result.items)
      } catch (error) {
        if (isCurrent) setError(error instanceof Error ? error.message : '任务历史获取失败')
      } finally {
        if (isCurrent) setLoading(false)
      }
    }

    void loadTasks()

    return () => {
      isCurrent = false
    }
  }, [accessToken])

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>任务历史</h2>
          <p>请先登录后再查看个人任务历史。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  return (
    <section className="tasks-page" aria-labelledby="tasks-title">
      <div className="tasks-toolbar">
        <div>
          <h2 id="tasks-title">最近任务</h2>
          <p>{loading ? '正在刷新任务历史' : `共 ${tasks.length} 个任务，${succeededCount} 个已成功`}</p>
        </div>
        <button type="button" onClick={refreshTasks} disabled={loading}>
          刷新
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="task-history-table" role="table" aria-label="最近任务列表">
        <div className="task-history-row task-history-head" role="row">
          <span role="columnheader">类型</span>
          <span role="columnheader">状态</span>
          <span role="columnheader">任务 ID</span>
          <span role="columnheader">结果文件 ID</span>
          <span role="columnheader">更新时间</span>
          <span role="columnheader">入口</span>
        </div>

        {tasks.map((task) => (
          <div className="task-history-row" role="row" key={`${task.type}:${task.task_id}`}>
            <span role="cell">{taskTypeLabels[task.type]}</span>
            <span role="cell">
              <span className={`status-badge ${task.status}`}>{task.status}</span>
            </span>
            <span role="cell" title={task.task_id}>
              {task.task_id}
            </span>
            <span role="cell" title={task.result_file_id ?? ''}>
              {task.result_file_id ?? '-'}
            </span>
            <span role="cell">{formatDate(task.updated_at)}</span>
            <span className="file-actions" role="cell">
              <a className="text-action small" href={`#/${taskTypeRoutes[task.type]}`}>
                打开
              </a>
              <button
                type="button"
                onClick={() => void handleCancelTask(task)}
                disabled={!['pending', 'running'].includes(task.status) || cancellingTaskId === task.task_id}
              >
                {cancellingTaskId === task.task_id ? '终止中' : '终止'}
              </button>
            </span>
            {task.error && (
              <span className="task-history-error" role="cell">
                {task.error}
              </span>
            )}
          </div>
        ))}

        {!loading && tasks.length === 0 && <div className="empty-state">暂无任务</div>}
      </div>
    </section>
  )
}

export default TasksPage
