import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Rafraîchissement « temps réel » pour refléter l'état des verrous.
      refetchInterval: 4000,
      refetchOnWindowFocus: true,
      staleTime: 2000,
    },
  },
})

const root = createRoot(document.getElementById('root')!)
root.render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)

const preloader = document.getElementById('tk-preloader')
if (preloader) {
  const MIN_DISPLAY = 2500
  const shown = (window as any).__TK_START__ ?? Date.now()
  const hide = () => {
    preloader.classList.add('tk-hide')
    setTimeout(() => preloader.remove(), 450)
  }
  const elapsed = Date.now() - shown
  const remaining = MIN_DISPLAY - elapsed
  setTimeout(hide, Math.max(0, remaining))
}
