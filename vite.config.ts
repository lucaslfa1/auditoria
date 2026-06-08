import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'

const packageJson = JSON.parse(readFileSync('./package.json', 'utf-8'))
const appVersion = resolveAppVersion(packageJson.version)

function parseSemver(value: string): [number, number, number] | null {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:$|[-_])/.exec(value)
  if (!match) return null
  return [Number(match[1]), Number(match[2]), Number(match[3])]
}

function formatSemver(value: [number, number, number]): string {
  return `${value[0]}.${value[1]}.${value[2]}`
}

function compareSemver(left: [number, number, number], right: [number, number, number]): number {
  if (left[0] !== right[0]) return left[0] - right[0]
  if (left[1] !== right[1]) return left[1] - right[1]
  return left[2] - right[2]
}

function getLatestLogVersion(): string | null {
  const logsDir = join(process.cwd(), 'logs', 'versions')
  if (!existsSync(logsDir)) return null

  const versions = readdirSync(logsDir)
    .map((fileName) => parseSemver(fileName.replace(/\.md$/i, '')))
    .filter((version): version is [number, number, number] => version !== null)

  if (versions.length === 0) return null

  versions.sort(compareSemver)

  return formatSemver(versions[versions.length - 1])
}

function resolveAppVersion(packageVersion: string): string {
  const packageSemver = parseSemver(packageVersion)
  const logVersion = getLatestLogVersion()
  const logSemver = logVersion ? parseSemver(logVersion) : null

  if (!packageSemver) return logVersion || packageVersion
  if (!logSemver) return packageVersion

  return compareSemver(logSemver, packageSemver) >= 0 ? logVersion! : packageVersion
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_URL || 'http://localhost:8080'

  return {
    plugins: [react()],
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
    },
    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
