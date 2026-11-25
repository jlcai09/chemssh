import { shallowRef } from 'vue'
import { listQueue, type QueueItem } from '../api/queue'

// 队列面板与终端共享同一份队列快照；面板卸载后快照仍可被终端读取，过期后由终端兜底拉取。
const DEFAULT_SNAPSHOT_MAX_AGE_MS = 60_000

export const queueJobsSnapshot = shallowRef<QueueItem[]>([])
export const queueSchedulerSnapshot = shallowRef('')
let snapshotSavedAt = 0
let inflight: Promise<void> | null = null

export function publishQueueJobs(items: QueueItem[], scheduler = '') {
  queueJobsSnapshot.value = items
  queueSchedulerSnapshot.value = scheduler
  snapshotSavedAt = Date.now()
}

export async function ensureQueueJobsSnapshot(maxAgeMs = DEFAULT_SNAPSHOT_MAX_AGE_MS) {
  if (snapshotSavedAt && Date.now() - snapshotSavedAt < maxAgeMs) return
  if (inflight) return inflight
  inflight = listQueue({ currentUserOnly: true })
    .then(response => publishQueueJobs(response.items, response.scheduler))
    .catch(() => undefined)
    .finally(() => {
      inflight = null
    })
  return inflight
}

export async function refreshQueueJobs() {
  if (inflight) await inflight
  return ensureQueueJobsSnapshot(0)
}
