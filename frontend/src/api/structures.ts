import { request } from './http'
import { API_BASE, ApiError } from './http'
import type { AseFrame, AseFrameChunk, AseFrameJsonChunk, AsePreviewResponse, BinaryArraySpec } from '../types/structure'

function aseQuery(path: string, format?: string | null, force = false) {
  const params = new URLSearchParams({ path })
  if (format) params.set('format', format)
  if (force) params.set('force', 'true')
  return params
}

export function readAsePreview(path: string, format?: string | null, force = false) {
  return request<AsePreviewResponse>(`/api/structures/ase/preview?${aseQuery(path, format, force).toString()}`)
}

export function readAseFrame(path: string, index: number, format?: string | null, force = false) {
  const params = aseQuery(path, format, force)
  params.set('index', String(index))
  return request<AseFrame>(`/api/structures/ase/frame?${params.toString()}`)
}

export function readAseFrameJsonChunk(path: string, start: number, count: number, format?: string | null, force = false) {
  const params = aseQuery(path, format, force)
  params.set('start', String(start))
  params.set('count', String(count))
  return request<AseFrameJsonChunk>(`/api/structures/ase/frames?${params.toString()}`)
}

export async function readAseFrameChunk(path: string, start: number, count: number, format?: string | null, force = false): Promise<AseFrameChunk> {
  const params = aseQuery(path, format, force)
  params.set('start', String(start))
  params.set('count', String(count))

  const response = await fetch(`${API_BASE}/api/structures/ase/frames.bin?${params.toString()}`, {
    headers: { Accept: 'application/vnd.chemweb.structure+bin' }
  })

  if (!response.ok) {
    const text = await response.text()
    let code = 'HTTP_ERROR'
    let message = response.statusText
    if (text) {
      try {
        const data = JSON.parse(text)
        code = data?.error?.code ?? code
        message = data?.error?.message ?? message
      } catch {
        message = text
      }
    }
    throw new ApiError(code, message)
  }

  const buffer = await response.arrayBuffer()
  const view = new DataView(buffer)
  const magic = new TextDecoder().decode(buffer.slice(0, 4))
  if (magic !== 'CWB1') {
    throw new ApiError('INVALID_STRUCTURE_BINARY', 'Invalid structure binary payload')
  }

  const headerLength = view.getUint32(4, true)
  const headerStart = 8
  const headerEnd = headerStart + headerLength
  const header = JSON.parse(new TextDecoder().decode(buffer.slice(headerStart, headerEnd)))
  const padding = (4 - (headerLength % 4)) % 4
  const dataStart = headerEnd + padding

  function floatArray(spec?: BinaryArraySpec) {
    if (!spec) return undefined
    return new Float32Array(buffer, dataStart + spec.offset, spec.byte_length / Float32Array.BYTES_PER_ELEMENT)
  }

  function intArray(spec?: BinaryArraySpec) {
    if (!spec) return undefined
    return new Int32Array(buffer, dataStart + spec.offset, spec.byte_length / Int32Array.BYTES_PER_ELEMENT)
  }

  function uint8Array(spec?: BinaryArraySpec) {
    if (!spec) return undefined
    return new Uint8Array(buffer, dataStart + spec.offset, spec.byte_length)
  }

  const positions = floatArray(header.arrays.positions)
  if (!positions) throw new ApiError('INVALID_STRUCTURE_BINARY', 'Structure binary payload has no positions array')

  return {
    header,
    buffer,
    dataStart,
    positions,
    cells: floatArray(header.arrays.cells) ?? new Float32Array(),
    tags: intArray(header.arrays.tags),
    fixedMask: uint8Array(header.arrays.fixed_mask),
    energy: floatArray(header.arrays.energy),
    fmax: floatArray(header.arrays.fmax)
  }
}
