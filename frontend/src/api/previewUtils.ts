import { ElMessageBox } from 'element-plus'
import { ApiError } from './http'
import { t } from '../i18n'

export type PreviewKind = 'text' | 'structure'

export function isLargePreviewError(error: unknown, code: 'FILE_TOO_LARGE' | 'STRUCTURE_FILE_TOO_LARGE') {
  return error instanceof ApiError && error.code === code
}

export async function confirmLargePreview(error: unknown, kind: PreviewKind) {
  const message = previewApiErrorMessage(error)
  const title = kind === 'structure' ? t('preview.largeStructureTitle') : t('preview.largeFileTitle')
  const body = kind === 'structure'
    ? t('preview.largeStructureMessage', { message })
    : t('preview.largeFileMessage', { message })

  try {
    await ElMessageBox.confirm(body, title, {
      confirmButtonText: t('preview.loadAnyway'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    return true
  } catch {
    return false
  }
}

export function previewApiErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'FILE_TOO_LARGE') return fileSizeLimitMessage(error.message, 'text') ?? t('error.fileTooLarge')
    if (error.code === 'STRUCTURE_FILE_TOO_LARGE') return fileSizeLimitMessage(error.message, 'structure') ?? t('error.structureFileTooLarge')
    if (error.code === 'STRUCTURE_TOO_MANY_FRAMES') return frameLimitMessage(error.message) ?? t('error.structureTooManyFrames')
    if (error.code === 'STRUCTURE_TOO_MANY_ATOMS') return atomLimitMessage(error.message) ?? t('error.structureTooManyAtoms')
    if (error.code === 'INVALID_FRAME_RANGE') return t('error.invalidFrameRange')
    if (error.code === 'FRAME_INDEX_OUT_OF_RANGE') return t('error.frameIndexOutOfRange')
  }
  return error instanceof Error ? error.message : t('message.previewFailed')
}

export function normalizeTextLineEndings(content: string) {
  return content.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
}

function fileSizeLimitMessage(message: string, kind: PreviewKind) {
  const match = message.match(/File is (\d+) bytes;.*?(?:larger than|limit is) (\d+) bytes/i)
  if (!match) return null
  const size = formatByteCount(Number(match[1]))
  const limit = formatByteCount(Number(match[2]))
  return kind === 'structure'
    ? t('error.structureFileTooLargeDetail', { size, limit })
    : t('error.fileTooLargeDetail', { size, limit })
}

function frameLimitMessage(message: string) {
  const match = message.match(/more than (\d+) frames/i)
  if (!match) return null
  return t('error.structureTooManyFramesDetail', { limit: Number(match[1]) })
}

function atomLimitMessage(message: string) {
  const match = message.match(/Structure has (\d+) atoms; limit is (\d+)/i)
  if (!match) return null
  return t('error.structureTooManyAtomsDetail', { count: Number(match[1]), limit: Number(match[2]) })
}

function formatByteCount(bytes: number) {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}
