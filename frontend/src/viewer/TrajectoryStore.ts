import type { StructureFrame, TrajectoryStore } from './types'

export function isFrameAvailable(store: TrajectoryStore, frameIndex: number) {
  return frameIndex >= 0 && frameIndex < store.nFrames && (!store.availableFrames || store.availableFrames[frameIndex] === 1)
}

export function frameFromTrajectoryStore(store: TrajectoryStore, frameIndex: number): StructureFrame | null {
  if (!isFrameAvailable(store, frameIndex)) return null

  const atomOffset = frameIndex * store.nAtoms
  const positionOffset = atomOffset * 3
  const cellOffset = frameIndex * 9
  const energy = store.energy?.[frameIndex]
  const fmax = store.fmax?.[frameIndex]

  return {
    frameIndex,
    symbols: store.symbols,
    numbers: store.numbers,
    positions: store.positions.subarray(positionOffset, positionOffset + store.nAtoms * 3),
    cell: store.cells?.subarray(cellOffset, cellOffset + 9),
    pbc: store.pbc,
    tags: store.tags?.subarray(atomOffset, atomOffset + store.nAtoms),
    fixedMask: store.fixedMask?.subarray(atomOffset, atomOffset + store.nAtoms),
    energy: energy === undefined || Number.isNaN(energy) ? null : energy,
    fmax: fmax === undefined || Number.isNaN(fmax) ? null : fmax
  }
}
