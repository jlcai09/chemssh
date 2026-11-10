import { computed, ref } from 'vue'
import type { FileItem } from '../api/files'

/**
 * Files copied from the file manager, kept in memory so they can be pasted into
 * another directory (or another file-manager window) later.
 */
export type FileClipboardItem = Pick<FileItem, 'name' | 'path' | 'type'>

const items = ref<FileClipboardItem[]>([])

export const fileClipboardItems = computed(() => items.value)
export const hasFileClipboard = computed(() => items.value.length > 0)

export function setFileClipboard(entries: FileClipboardItem[]) {
  items.value = entries.map(entry => ({ name: entry.name, path: entry.path, type: entry.type }))
}
