import { listFiles, type FileItem, type MovePathEntry } from './files'
import { ApiError } from './http'
import { joinDisplayPath, type UploadConflictAction, type UploadConflictResolution, uniqueSuffixedName } from './uploadEntries'

export interface PreparedMoveEntries {
  entries: MovePathEntry[]
  cancelled: boolean
  skippedCount: number
}

export interface PrepareMoveEntriesOptions {
  targetPath: string
  promptConflict: (name: string) => Promise<UploadConflictResolution>
}

export async function prepareMoveEntries(
  items: Pick<FileItem, 'name' | 'path' | 'type'>[],
  options: PrepareMoveEntriesOptions
): Promise<PreparedMoveEntries> {
  const targetItems = new Map((await listFiles(options.targetPath, { refresh: true })).items.map(item => [item.name, item] as const))
  const entries: MovePathEntry[] = []
  let skippedCount = 0
  let applyAllAction: UploadConflictAction | null = null

  for (const item of items) {
    const existing = targetItems.get(item.name) ?? null
    let action: UploadConflictAction = 'overwrite'

    if (existing) {
      const resolution: UploadConflictResolution = applyAllAction
        ? { action: applyAllAction, applyAll: true }
        : await options.promptConflict(item.name)
      if (resolution.applyAll) applyAllAction = resolution.action
      action = resolution.action
    }

    if (action === 'cancel') return { entries: [], cancelled: true, skippedCount }
    if (action === 'skip') {
      skippedCount += 1
      continue
    }

    const targetName = action === 'suffix' ? uniqueSuffixedName(item.name, targetItems) : item.name
    entries.push({
      path: item.path,
      targetName,
      overwrite: action === 'overwrite' && Boolean(existing)
    })
    targetItems.set(targetName, {
      name: targetName,
      path: joinDisplayPath(options.targetPath, targetName),
      type: item.type,
      size: null,
      mtime: '',
      extension: '',
      preview_type: item.type === 'directory' ? 'directory' : 'file',
      format: null
    })
  }

  return { entries, cancelled: false, skippedCount }
}

const MOVE_ERROR_MESSAGES: Record<string, string> = {
  MOVE_FAILED: '移动失败：后端移动命令执行失败，请检查源路径、目标文件夹和权限。',
  PERMISSION_DENIED: '移动失败：权限不足，无法移动所选项目。',
  PATH_NOT_FOUND: '移动失败：源文件或文件夹不存在，可能已被移动或删除。',
  DIRECTORY_NOT_FOUND: '移动失败：目标文件夹不存在，可能已被移动或删除。',
  NOT_A_DIRECTORY: '移动失败：目标路径不是文件夹，无法作为移动位置。',
  PATH_EXISTS: '移动失败：目标位置已存在同名项目，请选择覆盖、跳过或添加后缀后再移动。',
  MOVE_INTO_SELF: '移动失败：不能把文件夹移动到它自身或它的子文件夹中。',
  MOVE_SAME_PATH: '移动失败：源位置和目标位置相同。',
  MOVE_TYPE_CONFLICT: '移动失败：同名项目类型不同，不能用文件覆盖文件夹或用文件夹覆盖文件。',
  MOVE_WORKSPACE_ROOT: '移动失败：不能移动工作区根目录。',
  NO_PATHS: '移动失败：没有选择要移动的文件或文件夹。',
  FORBIDDEN_PATH: '移动失败：源路径或目标路径超出了工作区范围。',
  INVALID_NAME: '移动失败：目标名称包含不支持的字符。'
}

const LEGACY_GENERIC_MOVE_ERRORS = new Set([
  'Cannot move selected path',
  'Cannot move selected paths',
  'Move failed'
])

export function moveApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const message = error.message.trim()
    if (message.startsWith('移动失败')) return message
    if (message && /[\u4e00-\u9fff]/.test(message)) return `移动失败：${message}`
    const fallback = MOVE_ERROR_MESSAGES[error.code]
    if (fallback) {
      if (!message || LEGACY_GENERIC_MOVE_ERRORS.has(message)) return fallback
      return `${fallback} 原始错误：${message}`
    }
    if (message) return `移动失败：${message}`
  }

  if (error instanceof Error) {
    const message = error.message.trim()
    if (message.startsWith('移动失败')) return message
    if (!message || LEGACY_GENERIC_MOVE_ERRORS.has(message)) return MOVE_ERROR_MESSAGES.MOVE_FAILED
    return `移动失败：${message}`
  }

  return MOVE_ERROR_MESSAGES.MOVE_FAILED
}

const COPY_ERROR_MESSAGES: Record<string, string> = {
  COPY_FAILED: '复制失败：后端复制操作失败，请检查源路径、目标文件夹和权限。',
  PERMISSION_DENIED: '复制失败：权限不足，无法复制所选项目。',
  PATH_NOT_FOUND: '复制失败：源文件或文件夹不存在，可能已被移动或删除。',
  DIRECTORY_NOT_FOUND: '复制失败：目标文件夹不存在，可能已被移动或删除。',
  NOT_A_DIRECTORY: '复制失败：目标路径不是文件夹，无法作为复制位置。',
  PATH_EXISTS: '复制失败：目标位置已存在同名项目，请选择覆盖、跳过或添加后缀后再复制。',
  COPY_INTO_SELF: '复制失败：不能把文件夹复制到它自身或它的子文件夹中。',
  COPY_SAME_PATH: '复制失败：源位置和目标位置相同。',
  COPY_TYPE_CONFLICT: '复制失败：同名项目类型不同，不能用文件覆盖文件夹或用文件夹覆盖文件。',
  COPY_WORKSPACE_ROOT: '复制失败：不能复制工作区根目录。',
  NO_PATHS: '复制失败：没有选择要复制的文件或文件夹。',
  FORBIDDEN_PATH: '复制失败：源路径或目标路径超出了工作区范围。',
  INVALID_NAME: '复制失败：目标名称包含不支持的字符。'
}

const LEGACY_GENERIC_COPY_ERRORS = new Set([
  'Cannot copy selected path',
  'Cannot copy selected paths',
  'Copy failed'
])

export function copyApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const message = error.message.trim()
    if (message.startsWith('复制失败')) return message
    if (message && /[\u4e00-\u9fff]/.test(message)) return `复制失败：${message}`
    const fallback = COPY_ERROR_MESSAGES[error.code]
    if (fallback) {
      if (!message || LEGACY_GENERIC_COPY_ERRORS.has(message)) return fallback
      return `${fallback} 原始错误：${message}`
    }
    if (message) return `复制失败：${message}`
  }

  if (error instanceof Error) {
    const message = error.message.trim()
    if (message.startsWith('复制失败')) return message
    if (!message || LEGACY_GENERIC_COPY_ERRORS.has(message)) return COPY_ERROR_MESSAGES.COPY_FAILED
    return `复制失败：${message}`
  }

  return COPY_ERROR_MESSAGES.COPY_FAILED
}
