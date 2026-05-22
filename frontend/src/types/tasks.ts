export type TaskType = 'translation' | 'spi' | 'diff'

export type UnifiedTask = {
  task_id: string
  type: TaskType
  status: string
  result_file_id: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export type TaskListResponse = {
  items: UnifiedTask[]
}
