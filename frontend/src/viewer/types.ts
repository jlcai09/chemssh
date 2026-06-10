export type ViewerStyleMode = 'stick' | 'sphere' | 'line'
export type AtomIndexBase = 0 | 1

export interface ViewerStyle {
  mode?: ViewerStyleMode
  atomScale?: number
  bondRadius?: number
  bondScale?: number
  backgroundColor?: string
  showCell?: boolean
}

export interface LabelOptions {
  showAtomIndex?: boolean
  showAtomTag?: boolean
  atomIndexBase?: AtomIndexBase
  maxLabels?: number
}

export interface FixedAtomOptions {
  show?: boolean
  color?: string
}

export interface SupercellOptions {
  x?: number
  y?: number
  z?: number
}

export interface StructureDisplayOptions {
  supercell?: SupercellOptions
  wrap?: boolean
}

export interface ViewerOptions {
  backgroundColor?: string
  style?: ViewerStyle
  labelOptions?: LabelOptions
  fixedAtomOptions?: FixedAtomOptions
  displayOptions?: StructureDisplayOptions
}

export interface SetStructureOptions {
  keepView?: boolean
}

export interface SetTrajectoryOptions {
  keepView?: boolean
  initialFrameIndex?: number
}

export interface StructureFrame {
  frameIndex: number
  symbols: string[]
  numbers: number[]
  positions: Float32Array | number[][]
  cell?: Float32Array | number[][]
  pbc?: boolean[]
  tags?: Int32Array | number[]
  fixedMask?: Uint8Array
  fixedIndices?: number[]
  energy?: number | null
  fmax?: number | null
}

export interface TrajectoryStore {
  nFrames: number
  nAtoms: number
  symbols: string[]
  numbers: number[]
  positions: Float32Array
  cells?: Float32Array
  tags?: Int32Array
  fixedMask?: Uint8Array
  energy?: Float32Array
  fmax?: Float32Array
  pbc?: boolean[]
  availableFrames?: Uint8Array
  initialFrameIndex?: number
}
