export type DiffSummary = {
  changed: boolean
  bin_changed: boolean
  lib_changed: boolean
}

export type DiffTask = {
  task_id: string
  status: string
  summary: DiffSummary | null
  result_file_id: string | null
  result_text: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export type CreateDiffTaskPayload = {
  left_file_id: string
  right_file_id: string
}
