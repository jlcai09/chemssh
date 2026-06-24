import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SystemInfo } from '../api/system'
import type { LauncherBridgeSyncEvent } from '../api/launcherBridge'

export const useSystemStore = defineStore('chemssh-system', () => {
  const systemInfo = ref<SystemInfo | null>(null)
  const syncEvents = ref<LauncherBridgeSyncEvent[]>([])

  function setSystemInfo(info: SystemInfo | null) {
    systemInfo.value = info
  }

  function broadcastSyncEvents(events: LauncherBridgeSyncEvent[]) {
    syncEvents.value = [...events]
  }

  return { systemInfo, syncEvents, setSystemInfo, broadcastSyncEvents }
})
