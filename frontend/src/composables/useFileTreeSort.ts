import { computed, ref, type Ref } from 'vue'
import { locale, t } from '../i18n'
import type { FileItem } from '../api/files'

export type SortKey = 'name' | 'size' | 'mtime'
export type SortDirection = 'asc' | 'desc'

export function useFileTreeSort(items: Ref<FileItem[]>) {
  const sortKey = ref<SortKey>('name')
  const sortDirection = ref<SortDirection>('asc')

  const nameCollator = computed(
    () =>
      new Intl.Collator(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
        numeric: true,
        sensitivity: 'base'
      })
  )

  function typeRank(item: FileItem) {
    return item.type === 'directory' ? 0 : 1
  }

  function nameCompare(a: FileItem, b: FileItem) {
    return nameCollator.value.compare(a.name, b.name)
  }

  function timestamp(value: string) {
    const time = new Date(value).getTime()
    return Number.isNaN(time) ? 0 : time
  }

  function compareItems(a: FileItem, b: FileItem) {
    let result = 0
    if (sortKey.value === 'name') {
      result = nameCompare(a, b)
    } else if (sortKey.value === 'size') {
      result = (a.size ?? -1) - (b.size ?? -1)
    } else {
      result = timestamp(a.mtime) - timestamp(b.mtime)
    }
    return result === 0 ? nameCompare(a, b) : result
  }

  const sortedItems = computed(() => {
    return [...items.value].sort((a, b) => {
      const typeCompare = typeRank(a) - typeRank(b)
      if (typeCompare !== 0) return typeCompare
      const result = compareItems(a, b)
      return sortDirection.value === 'asc' ? result : -result
    })
  })

  function sortFieldLabel(key: SortKey) {
    if (key === 'name') return t('file.name')
    if (key === 'size') return t('file.size')
    return t('file.modified')
  }

  function sortAria(key: SortKey) {
    if (sortKey.value !== key) return 'none'
    return sortDirection.value === 'asc' ? 'ascending' : 'descending'
  }

  function sortTitle(key: SortKey) {
    const direction =
      sortDirection.value === 'asc' ? t('file.sortAscending') : t('file.sortDescending')
    return sortKey.value === key
      ? `${t('file.sortBy', { field: sortFieldLabel(key) })}: ${direction}`
      : t('file.sortBy', { field: sortFieldLabel(key) })
  }

  function toggleSort(key: SortKey) {
    if (sortKey.value === key) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortKey.value = key
      sortDirection.value = 'asc'
    }
  }

  return { sortKey, sortDirection, sortedItems, toggleSort, sortAria, sortTitle, sortFieldLabel }
}
