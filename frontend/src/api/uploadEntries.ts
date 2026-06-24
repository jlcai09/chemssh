import { listFiles, type FileItem } from './files'

export type UploadConflictAction = 'overwrite' | 'skip' | 'suffix' | 'cancel'

export type UploadConflictResolution = {
  action: UploadConflictAction
  applyAll: boolean
}

export type UploadEntry = {
  file: File
  relativePath: string
  displayPath: string
  rootName: string
}

export type PreparedUploadEntries = {
  entries: UploadEntry[]
  invalidCount: number
  renamedCount: number
  cancelled: boolean
}

export type FileSystemEntryLike = {
  isFile: boolean
  isDirectory: boolean
  name: string
  file?: (callback: (file: File) => void, errorCallback?: (error: unknown) => void) => void
  createReader?: () => {
    readEntries: (callback: (entries: FileSystemEntryLike[]) => void, errorCallback?: (error: unknown) => void) => void
  }
}

export type PrepareUploadEntriesOptions = {
  targetPath: string
  promptConflict: (name: string) => Promise<UploadConflictResolution>
}

export const SAFE_UPLOAD_SEGMENT_RE = /^[A-Za-z0-9._-]+$/

export function filesToUploadEntries(files: File[]) {
  return files
    .filter(file => file.name)
    .map(file => {
      const relativePath = sanitizeRelativePath(file.webkitRelativePath || file.name)
      return {
        file,
        relativePath,
        displayPath: relativePath,
        rootName: relativePath.split('/')[0] ?? file.name
      } satisfies UploadEntry
    })
}

export async function prepareUploadEntries(
  entries: UploadEntry[],
  options: PrepareUploadEntriesOptions
): Promise<PreparedUploadEntries> {
  const { entries: normalized, invalidCount, renamedCount } = normalizeUploadEntries(entries)
  if (normalized.length === 0) return { entries: [], invalidCount, renamedCount, cancelled: false }

  const topLevelItems = new Map((await listFiles(options.targetPath, { refresh: true })).items.map(item => [item.name, item] as const))
  const resolved: UploadEntry[] = []
  let applyAllAction: UploadConflictAction | null = null
  const groups = new Map<string, UploadEntry[]>()

  for (const entry of normalized) {
    const rootName = entry.relativePath.split('/')[0] ?? entry.file.name
    const group = groups.get(rootName)
    if (group) group.push(entry)
    else groups.set(rootName, [entry])
  }

  for (const [rootName, group] of groups) {
    const isFolderUpload = group.some(entry => entry.relativePath.includes('/'))
    const existing = topLevelItems.get(rootName) ?? null
    let action: UploadConflictAction = 'overwrite'

    if (existing) {
      const resolution: UploadConflictResolution = applyAllAction
        ? { action: applyAllAction, applyAll: true }
        : await options.promptConflict(rootName)
      if (resolution.applyAll) applyAllAction = resolution.action
      action = resolution.action
    }

    if (action === 'cancel') return { entries: [], invalidCount, renamedCount, cancelled: true }
    if (action === 'skip') continue

    let finalRootName = rootName
    if (action === 'suffix') finalRootName = uniqueSuffixedName(rootName, topLevelItems)

    for (const entry of group) {
      const suffix = entry.relativePath === rootName ? '' : entry.relativePath.slice(rootName.length)
      const relativePath = `${finalRootName}${suffix}`
      resolved.push({ ...entry, relativePath, displayPath: relativePath, rootName: finalRootName })
    }

    topLevelItems.set(finalRootName, {
      name: finalRootName,
      path: joinDisplayPath(options.targetPath, finalRootName),
      type: isFolderUpload ? 'directory' : 'file',
      size: null,
      mtime: '',
      extension: '',
      preview_type: isFolderUpload ? 'directory' : 'file',
      format: null
    })
  }

  return { entries: resolved, invalidCount, renamedCount, cancelled: false }
}

