import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './components/ui/index.css'
import App from './App.tsx'
import ToastContainer from './components/ui/ToastContainer'
import { ToastProvider } from './components/ui/useToast'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <App />
      <ToastContainer />
    </ToastProvider>
  </StrictMode>,
)
