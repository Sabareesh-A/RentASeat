import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const DEFAULT_API_GATEWAY_URL = 'https://wmic9c9ilf.execute-api.ap-south-1.amazonaws.com'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // Target for local dev proxy is the upstream API Gateway URL, separate from
  // the frontend request prefix (VITE_API_URL, which defaults to '/api').
  const apiGatewayTarget = env.VITE_API_GATEWAY_URL || DEFAULT_API_GATEWAY_URL

  return {
    plugins: [react()],

    server: {
      proxy: {
        // During local dev, proxy /api/* to the API Gateway so the browser
        // never makes a cross-origin request and CORS is not an issue.
        // The frontend code uses VITE_API_URL (e.g. '/api') as the base path.
        //
        // In production (S3 + CloudFront), CloudFront behaviour rules will
        // forward /api/* to API Gateway directly — no dev proxy needed.
        '/api': {
          target: apiGatewayTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
          secure: true,
        },
      },
    },
  }
})
