import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ChangeEvent } from 'react'
import { deleteFile, downloadFile, listFiles, uploadFile } from '../api/files'
import type { WorkspaceFile } from '../types/files'

type FilesPageProps = {
  accessToken: string | null
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function FilesPage({ accessToken }: FilesPageProps) {
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const canUpload = useMemo(() => Boolean(accessToken && selectedFile && !uploading), [
    accessToken,
    selectedFile,
    uploading,
  ])

  const refreshFiles = useCallback(async () => {
    if (!accessToken) return

    setLoading(true)
    setError('')
    try {
      const result = await listFiles(accessToken)
      setFiles(result.items)
    } catch (error) {
      setError(error instanceof Error ? error.message : '文件列表获取失败')
    } finally {
      setLoading(false)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return

    let isCurrent = true
    const token = accessToken

    async function loadFiles() {
      setLoading(true)
      setError('')
      try {
        const result = await listFiles(token)
        if (isCurrent) setFiles(result.items)
      } catch (error) {
        if (isCurrent) setError(error instanceof Error ? error.message : '文件列表获取失败')
      } finally {
        if (isCurrent) setLoading(false)
      }
    }

    void loadFiles()

    return () => {
      isCurrent = false
    }
  }, [accessToken])

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0] ?? null)
    setMessage('')
    setError('')
  }

  async function handleUpload() {
    if (!accessToken || !selectedFile) return

    setUploading(true)
    setError('')
    setMessage('')
    try {
      await uploadFile(accessToken, selectedFile)
      setSelectedFile(null)
      setMessage('上传完成')
      await refreshFiles()
    } catch (error) {
      setError(error instanceof Error ? error.message : '文件上传失败')
    } finally {
      setUploading(false)
    }
  }

  async function handleDownload(file: WorkspaceFile) {
    if (!accessToken) return

    setError('')
    setMessage('')
    try {
      await downloadFile(accessToken, file)
    } catch (error) {
      setError(error instanceof Error ? error.message : '文件下载失败')
    }
  }

  async function handleDelete(fileId: string) {
    if (!accessToken) return

    setError('')
    setMessage('')
    try {
      await deleteFile(accessToken, fileId)
      setMessage('文件已删除')
      await refreshFiles()
    } catch (error) {
      setError(error instanceof Error ? error.message : '文件删除失败')
    }
  }

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>文件管理</h2>
          <p>请先登录后再访问个人 workspace 文件。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  return (
    <section className="files-page" aria-labelledby="files-title">
      <div className="files-toolbar">
        <div>
          <h2 id="files-title">Workspace 文件</h2>
          <p>{loading ? '正在刷新文件列表' : `共 ${files.length} 个文件`}</p>
        </div>
        <button type="button" onClick={refreshFiles} disabled={loading}>
          刷新
        </button>
      </div>

      <div className="upload-panel">
        <input type="file" onChange={handleFileChange} />
        <button type="button" onClick={handleUpload} disabled={!canUpload}>
          {uploading ? '上传中' : '上传'}
        </button>
      </div>

      {selectedFile && (
        <p className="file-hint">
          待上传：{selectedFile.name}，{formatBytes(selectedFile.size)}
        </p>
      )}
      {message && <p className="form-message">{message}</p>}
      {error && <p className="form-error">{error}</p>}

      <div className="file-table" role="table" aria-label="workspace 文件列表">
        <div className="file-row file-head" role="row">
          <span role="columnheader">文件名</span>
          <span role="columnheader">大小</span>
          <span role="columnheader">创建时间</span>
          <span role="columnheader">操作</span>
        </div>

        {files.map((file) => (
          <div className="file-row" role="row" key={file.id}>
            <span role="cell" title={file.filename}>
              {file.filename}
            </span>
            <span role="cell">{formatBytes(file.size)}</span>
            <span role="cell">{formatDate(file.created_at)}</span>
            <span className="file-actions" role="cell">
              <button type="button" onClick={() => handleDownload(file)}>
                下载
              </button>
              <button type="button" onClick={() => handleDelete(file.id)}>
                删除
              </button>
            </span>
          </div>
        ))}

        {!loading && files.length === 0 && <div className="empty-state">暂无文件</div>}
      </div>
    </section>
  )
}

export default FilesPage
