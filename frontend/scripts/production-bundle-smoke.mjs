import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { setTimeout as delay } from 'node:timers/promises'

import { chromium } from 'playwright-chromium'

const HOST = '127.0.0.1'

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      shell: process.platform === 'win32',
      ...options,
    })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`${command} ${args.join(' ')} exited with ${code}`))
    })
  })
}

async function findOpenPort() {
  const server = createServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, HOST, resolve)
  })
  const { port } = server.address()
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  return port
}

async function waitForHttp(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs
  let lastError = null
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
      lastError = new Error(`HTTP ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await delay(250)
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError?.message || 'no response'}`)
}

async function runSmoke() {
  await run(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', 'build'])

  const port = await findOpenPort()
  const preview = spawn(
    process.execPath,
    ['./node_modules/vite/bin/vite.js', 'preview', '--host', HOST, '--port', String(port)],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  )
  const previewExited = new Promise(resolve => preview.once('exit', resolve))

  try {
    await waitForHttp(`http://${HOST}:${port}/`)

    const browser = await chromium.launch({ headless: true })
    try {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
      const startupErrors = []

      page.on('pageerror', (error) => {
        startupErrors.push(error.stack || error.message)
      })
      page.on('console', (message) => {
        if (message.type() === 'error' && message.text().includes('[vue.io startup crash]')) {
          startupErrors.push(message.text())
        }
      })

      await page.goto(`http://${HOST}:${port}/`, { waitUntil: 'networkidle', timeout: 20000 })
      await page.waitForTimeout(500)

      const bodyText = await page.locator('body').innerText().catch(() => '')

      if (/Startup error/i.test(bodyText) || startupErrors.length > 0) {
        throw new Error([
          'Production bundle failed browser startup.',
          ...startupErrors,
          bodyText.slice(0, 1000),
        ].filter(Boolean).join('\n\n'))
      }
    } finally {
      await browser.close()
    }
  } finally {
    preview.kill('SIGTERM')
    await previewExited
  }
}

runSmoke().catch((error) => {
  console.error(error)
  process.exit(1)
})
