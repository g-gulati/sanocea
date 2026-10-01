import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    rollupOptions: {
      input: {
        main:            resolve(__dirname, 'index.html'),
        // demo.html → Canonical SANOCEA Commerce Command Center (Dashboard + WhatsApp Ops)
        demo:            resolve(__dirname, 'demo.html'),
        // whatsapp-demo.html → Backwards-compatible canonical redirect to demo.html?tab=whatsapp
        'whatsapp-demo': resolve(__dirname, 'whatsapp-demo.html'),
        reconciliation:  resolve(__dirname, 'solutions/marketplace-reconciliation/index.html'),
      },
    },
  },
})
