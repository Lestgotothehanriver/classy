import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { once } from 'node:events';

const port = 4188;
const origin = `http://127.0.0.1:${port}`;
const manifest = JSON.parse(
  await readFile(new URL('../dist/policies/manifest.json', import.meta.url), 'utf8'),
);
const server = spawn(process.execPath, ['server.mjs'], {
  cwd: new URL('..', import.meta.url),
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port) },
  stdio: ['ignore', 'pipe', 'pipe'],
});

const waitForServer = async () => {
  let lastError;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const response = await fetch(`${origin}/privacy`);
      if (response.ok) return;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw lastError ?? new Error('Policy test server did not start.');
};

try {
  await waitForServer();

  const manifestResponse = await fetch(`${origin}/policies/manifest.json`);
  assert.equal(manifestResponse.status, 200);
  assert.match(manifestResponse.headers.get('cache-control') ?? '', /no-cache/);
  assert.deepEqual(await manifestResponse.json(), manifest);

  for (const [documentType, route] of [
    ['privacy', 'privacy'],
    ['service-terms', 'service-terms'],
  ]) {
    const policy = manifest.documents[documentType];
    const current = policy.versions.find(
      (version) => version.version === policy.currentVersion,
    );
    const expected = await readFile(
      new URL(`../dist${current.path}`, import.meta.url),
      'utf8',
    );

    for (const suffix of ['', '/', '/?embed=1']) {
      const response = await fetch(`${origin}/${route}${suffix}`);
      assert.equal(response.status, 200);
      assert.equal(await response.text(), expected);
    }

    for (const version of policy.versions) {
      const response = await fetch(`${origin}${version.path}`);
      assert.equal(response.status, 200);
    }

    assert.match(expected, new RegExp(`data-policy-document="${documentType}"`));
    assert.match(expected, new RegExp(`href="${current.path}"`));
  }

  console.log('PASS policy manifest, canonical policy routes, versioned documents, and version controls');
} finally {
  server.kill();
  await once(server, 'exit');
}
