const searchByKey = new Map<string, string>()

// 模块级缓存：侧栏切换标签页会卸载并重建队列窗口，搜索文本需要跨卸载保留；仅存在于前端内存，刷新页面即清空。
export function readCachedQueueSearch(key: string): string {
  return key ? searchByKey.get(key) ?? '' : ''
}

export function writeCachedQueueSearch(key: string, value: string): void {
  if (key) searchByKey.set(key, value)
}
