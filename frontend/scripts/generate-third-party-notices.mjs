import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const outputPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(root, 'public', 'THIRD_PARTY_NOTICES.txt')
const lock = JSON.parse(fs.readFileSync(path.join(root, 'package-lock.json'), 'utf8'))

function repositoryUrl(value) {
  const repository = typeof value === 'string' ? value : value?.url
  return String(repository || '')
    .replace(/^git\+/, '')
    .replace(/^git:\/\//, 'https://')
    .replace(/\.git$/, '')
}

function noticeFiles(directory) {
  return fs.readdirSync(directory)
    .filter(name => /^(licen[cs]e|copying|notice)(\.|$)/i.test(name))
    .sort((left, right) => left.localeCompare(right))
}

const packages = []
for (const [packagePath, locked] of Object.entries(lock.packages || {})) {
  if (!packagePath.startsWith('node_modules/') || locked.dev) continue
  const directory = path.join(root, packagePath)
  const manifestPath = path.join(directory, 'package.json')
  if (!fs.existsSync(manifestPath)) continue

  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
  const name = manifest.name || packagePath.slice('node_modules/'.length)
  const version = manifest.version || locked.version || 'unknown'
  const license = manifest.license || locked.license || 'NOASSERTION'
  const source = repositoryUrl(manifest.repository) ||
    manifest.homepage ||
    `https://www.npmjs.com/package/${encodeURIComponent(name)}/v/${encodeURIComponent(version)}`
  const notices = noticeFiles(directory).map(filename => ({
    filename,
    text: fs.readFileSync(path.join(directory, filename), 'utf8').trim(),
  }))
  packages.push({ name, version, license, source, notices })
}

packages.sort((left, right) =>
  left.name.localeCompare(right.name) || left.version.localeCompare(right.version)
)

const lines = [
  'Vueio UI third-party notices',
  '================================',
  '',
  'Generated from the production packages installed by package-lock.json.',
  'Source locations and declared licenses are retained even when an npm',
  'package does not include a standalone license file in its archive.',
  '',
]

for (const item of packages) {
  lines.push(`${item.name}@${item.version}`, `License: ${item.license}`, `Source: ${item.source}`)
  if (item.notices.length) {
    for (const notice of item.notices) {
      lines.push('', `--- ${notice.filename} ---`, notice.text)
    }
  } else {
    lines.push('', 'No standalone license file was included in this package archive; see the source location above.')
  }
  lines.push('', '------------------------------------------------------------------------', '')
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true })
fs.writeFileSync(outputPath, `${lines.join('\n')}\n`, 'utf8')
