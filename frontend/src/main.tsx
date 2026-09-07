import './styles/tokens.css'
import './styles/global.css'
import './styles/animations.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'

// F050 §6.x.1: TanStack Query 仅用于 F001 偏好缓存 / 失效。
// Agent SSE 流不走 query (sse.ts 自己管理), 因此 client 不需要
// staleTime / refetchOnWindowFocus 等流式优化。
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)