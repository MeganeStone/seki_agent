export type WorkspaceFile = {
  id: string
  filename: string
  size: number
  created_at: string
}

export type FileListResponse = {
  items: WorkspaceFile[]
}

export type DeleteFileResponse = {
  deleted: boolean
}
