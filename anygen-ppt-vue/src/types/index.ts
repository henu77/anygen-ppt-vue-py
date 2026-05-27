export interface Task {
  id: number
  key_id: number
  url: string
  email: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  file_path: string | null
  error_msg: string | null
  created_at: string
  completed_at: string | null
}

export interface TaskStats {
  total: number
  pending: number
  done: number
  failed: number
}

export interface ExportResponse {
  taskId: number
  status: string
}

export interface Key {
  id: number
  key: string
  max_uses: number
  used_count: number
  is_super: number
  status: string
  created_at: string
}

export interface AuthResponse {
  valid: boolean
}
