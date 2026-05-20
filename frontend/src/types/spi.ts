export type SpiTask = {
  task_id: string
  status: string
  result_file_id: string | null
  result_filename: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export type CreateSpiTaskPayload = {
  file_id?: string
  file_ids?: string[]
}
