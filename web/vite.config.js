import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
const target = process.env.CLASSY_API_URL || 'https://api.classystudy.com';
export default defineConfig({ plugins: [react()], server: { port: 4173, strictPort: true, proxy: { '/api': { target, changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') } } } });
