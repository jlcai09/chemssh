export interface StructureSource {
  id: string
  parser: string
  apiBase: string
}

export interface AseFrame {
  frame_index: number
  positions: number[][]
  cell: number[][]
  pbc: boolean[]
  tags: number[]
  fixed_indices: number[]
  energy?: number | null
  fmax?: number | null
  symbols?: string[] | null
  numbers?: number[] | null
}

export interface AsePreviewResponse {
  path: string
  name: string
  format?: string | null
  transport: 'json' | 'binary-available'
  is_trajectory: boolean
  n_frames: number
  n_atoms: number
  initial_frame_index: number
  topology_stable: boolean
  size_limit_overridden?: boolean
  frame: AseFrame
  source?: StructureSource
  file_incomplete?: boolean
  scan_completed?: boolean
  warnings?: string[]
}

export interface BinaryArraySpec {
  offset: number
  byte_length: number
  shape: number[]
}

export interface AseFrameChunkHeader {
  version: number
  dtype: 'float32-le'
  int_dtype: 'int32-le'
  start: number
  count: number
  n_frames_total: number
  n_atoms: number
  topology_stable: boolean
  frame_encoding?: 'variable-atoms-v1'
  path?: string
  name?: string
  format?: string | null
  symbols: string[]
  numbers: number[]
  pbc: boolean[]
  arrays: Record<string, BinaryArraySpec>
  nan_means_null?: string[]
}

export interface AseFrameChunk {
  header: AseFrameChunkHeader
  buffer: ArrayBuffer
  dataStart: number
  positions: Float32Array
  cells: Float32Array
  tags?: Int32Array
  fixedMask?: Uint8Array
  energy?: Float32Array
  fmax?: Float32Array
  // Variable-topology (frame_encoding === 'variable-atoms-v1') fields.
  // positions is flattened to [total_atoms, 3]; numbers/tags/fixedMask are
  // concatenated by frame with offsets derived from frameAtomCounts prefix sums.
  frameAtomCounts?: Int32Array
  numbers?: Int32Array
  pbc?: Uint8Array
}

export interface AseFrameJsonChunk {
  start: number
  count: number
  frames: AseFrame[]
}

export type FragmentQueryMode =
  | 'connected'
  | 'same_formula'
  | 'within_radius'
  | 'whole_molecule_wrap'

export interface AseFragmentRequest {
  path: string
  format?: string | null
  force?: boolean
  frame_index: number
  bond_scale: number
  seed_atoms?: number[]
  mode: FragmentQueryMode
  use_pbc?: boolean
  radius?: number
  expand_fragments?: boolean
}

export interface AseFragmentResponse {
  frame_index: number
  mode: FragmentQueryMode
  atom_indices: number[]
  fragment_count: number
  formulas: string[]
  wrapped_positions?: number[][] | null
}

export type DynamicRuleType =
  | 'formula'
  | 'shell'
  | 'coordination'
  | 'slice'
  | 'minority'
  | 'element_fixed'

export type CoordOperator = 'eq' | 'ne' | 'lt' | 'le' | 'gt' | 'ge'

export type DynamicDisplayStyle = 'stick' | 'sphere' | 'line' | 'dim' | 'hidden'

export interface DynamicDisplayRule {
  id: string
  enabled: boolean
  type: DynamicRuleType
  style: DynamicDisplayStyle
  formulas?: string[]
  anchor_type?: 'atoms' | 'elements'
  anchor_atoms?: number[]
  anchor_elements?: string[]
  radius?: number
  outside?: boolean
  expand_fragments?: boolean
  elements?: string[]
  operator?: CoordOperator
  count?: number
  axis?: 'x' | 'y' | 'z'
  min_val?: number | null
  max_val?: number | null
  fractional?: boolean
  max_fraction?: number
  invert?: boolean
  fixed_only?: boolean
}

export interface AseDynamicDisplayRequest {
  path: string
  format?: string | null
  force?: boolean
  frame_index: number
  bond_scale: number
  use_pbc?: boolean
  default_style?: DynamicDisplayStyle
  rules: DynamicDisplayRule[]
}

export interface AseDynamicDisplayResponse {
  frame_index: number
  atom_modes: number[]
  rule_match_counts: Record<string, number>
  available_formulas: string[]
}
