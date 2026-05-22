import { useCallback, useEffect, useMemo, useState } from 'react'
import { downloadFile, listFiles } from '../api/files'
import { createSpiTask, getSpiTask } from '../api/spi'
import TaskResultPanel from '../components/TaskResultPanel'
import type { WorkspaceFile } from '../types/files'
import type { SpiTask } from '../types/spi'

type SpiPageProps = {
  accessToken: string | null
}

const LAST_TASK_STORAGE_KEY = 'seki_last_spi_task'

function isLogFile(file: WorkspaceFile): boolean {
  return file.filename.toLowerCase().endsWith('.log')
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function readCachedTask(): SpiTask | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(LAST_TASK_STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as SpiTask
  } catch {
    return null
  }
}

function persistTask(task: SpiTask | null): void {
  if (typeof window === 'undefined') return
  try {
    if (task) {
      window.localStorage.setItem(LAST_TASK_STORAGE_KEY, JSON.stringify(task))
    } else {
      window.localStorage.removeItem(LAST_TASK_STORAGE_KEY)
    }
  } catch {
    // ignore storage errors
  }
}

function SpiPage({ accessToken }: SpiPageProps) {
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([])
  const [task, setTask] = useState<SpiTask | null>(() => readCachedTask())
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [refreshingTask, setRefreshingTask] = useState(false)
  const [error, setError] = useState('')

  const logFiles = useMemo(() => files.filter(isLogFile), [files])
  const selectedFiles = useMemo(
    () => files.filter((file) => selectedFileIds.includes(file.id)),
    [files, selectedFileIds],
  )
  const canCreateTask = Boolean(accessToken && selectedFileIds.length > 0 && !submitting)

  const refreshFiles = useCallback(async () => {
    if (!accessToken) return

    setLoadingFiles(true)
    setError('')
    try {
      const result = await listFiles(accessToken)
      setFiles(result.items)
      const availableIds = result.items.filter(isLogFile).map((file) => file.id)
      setSelectedFileIds((current) => current.filter((id) => availableIds.includes(id)))
    } catch (error) {
      setError(error instanceof Error ? error.message : '文件列表获取失败')
    } finally {
      setLoadingFiles(false)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return

    let isCurrent = true
    const token = accessToken
    const cachedTask = readCachedTask()

    async function loadFiles() {
      setLoadingFiles(true)
      setError('')
      try {
        const result = await listFiles(token)
        if (!isCurrent) return
        setFiles(result.items)
        const availableIds = result.items.filter(isLogFile).map((file) => file.id)
        setSelectedFileIds((current) => current.filter((id) => availableIds.includes(id)))
      } catch (error) {
        if (isCurrent) setError(error instanceof Error ? error.message : '文件列表获取失败')
      } finally {
        if (isCurrent) setLoadingFiles(false)
      }
    }

    void loadFiles()

    if (cachedTask) {
      void (async () => {
        try {
          const latestTask = await getSpiTask(token, cachedTask.task_id)
          if (!isCurrent) return
          setTask(latestTask)
          persistTask(latestTask)
        } catch {
          if (isCurrent) {
            persistTask(null)
          }
        }
      })()
    }

    return () => {
      isCurrent = false
    }
  }, [accessToken])

  async function handleCreateTask() {
    if (!accessToken || selectedFileIds.length === 0) return

    setSubmitting(true)
    setError('')
    try {
      const created = await createSpiTask(accessToken, { file_ids: selectedFileIds })
      setTask(created)
      persistTask(created)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'SPI 解析任务创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRefreshTask() {
    if (!accessToken || !task) return

    setRefreshingTask(true)
    setError('')
    try {
      const refreshed = await getSpiTask(accessToken, task.task_id)
      setTask(refreshed)
      persistTask(refreshed)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'SPI 解析任务查询失败')
    } finally {
      setRefreshingTask(false)
    }
  }

  async function handleDownloadResult() {
    if (!accessToken || !task?.result_file_id) return

    setError('')
    try {
      await downloadFile(accessToken, {
        id: task.result_file_id,
        filename: task.result_filename ?? `${selectedFiles[0]?.filename ?? 'spi'}_result.xlsx`,
        size: 0,
        created_at: task.updated_at,
      })
    } catch (error) {
      setError(error instanceof Error ? error.message : 'SPI 解析结果下载失败')
    }
  }

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>SPI log 解析</h2>
          <p>请先登录后再创建 SPI log 解析任务。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  return (
    <section className="task-page" aria-labelledby="spi-title">
      <div className="task-toolbar">
        <div>
          <h2 id="spi-title">创建 SPI 解析任务</h2>
          <p>{loadingFiles ? '正在读取 workspace 文件' : `可解析 log ${logFiles.length} 个`}</p>
        </div>
        <button type="button" onClick={refreshFiles} disabled={loadingFiles}>
          刷新文件
        </button>
      </div>

      <div className="task-form compact">
        <label>
          SPI log 文件
          <select
            multiple
            size={Math.min(8, Math.max(3, logFiles.length))}
            value={selectedFileIds}
            onChange={(event) =>
              setSelectedFileIds(Array.from(event.target.selectedOptions, (option) => option.value))
            }
          >
            {logFiles.map((file) => (
              <option value={file.id} key={file.id}>
                {file.filename}
              </option>
            ))}
          </select>
        </label>

        <button type="button" onClick={handleCreateTask} disabled={!canCreateTask}>
          {submitting ? '提交中' : '创建任务'}
        </button>
      </div>

      {logFiles.length === 0 && !loadingFiles && (
        <p className="file-hint">当前 workspace 没有 .log 文件，请先到文件管理上传。</p>
      )}
      {error && <p className="form-error">{error}</p>}

      {task && (
        <TaskResultPanel
          status={task.status}
          fields={[
            { label: '任务 ID', value: task.task_id },
            { label: '源文件', value: selectedFiles.map((file) => file.filename).join('，') || '-' },
            { label: '结果文件', value: task.result_filename ?? '-' },
            { label: '更新时间', value: formatDate(task.updated_at) },
          ]}
          error={task.error}
          refreshing={refreshingTask}
          canDownload={Boolean(task.result_file_id)}
          onRefresh={handleRefreshTask}
          onDownload={handleDownloadResult}
        />
      )}
    </section>
  )
}

export default SpiPage