export function normalizeUploadEntries(entries: UploadEntry[]) {
  let invalidCount = 0
  let renamedCount = 0
  const normalized: UploadEntry[] = []

  for (const entry of entries) {
    const originalPath = sanitizeRelativePath(entry.relativePath)
    const originalDisplayPath = sanitizeRelativePath(entry.displayPath || entry.relativePath)
    const relativePath = normalizeUploadRelativePath(originalPath)
    const displayPath = normalizeUploadRelativePath(originalDisplayPath)
    if (!relativePath || !isSafeUploadRelativePath(relativePath)) {
      invalidCount += 1
      continue
    }
    if (relativePath !== originalPath || displayPath !== originalDisplayPath) renamedCount += 1
    normalized.push({
      ...entry,
      relativePath,
      displayPath,
      rootName: relativePath.split('/')[0] ?? entry.file.name
    })
  }

  return { entries: normalized, invalidCount, renamedCount }
}

export function sanitizeRelativePath(path: string) {
  return path.replace(/\\/g, '/').split('/').filter(part => part && part !== '.' && part !== '..').join('/')
}

export function normalizeUploadRelativePath(path: string) {
  return sanitizeRelativePath(path)
    .split('/')
    .map(part => part.replace(/\s+/g, '_'))
    .filter(Boolean)
    .join('/')
}

export function isSafeUploadRelativePath(path: string) {
  const parts = path.split('/').filter(Boolean)
  return parts.length > 0 && parts.every(part => SAFE_UPLOAD_SEGMENT_RE.test(part))
}

export function uniqueSuffixedName(name: string, existing: Map<string, FileItem>) {
  let candidate = `${name}.new`
  while (existing.has(candidate)) candidate = `${candidate}.new`
  return candidate
}

export function hasFileDrag(event: DragEvent) {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

export function setUploadDropEffect(event: DragEvent) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

export async function collectDropUploadEntries(event: DragEvent) {
  const items = Array.from(event.dataTransfer?.items ?? [])
  if (items.length > 0) {
    const entries = await Promise.all(items.map(item => collectDataTransferItem(item)))
    const flattened = entries.flat().filter(entry => entry.file.name)
    if (flattened.length > 0) return flattened
  }
  return filesToUploadEntries(Array.from(event.dataTransfer?.files ?? []).filter(file => file.name))
}

export async function collectDataTransferItem(item: DataTransferItem): Promise<UploadEntry[]> {
  if (item.kind !== 'file') return []
  const getEntry = (item as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntryLike | null }).webkitGetAsEntry
  const entry = getEntry?.call(item)
  if (!entry) {
    const file = item.getAsFile()
    return file ? filesToUploadEntries([file]) : []
  }
  return collectFileSystemEntry(entry, '')
}

export async function collectFileSystemEntry(entry: FileSystemEntryLike, parentPath: string): Promise<UploadEntry[]> {
  const relativePath = sanitizeRelativePath(parentPath ? `${parentPath}/${entry.name}` : entry.name)
  if (entry.isFile) {
    const file = await readFileSystemEntryFile(entry)
    return file
      ? [{
          file,
          relativePath,
          displayPath: relativePath,
          rootName: relativePath.split('/')[0] ?? file.name
        }]
      : []
  }
  if (!entry.isDirectory || !entry.createReader) return []
  const children = await readAllDirectoryEntries(entry)
  const nested = await Promise.all(children.map(child => collectFileSystemEntry(child, relativePath)))
  return nested.flat()
}

export function readFileSystemEntryFile(entry: FileSystemEntryLike) {
  return new Promise<File | null>(resolve => {
    if (!entry.file) {
      resolve(null)
      return
    }
    entry.file(file => resolve(file), () => resolve(null))
  })
}

export async function readAllDirectoryEntries(entry: FileSystemEntryLike) {
  const reader = entry.createReader?.()
  if (!reader) return []
  const entries: FileSystemEntryLike[] = []
  while (true) {
    const batch = await new Promise<FileSystemEntryLike[]>(resolve => {
      reader.readEntries(resolve, () => resolve([]))
    })
    if (batch.length === 0) break
    entries.push(...batch)
  }
  return entries
}

export function joinDisplayPath(parent: string, name: string) {
  if (!parent) return name
  const separator = parent.includes('\\') ? '\\' : '/'
  return `${parent.replace(/[\\/]+$/, '')}${separator}${name}`
}
