import { useCallback, useEffect, useMemo, useState } from 'react'
import { downloadFile, listFiles } from '../api/files'
import { createTranslationTask, getTranslationTask } from '../api/translation'
import TaskResultPanel from '../components/TaskResultPanel'
import type { WorkspaceFile } from '../types/files'
import type { TranslationTask } from '../types/translation'

type TranslationPageProps = {
  accessToken: string | null
}

const targetLanguages = ['英语', '日语', '中文', '德语', '法语']
const supportedSuffixes = ['.pptx', '.xlsx', '.docx']

function isSupportedDocument(file: WorkspaceFile): boolean {
  return supportedSuffixes.some((suffix) => file.filename.toLowerCase().endsWith(suffix))
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function TranslationPage({ accessToken }: TranslationPageProps) {
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [selectedFileId, setSelectedFileId] = useState('')
  const [targetLanguage, setTargetLanguage] = useState(targetLanguages[0])
  const [customLanguage, setCustomLanguage] = useState('')
  const [task, setTask] = useState<TranslationTask | null>(null)
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [refreshingTask, setRefreshingTask] = useState(false)
  const [error, setError] = useState('')

  const documentFiles = useMemo(() => files.filter(isSupportedDocument), [files])
  const selectedFile = useMemo(
    () => files.find((file) => file.id === selectedFileId) ?? null,
    [files, selectedFileId],
  )
  const effectiveTargetLanguage = customLanguage.trim() || targetLanguage
  const canCreateTask = Boolean(accessToken && selectedFileId && effectiveTargetLanguage && !submitting)

  const refreshFiles = useCallback(async () => {
    if (!accessToken) return

    setLoadingFiles(true)
    setError('')
    try {
      const result = await listFiles(accessToken)
      setFiles(result.items)
      const firstDocument = result.items.find(isSupportedDocument)
      setSelectedFileId((current) => current || firstDocument?.id || '')
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
        const firstDocument = result.items.find(isSupportedDocument)
        setSelectedFileId((current) => current || firstDocument?.id || '')
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
      const created = await createTranslationTask(accessToken, {
        file_id: selectedFileId,
        target_language: effectiveTargetLanguage,
      })
      setTask(created)
    } catch (error) {
      setError(error instanceof Error ? error.message : '翻译任务创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRefreshTask() {
    if (!accessToken || !task) return

    setRefreshingTask(true)
    setError('')
    try {
      setTask(await getTranslationTask(accessToken, task.task_id))
    } catch (error) {
      setError(error instanceof Error ? error.message : '翻译任务查询失败')
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
        filename: `${selectedFile?.filename ?? 'translated'}_${task.target_language}`,
        size: 0,
        created_at: task.updated_at,
      })
    } catch (error) {
      setError(error instanceof Error ? error.message : '翻译结果下载失败')
    }
  }

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>文档翻译</h2>
          <p>请先登录后再创建翻译任务。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  return (
    <section className="task-page" aria-labelledby="translation-title">
      <div className="task-toolbar">
        <div>
          <h2 id="translation-title">创建翻译任务</h2>
          <p>{loadingFiles ? '正在读取 workspace 文件' : `可翻译文档 ${documentFiles.length} 个`}</p>
        </div>
        <button type="button" onClick={refreshFiles} disabled={loadingFiles}>
          刷新文件
        </button>
      </div>

      <div className="task-form">
        <label>
          源文件
          <select value={selectedFileId} onChange={(event) => setSelectedFileId(event.target.value)}>
            <option value="">请选择文档</option>
            {documentFiles.map((file) => (
              <option value={file.id} key={file.id}>
                {file.filename}
              </option>
            ))}
          </select>
        </label>

        <label>
          目标语言
          <select value={targetLanguage} onChange={(event) => setTargetLanguage(event.target.value)}>
            {targetLanguages.map((language) => (
              <option value={language} key={language}>
                {language}
              </option>
            ))}
          </select>
        </label>

        <label>
          自定义目标语言
          <input
            value={customLanguage}
            onChange={(event) => setCustomLanguage(event.target.value)}
            placeholder="可选，填写后优先生效"
          />
        </label>

        <button type="button" onClick={handleCreateTask} disabled={!canCreateTask}>
          {submitting ? '提交中' : '创建任务'}
        </button>
      </div>

      {documentFiles.length === 0 && !loadingFiles && (
        <p className="file-hint">当前 workspace 没有 .pptx、.xlsx 或 .docx 文件，请先到文件管理上传。</p>
      )}
      {error && <p className="form-error">{error}</p>}

      {task && (
        <TaskResultPanel
          status={task.status}
          fields={[
            { label: '任务 ID', value: task.task_id },
            { label: '目标语言', value: task.target_language },
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

export default TranslationPage
