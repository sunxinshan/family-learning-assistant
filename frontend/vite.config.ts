import { defineConfig, loadEnv } from 'vite'
import type { ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * 部署位置由 VITE_BASE_PATH 决定（见 .env.production，例如 /zijixue/）。
 * 本地开发默认取 /，行为不变。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  const base = env.VITE_BASE_PATH || '/'

  const proxy: Record<string, string | ProxyOptions> = {
    '/api': 'http://127.0.0.1:8000',
  }

  // 子路径部署时（base=/zijixue/）开发环境的接口请求是 /zijixue/api/v1/...，
  // 需要剥掉前缀再转给后端，与生产 nginx 的行为保持一致。
  if (base !== '/') {
    const prefix = base.replace(/\/$/, '')
    proxy[`${prefix}/api`] = {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(new RegExp(`^${prefix}`), ''),
    }
  }

  return {
    base,
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy,
    },
  }
})
