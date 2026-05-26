import { useCallback, useEffect, useMemo, useState } from 'react'
import { createDiffTask, getDiffTask } from '../api/diff'
import { downloadFile, listFiles } from '../api/files'
import TaskResultPanel from '../components/TaskResultPanel'
import type { DiffTask } from '../types/diff'
import type { WorkspaceFile } from '../types/files'
import { scopedStorageKey } from '../utils/storageScope'

type DiffPageProps = {
  accessToken: string | null
  username: string | null
}

const LAST_TASK_BASE_KEY = 'seki_last_diff_task'

function isArchive(file: WorkspaceFile): boolean {
  return file.filename.toLowerCase().endsWith('.tar.gz')
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function readCachedTask(storageKey: string): DiffTask | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return null
    return JSON.parse(raw) as DiffTask
  } catch {
    return null
  }
}

function persistTask(storageKey: string, task: DiffTask | null): void {
  if (typeof window === 'undefined') return
  try {
    if (task) {
      window.localStorage.setItem(storageKey, JSON.stringify(task))
    } else {
      window.localStorage.removeItem(storageKey)
    }
  } catch {
    // ignore storage errors
  }
}

function DiffPage({ accessToken, username }: DiffPageProps) {
  const taskStorageKey = scopedStorageKey(LAST_TASK_BASE_KEY, username)
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [leftFileId, setLeftFileId] = useState('')
  const [rightFileId, setRightFileId] = useState('')
  const [task, setTask] = useState<DiffTask | null>(null)
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [refreshingTask, setRefreshingTask] = useState(false)
  const [error, setError] = useState('')

  const archiveFiles = useMemo(() => files.filter(isArchive), [files])
  const leftFile = useMemo(() => files.find((file) => file.id === leftFileId) ?? null, [files, leftFileId])
  const rightFile = useMemo(() => files.find((file) => file.id === rightFileId) ?? null, [files, rightFileId])
  const canCreateTask = Boolean(
    accessToken && leftFileId && rightFileId && leftFileId !== rightFileId && !submitting,
  )

  const refreshFiles = useCallback(async () => {
    if (!accessToken) return

    setLoadingFiles(true)
    setError('')
    try {
      const result = await listFiles(accessToken)
      setFiles(result.items)
      const archives = result.items.filter(isArchive)
      setLeftFileId((current) => current || archives[0]?.id || '')
      setRightFileId((current) => current || archives[1]?.id || '')
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
    const cachedTask = readCachedTask(taskStorageKey)
    queueMicrotask(() => {
      if (isCurrent) setTask(cachedTask)
    })

    async function loadFiles() {
      setLoadingFiles(true)
      setError('')
      try {
        const result = await listFiles(token)
        if (!isCurrent) return
        setFiles(result.items)
        const archives = result.items.filter(isArchive)
        setLeftFileId((current) => current || archives[0]?.id || '')
        setRightFileId((current) => current || archives[1]?.id || '')
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
          const latestTask = await getDiffTask(token, cachedTask.task_id)
          if (!isCurrent) return
          setTask(latestTask)
          persistTask(taskStorageKey, latestTask)
        } catch {
          if (isCurrent) {
            persistTask(taskStorageKey, null)
          }
        }
      })()
    }

    return () => {
      isCurrent = false
    }
  }, [accessToken, taskStorageKey])

  async function handleCreateTask() {
    if (!accessToken || !canCreateTask) return

    setSubmitting(true)
    setError('')
    try {
      const created = await createDiffTask(accessToken, {
        left_file_id: leftFileId,
        right_file_id: rightFileId,
      })
      setTask(created)
      persistTask(taskStorageKey, created)
    } catch (error) {
      setError(error instanceof Error ? error.message : '版本差分任务创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRefreshTask() {
    if (!accessToken || !task) return

    setRefreshingTask(true)
    setError('')
    try {
      const refreshed = await getDiffTask(accessToken, task.task_id)
      setTask(refreshed)
      persistTask(taskStorageKey, refreshed)
    } catch (error) {
      setError(error instanceof Error ? error.message : '版本差分任务查询失败')
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
        filename: `diff_${leftFile?.filename ?? 'left'}_${rightFile?.filename ?? 'right'}.txt`,
        size: 0,
        created_at: task.updated_at,
      })
    } catch (error) {
      setError(error instanceof Error ? error.message : '差分结果下载失败')
    }
  }

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>版本差分比较</h2>
          <p>请先登录后再创建版本差分任务。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  return (
    <section className="task-page" aria-labelledby="diff-title">
      <div className="task-toolbar">
        <div>
          <h2 id="diff-title">创建版本差分任务</h2>
          <p>{loadingFiles ? '正在读取 workspace 文件' : `可比较版本包 ${archiveFiles.length} 个`}</p>
        </div>
        <button type="button" onClick={refreshFiles} disabled={loadingFiles}>
          刷新文件
        </button>
      </div>

      <div className="task-form diff-form">
        <label>
          旧版本包
          <select value={leftFileId} onChange={(event) => setLeftFileId(event.target.value)}>
            <option value="">请选择 .tar.gz 文件</option>
            {archiveFiles.map((file) => (
              <option value={file.id} key={file.id}>
                {file.filename}
              </option>
            ))}
          </select>
        </label>

        <label>
          新版本包
          <select value={rightFileId} onChange={(event) => setRightFileId(event.target.value)}>
            <option value="">请选择 .tar.gz 文件</option>
            {archiveFiles.map((file) => (
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

      {archiveFiles.length < 2 && !loadingFiles && (
        <p className="file-hint">当前 workspace 至少需要两个 .tar.gz 文件，请先到文件管理上传。</p>
      )}
      {leftFileId && rightFileId && leftFileId === rightFileId && (
        <p className="form-error">新旧版本包不能选择同一个文件。</p>
      )}
      {error && <p className="form-error">{error}</p>}

      {task && (
        <TaskResultPanel
          status={task.status}
          fields={[
            { label: '任务 ID', value: task.task_id },
            { label: '旧版本包', value: leftFile?.filename ?? '-' },
            { label: '新版本包', value: rightFile?.filename ?? '-' },
            { label: '更新时间', value: formatDate(task.updated_at) },
            ...(task.summary
              ? [
                  {
                    label: '摘要',
                    value: `changed: ${String(task.summary.changed)}, bin: ${String(
                      task.summary.bin_changed,
                    )}, lib: ${String(task.summary.lib_changed)}`,
                  },
                ]
              : []),
          ]}
          error={task.error}
          preview={task.result_text}
          refreshing={refreshingTask}
          canDownload={Boolean(task.result_file_id)}
          onRefresh={handleRefreshTask}
          onDownload={handleDownloadResult}
        />
      )}
    </section>
  )
}

export default DiffPage
