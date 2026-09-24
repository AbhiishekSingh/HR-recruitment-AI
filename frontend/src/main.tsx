import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import './styles/global.css'

// Chrome/Edge/Safari change a focused number input's value when the mouse
// wheel scrolls over it, even with the spinner arrows hidden via CSS. Blur
// it first so a scroll while the cursor happens to be over a CTC/experience/
// notice-period field never silently edits the number.
document.addEventListener(
  'wheel',
  () => {
    const active = document.activeElement
    if (active instanceof HTMLInputElement && active.type === 'number') {
      active.blur()
    }
  },
  { passive: true }
)

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
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
