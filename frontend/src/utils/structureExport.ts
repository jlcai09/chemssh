import type { AseFrame } from '../types/structure'

/**
 * Export structure frame to XYZ format (Extended XYZ with Lattice info)
 */
export function exportToXYZ(frame: AseFrame, filename: string): string {
  const symbols = frame.symbols || []
  const positions = frame.positions || []
  const nAtoms = positions.length

  if (nAtoms === 0) {
    throw new Error('No atoms to export')
  }

  const lines: string[] = []

  // XYZ format: first line is number of atoms
  lines.push(String(nAtoms))

  // Second line is comment (extended XYZ format can include Lattice)
  let comment = ''

  // Add lattice vectors if periodic (extended XYZ format)
  if (frame.cell && frame.pbc && frame.pbc.some(p => p)) {
    const cell = frame.cell
    // Flatten cell vectors: Lattice="v1x v1y v1z v2x v2y v2z v3x v3y v3z"
    const lattice = [
      ...cell[0].map(v => v.toFixed(8)),
      ...cell[1].map(v => v.toFixed(8)),
      ...cell[2].map(v => v.toFixed(8))
    ].join(' ')
    comment += `Lattice="${lattice}"`
  }

  // Add properties
  const props: string[] = []
  if (frame.energy !== null && frame.energy !== undefined) {
    props.push(`energy=${frame.energy}`)
  }
  if (props.length > 0) {
    if (comment) comment += ' '
    comment += `Properties=species:S:1:pos:R:3 ${props.join(' ')}`
  }

  // If no special properties, just use filename as comment
  if (!comment) {
    comment = filename || 'Structure'
  }

  lines.push(comment)

  // Atom lines: symbol x y z
  for (let i = 0; i < nAtoms; i++) {
    const symbol = symbols[i] || 'X'
    const pos = positions[i]
    lines.push(`${symbol}  ${pos[0].toFixed(8)}  ${pos[1].toFixed(8)}  ${pos[2].toFixed(8)}`)
  }

  return lines.join('\n')
}

/**
 * Export multiple frames to XYZ format (trajectory)
 */
export function exportTrajectoryToXYZ(frames: AseFrame[], filename: string): string {
  return frames.map(frame => exportToXYZ(frame, filename)).join('\n')
}

/**
 * Export multiple frames to Arc format (trajectory)
 * Matches ASE write_dmol_arc format exactly
 */
export function exportTrajectoryToArc(frames: AseFrame[], _filename: string): string {
  if (frames.length === 0) return ''

  const lines: string[] = []

  // Arc header (only once)
  lines.push('!BIOSYM archive 3')
  lines.push('PBC=ON')

  // Export each frame
  for (const frame of frames) {
    const symbols = frame.symbols || []
    const positions = frame.positions || []
    const nAtoms = positions.length

    // Energy line (74 spaces + energy value right-aligned in 8 chars)
    const energy = frame.energy !== null && frame.energy !== undefined ? frame.energy : 0.0
    const energyStr = energy.toFixed(4)
    lines.push(`${' '.repeat(74)}${energyStr.padStart(8)}`)

    // Date line
    lines.push('!DATE     Jan 01 00:00:00 2000')

    // Cell parameters - ASE uses %9.5f format (9 chars wide, 5 decimals)
    let cellLine = 'PBC    0.0000    0.0000    0.0000   90.0000   90.0000   90.0000'
    if (frame.cell && frame.pbc && frame.pbc.some(p => p)) {
      const cell = frame.cell
      const a = Math.sqrt(cell[0][0]**2 + cell[0][1]**2 + cell[0][2]**2)
      const b = Math.sqrt(cell[1][0]**2 + cell[1][1]**2 + cell[1][2]**2)
      const c = Math.sqrt(cell[2][0]**2 + cell[2][1]**2 + cell[2][2]**2)

      const cosAlpha = (cell[1][0]*cell[2][0] + cell[1][1]*cell[2][1] + cell[1][2]*cell[2][2]) / (b * c)
      const cosBeta = (cell[0][0]*cell[2][0] + cell[0][1]*cell[2][1] + cell[0][2]*cell[2][2]) / (a * c)
      const cosGamma = (cell[0][0]*cell[1][0] + cell[0][1]*cell[1][1] + cell[0][2]*cell[1][2]) / (a * b)

      const alpha = Math.acos(Math.max(-1, Math.min(1, cosAlpha))) * 180 / Math.PI
      const beta = Math.acos(Math.max(-1, Math.min(1, cosBeta))) * 180 / Math.PI
      const gamma = Math.acos(Math.max(-1, Math.min(1, cosGamma))) * 180 / Math.PI

      // Format: 'PBC ' + 6 values each padded to 9 chars with 5 decimals
      cellLine = `PBC ${a.toFixed(5).padStart(9)} ${b.toFixed(5).padStart(9)} ${c.toFixed(5).padStart(9)} ${alpha.toFixed(5).padStart(9)} ${beta.toFixed(5).padStart(9)} ${gamma.toFixed(5).padStart(9)}`
    }
    lines.push(cellLine)

    // Atom lines matching ASE format: %-6s  %12.8f   %12.8f   %12.8f XXXX 1      xx      %-2s  0.000
    // Symbol+index left-aligned in 6 chars, 2 spaces, then coords in 12.8f (12 chars, 8 decimals), 3 spaces between coords
    for (let i = 0; i < nAtoms; i++) {
      const symbol = symbols[i] || 'X'
      const pos = positions[i]

      // Symbol field: symbol + 1-based index, left-aligned in 6 characters, then 2 spaces
      const symbolWithIndex = `${symbol}${i + 1}`.padEnd(6)

      // Coordinates: 12 characters wide with 8 decimal places, 3 spaces between
      const x = pos[0].toFixed(8).padStart(12)
      const y = pos[1].toFixed(8).padStart(12)
      const z = pos[2].toFixed(8).padStart(12)

      // Full line format
      lines.push(`${symbolWithIndex}  ${x}   ${y}   ${z} XXXX 1      xx      ${symbol.padEnd(2)}  0.000`)
    }

    lines.push('end')
    lines.push('end')
  }

  return lines.join('\n')
}

/**
 * Trigger download of text content as a file
 */
export function downloadTextFile(content: string, filename: string, mimeType = 'text/plain') {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * Get base filename without extension
 */
export function getBaseFilename(path: string): string {
  const name = path.split(/[\\/]/).pop() || 'structure'
  return name.replace(/\.[^.]*$/, '')
}
