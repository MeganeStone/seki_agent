import { API_BASE_URL } from './client'
import type { DeleteFileResponse, FileListResponse, WorkspaceFile } from '../types/files'

function authHeaders(accessToken: string): HeadersInit {
  return {
    Authorization: `Bearer ${accessToken}`,
  }
}

async function parseError(response: Response, fallback: string): Promise<Error> {
  try {
    const payload = await response.json()
    if (typeof payload?.detail === 'string') return new Error(payload.detail)
    if (typeof payload?.message === 'string') return new Error(payload.message)
  } catch {
    // Keep the fallback when the backend returns an empty or non-JSON body.
  }

  return new Error(fallback)
}

export async function listFiles(accessToken: string): Promise<FileListResponse> {
  const response = await fetch(`${API_BASE_URL}/files`, {
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '文件列表获取失败')
  }

  return response.json()
}

export async function uploadFile(accessToken: string, file: File): Promise<WorkspaceFile> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/files`, {
    method: 'POST',
    headers: authHeaders(accessToken),
    body: formData,
  })

  if (!response.ok) {
    throw await parseError(response, '文件上传失败')
  }

  return response.json()
}

export async function deleteFile(
  accessToken: string,
  fileId: string,
): Promise<DeleteFileResponse> {
  const response = await fetch(`${API_BASE_URL}/files/${fileId}`, {
    method: 'DELETE',
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '文件删除失败')
  }

  return response.json()
}

export async function downloadFile(accessToken: string, file: WorkspaceFile): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/files/${file.id}/download`, {
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '文件下载失败')
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = file.filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
