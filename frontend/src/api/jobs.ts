import { request } from './http'

export interface SubmitJobResponse {
  success: boolean
  scheduler: string
  job_id?: string | null
  message: string
}

export type SubmitCommand = 'sbatch' | 'qsub'

export function submitJob(workdir: string, script = 'run.sh', command: SubmitCommand = 'sbatch') {
  return request<SubmitJobResponse>('/api/jobs/submit', {
    method: 'POST',
    body: JSON.stringify({ workdir, script, command })
  })
}
