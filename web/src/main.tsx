import '@razorpay/blade/fonts.css'
import { BladeProvider } from '@razorpay/blade/components'
import { bladeTheme } from '@razorpay/blade/tokens'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './global.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BladeProvider themeTokens={bladeTheme} colorScheme="light">
      <App />
    </BladeProvider>
  </StrictMode>,
)
