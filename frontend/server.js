// Serves the built app (dist/) online, e.g. on Railway: `npm start` after `npm run build`.
// No packages needed. Any path that isn't a file gets index.html, so React
// Router pages like /eucl/users still open when the browser is refreshed.
import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer } from 'node:http'
import { extname, join, normalize, resolve, sep } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const DIST = resolve(fileURLToPath(new URL('.', import.meta.url)), 'dist')
const INDEX = join(DIST, 'index.html')
const PORT = Number(process.env.PORT) || 3000

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json',
}

function fileFor(urlPath) {
  let path
  try {
    path = decodeURIComponent(urlPath.split('?')[0])
  } catch {
    return null
  }
  const full = normalize(join(DIST, path))
  if (full !== DIST && !full.startsWith(DIST + sep)) return null // outside dist/
  return existsSync(full) && statSync(full).isFile() ? full : null
}

const server = createServer((req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' }).end()
    return
  }
  const file = fileFor(req.url || '/') ?? INDEX
  const headers = {
    'Content-Type': TYPES[extname(file).toLowerCase()] ?? 'application/octet-stream',
    'X-Content-Type-Options': 'nosniff',
    // Vite gives built files a hash in their name, so they can be kept a year;
    // index.html must always be fresh so a new deploy shows straight away.
    'Cache-Control': file.includes(`${sep}assets${sep}`) ? 'public, max-age=31536000, immutable' : 'no-cache',
  }
  res.writeHead(200, headers)
  if (req.method === 'HEAD') res.end()
  else createReadStream(file).pipe(res)
})

server.listen(PORT, '0.0.0.0', () => console.log(`Wellness frontend on port ${PORT}`))
