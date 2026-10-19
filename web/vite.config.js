import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { copyFile, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const target = process.env.CLASSY_API_URL || 'https://api.classystudy.com';

const policyAliases = () => ({
  name: 'policy-aliases',
  apply: 'build',
  async closeBundle() {
    const webRoot = process.cwd();
    const publicRoot = resolve(webRoot, 'public');
    const distRoot = resolve(webRoot, 'dist');
    const manifest = JSON.parse(
      await readFile(resolve(publicRoot, 'policies/manifest.json'), 'utf8'),
    );

    await Promise.all(
      Object.entries(manifest.documents).map(async ([documentType, policy]) => {
        const current = policy.versions.find(
          (version) => version.version === policy.currentVersion,
        );
        if (!current?.path?.startsWith('/policies/')) {
          throw new Error(`Invalid current ${documentType} policy manifest entry.`);
        }
        await copyFile(
          resolve(publicRoot, current.path.slice(1)),
          resolve(distRoot, `${documentType}.html`),
        );
      }),
    );
  },
});

export default defineConfig({ plugins: [react(), policyAliases()], server: { port: 4173, strictPort: true, proxy: { '/api': { target, changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') } } } });
