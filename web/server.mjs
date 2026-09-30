import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { fileURLToPath } from 'node:url';
const app = express();
const origin = process.env.CLASSY_API_URL || 'https://api.classystudy.com';
app.disable('x-powered-by');
app.use((req, res, next) => { res.setHeader('X-Content-Type-Options', 'nosniff'); res.setHeader('Referrer-Policy', 'same-origin'); if (req.url.startsWith('/api/')) res.setHeader('Cache-Control', 'no-store'); next(); });
// Mounting /api strips the prefix. The upstream remains fixed and credentials are never logged.
app.use('/api', createProxyMiddleware({target: origin, changeOrigin: true, proxyTimeout: 600000, on: { error: (_err, _req, res) => { if (!res.headersSent) res.writeHead(502, {'Content-Type':'application/json'}); res.end(JSON.stringify({detail:'서버 연결에 실패했습니다. 잠시 후 다시 시도해 주세요.'})); } } }));
const dist = fileURLToPath(new URL('./dist/', import.meta.url));
app.get(['/privacy', '/privacy/'], (_req,res) => res.sendFile(dist + 'privacy.html'));
app.get(['/service-terms', '/service-terms/'], (_req,res) => res.sendFile(dist + 'service-terms.html'));
app.use(express.static(dist, {extensions: ['html']}));
app.get('/{*path}', (_req, res) => res.sendFile(dist + 'index.html'));
app.listen(Number(process.env.PORT || 4173), process.env.HOST || '127.0.0.1', () => console.log('Classy Web: http://127.0.0.1:' + (process.env.PORT || 4173)));
