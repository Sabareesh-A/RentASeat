import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],

    server: {
      proxy: {
        // During local dev, proxy /api/* to the API Gateway so the browser
        // never makes a cross-origin request and CORS is not an issue.
        // VITE_API_URL still controls where requests go; the frontend code
        // uses '/api' as the base path when this proxy is active.
        //
        // In production (S3 + CloudFront), CloudFront behaviour rules will
        // forward /api/* to API Gateway directly — no proxy needed.
        '/api': {
          target: env.VITE_API_URL ?? 'https://wmic9c9ilf.execute-api.ap-south-1.amazonaws.com',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
          secure: true,
        },
      },
    },
  }
})
