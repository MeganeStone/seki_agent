import { useCallback, useEffect, useMemo, useState } from 'react'
import { downloadFile, listFiles } from '../api/files'
import { createSpiTask, getSpiTask } from '../api/spi'
import TaskResultPanel from '../components/TaskResultPanel'
import type { WorkspaceFile } from '../types/files'
import type { SpiTask } from '../types/spi'

type SpiPageProps = {
  accessToken: string | null
}

function isLogFile(file: WorkspaceFile): boolean {
  return file.filename.toLowerCase().endsWith('.log')
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function SpiPage({ accessToken }: SpiPageProps) {
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [selectedFileId, setSelectedFileId] = useState('')
  const [task, setTask] = useState<SpiTask | null>(null)
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [refreshingTask, setRefreshingTask] = useState(false)
  const [error, setError] = useState('')

  const logFiles = useMemo(() => files.filter(isLogFile), [files])
  const selectedFile = useMemo(
    () => files.find((file) => file.id === selectedFileId) ?? null,
    [files, selectedFileId],
  )
  const canCreateTask = Boolean(accessToken && selectedFileId && !submitting)

  const refreshFiles = useCallback(async () => {
    if (!accessToken) return

    setLoadingFiles(true)
    setError('')
    try {
      const result = await listFiles(accessToken)
      setFiles(result.items)
      const firstLog = result.items.find(isLogFile)
      setSelectedFileId((current) => current || firstLog?.id || '')
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

    async function loadFiles() {
      setLoadingFiles(true)
      setError('')
      try {
        const result = await listFiles(token)
        if (!isCurrent) return
        setFiles(result.items)
        const firstLog = result.items.find(isLogFile)
        setSelectedFileId((current) => current || firstLog?.id || '')
      } catch (error) {
        if (isCurrent) setError(error instanceof Error ? error.message : '文件列表获取失败')
      } finally {
        if (isCurrent) setLoadingFiles(false)
      }
    }

    void loadFiles()

    return () => {
      isCurrent = false
    }
  }, [accessToken])

  async function handleCreateTask() {
    if (!accessToken || !selectedFileId) return

    setSubmitting(true)
    setError('')
    try {
      setTask(await createSpiTask(accessToken, { file_id: selectedFileId }))
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
      setTask(await getSpiTask(accessToken, task.task_id))
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
        filename: `${selectedFile?.filename ?? 'spi'}_result.xlsx`,
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
          <select value={selectedFileId} onChange={(event) => setSelectedFileId(event.target.value)}>
            <option value="">请选择 .log 文件</option>
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
            { label: '源文件', value: selectedFile?.filename ?? '-' },
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
