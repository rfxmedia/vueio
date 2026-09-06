const MAX_FILE_BYTES = 32 * 1024 * 1024
const NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/
const HEADERS = new Set(['TITLE', 'LUT_3D_SIZE', 'DOMAIN_MIN', 'DOMAIN_MAX', 'LUT_3D_INPUT_RANGE'])

// Adobe Cube 1.0 table order: r + size * g + size * size * b.
// Also accepts Resolve's scalar LUT_3D_INPUT_RANGE extension.
export function parseCubeLut(text, filename = '') {
  if (typeof text !== 'string') throw new Error('The LUT must be a text .cube file.')
  if (text.length > MAX_FILE_BYTES) throw new Error('The LUT file must be 32 MiB or smaller.')
  let bytes = 0
  for (let i = 0; i < text.length; i++) {
    const point = text.codePointAt(i)
    bytes += point <= 0x7f ? 1 : point <= 0x7ff ? 2 : point <= 0xffff ? 3 : 4
    if (point > 0xffff) i++
    if (bytes > MAX_FILE_BYTES) throw new Error('The LUT file must be 32 MiB or smaller.')
  }

  let name = String(filename).split(/[\\/]/).pop().replace(/\.cube$/i, '') || 'Custom LUT'
  let size = 0
  let data = null
  let rows = 0
  let lineNumber = 0
  const seen = new Set()
  const domainMin = new Float32Array([0, 0, 0])
  const domainMax = new Float32Array([1, 1, 1])
  const fail = message => { throw new Error(`Line ${lineNumber}: ${message}`) }
  const number = token => {
    if (!NUMBER.test(token)) fail('Expected finite decimal numbers.')
    const value = Math.fround(Number(token))
    if (!Number.isFinite(value)) fail('Numbers must fit within the finite 32-bit float range.')
    return value
  }

  // Iterate instead of splitting the entire file into an array of rows.
  for (const match of text.matchAll(/([^\r\n]*)(?:\r\n|\r|\n|$)/g)) {
    lineNumber++
    const raw = match[1].trim()
    if (!raw || raw.startsWith('#')) continue
    const isTitle = /^TITLE(?:\s|$)/.test(raw)
    const line = isTitle ? raw : raw.split('#', 1)[0].trim()
    const tokens = line.split(/\s+/, 5)
    const keyword = tokens[0]

    if (keyword.startsWith('LUT_1D_')) {
      fail('1D LUTs and combined 1D shapers are not supported. Export a standalone 3D .cube LUT.')
    }
    if (HEADERS.has(keyword)) {
      if (rows) fail('LUT headers must appear before the sample rows.')
      if (seen.has(keyword)) fail(`${keyword} must appear only once.`)
      seen.add(keyword)
      if (keyword === 'TITLE') {
        const title = /^TITLE\s+"([^"]*)"\s*(?:#.*)?$/.exec(line)
        if (!title) fail('TITLE must contain one quoted name.')
        name = title[1].trim() || name
      } else if (keyword === 'LUT_3D_SIZE') {
        if (tokens.length !== 2 || !/^\d+$/.test(tokens[1])) {
          fail('LUT_3D_SIZE must be an integer from 2 to 65.')
        }
        size = Number(tokens[1])
        if (size < 2 || size > 65) fail('Supported 3D LUT sizes are 2 through 65.')
        data = new Float32Array(size ** 3 * 4)
      } else if (keyword === 'LUT_3D_INPUT_RANGE') {
        if (seen.has('DOMAIN_MIN') || seen.has('DOMAIN_MAX')) {
          fail('Use either LUT_3D_INPUT_RANGE or DOMAIN_MIN/DOMAIN_MAX, not both.')
        }
        if (tokens.length !== 3) fail('LUT_3D_INPUT_RANGE requires a minimum and maximum.')
        domainMin.fill(number(tokens[1]))
        domainMax.fill(number(tokens[2]))
      } else {
        if (seen.has('LUT_3D_INPUT_RANGE')) {
          fail('Use either LUT_3D_INPUT_RANGE or DOMAIN_MIN/DOMAIN_MAX, not both.')
        }
        if (tokens.length !== 4) fail(`${keyword} requires three numbers.`)
        const target = keyword === 'DOMAIN_MIN' ? domainMin : domainMax
        for (let channel = 0; channel < 3; channel++) target[channel] = number(tokens[channel + 1])
      }
      continue
    }

    if (/^[A-Za-z_]/.test(keyword)) fail(`Unsupported .cube directive: ${keyword.slice(0, 60)}.`)
    if (!data) fail('LUT_3D_SIZE must appear before the sample rows.')
    if (tokens.length !== 3) fail('Each sample row must contain exactly three numbers.')
    if (rows >= size ** 3) fail(`The LUT contains more than the expected ${size ** 3} sample rows.`)
    const offset = rows * 4
    data[offset] = number(tokens[0])
    data[offset + 1] = number(tokens[1])
    data[offset + 2] = number(tokens[2])
    data[offset + 3] = 1
    rows++
  }

  if (!data) throw new Error('The file is missing LUT_3D_SIZE. Select a standalone 3D .cube LUT.')
  if (rows !== size ** 3) throw new Error(`Expected ${size ** 3} sample rows; found ${rows}.`)
  for (let channel = 0; channel < 3; channel++) {
    const span = Math.fround(domainMax[channel] - domainMin[channel])
    if (!(span > 0) || !Number.isFinite(span)) {
      throw new Error('Each input domain must have a minimum below its maximum and a finite 32-bit span.')
    }
  }
  return { name, size, data, domainMin, domainMax }
}
