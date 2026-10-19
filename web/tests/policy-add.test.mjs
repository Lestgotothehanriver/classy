import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import test from 'node:test';

const execute = promisify(execFile);

test('policy add command validates and previews a new policy version', async () => {
  const { stdout } = await execute(
    process.execPath,
    ['scripts/add-policy-version.mjs', 'service-terms', '2026-10-19', '--dry-run'],
    { cwd: new URL('..', import.meta.url) },
  );

  assert.match(stdout, /Would create .*service-terms\\2026-10-19\.html/);
  assert.match(stdout, /Would update .*policies\\manifest\.json/);
  assert.match(stdout, /POLICY_VERSIONS changed/);
});
