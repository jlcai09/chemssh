import { request } from './http'

export interface QueueItem {
  job_id: string
  name: string
  user: string
  state: string
  partition: string
  nodes?: number | null
  cpus?: number | null
  time_used: string
  time_limit: string
  reason: string
  workdir?: string | null
}

export interface QueueResponse {
  scheduler: string
  available: boolean
  message: string
  items: QueueItem[]
}

export interface QueueJobDetailResponse {
  job_id: string
  detail: Record<string, string>
}

export type QueueJobAction = 'hold' | 'release' | 'cancel'

export interface QueueJobActionResponse {
  success: boolean
  scheduler: string
  job_id: string
  action: QueueJobAction
  command: string
  message: string
}

export function listQueue() {
  return request<QueueResponse>('/api/queue/list')
}

export function cancelJob(jobId: string) {
  return runQueueAction(jobId, 'cancel')
}

export function runQueueAction(jobId: string, action: QueueJobAction) {
  return request<QueueJobActionResponse>('/api/queue/action', {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId, action })
  })
}

export function getJobDetail(jobId: string) {
  return request<QueueJobDetailResponse>(`/api/queue/job/${encodeURIComponent(jobId)}`)
}
