import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import test from 'node:test';

const publicRoot = new URL('../public/', import.meta.url);
const manifestUrl = new URL('policies/manifest.json', publicRoot);
const manifest = JSON.parse(await readFile(manifestUrl, 'utf8'));
const documentTypes = ['privacy', 'service-terms'];

test('policy manifest points to immutable, versioned policy documents', async () => {
  for (const documentType of documentTypes) {
    const policy = manifest.documents?.[documentType];
    assert.ok(policy, `${documentType} must be present in the manifest`);
    assert.match(policy.currentVersion, /^\d{4}-\d{2}-\d{2}$/);
    assert.ok(Array.isArray(policy.versions) && policy.versions.length > 0);

    const versions = new Set();
    for (const version of policy.versions) {
      assert.match(version.version, /^\d{4}-\d{2}-\d{2}$/);
      assert.ok(!versions.has(version.version), 'versions must be unique');
      versions.add(version.version);
      assert.equal(
        version.path,
        `/policies/${documentType}/${version.version}.html`,
      );
      const source = new URL(version.path.slice(1), publicRoot);
      await access(source, constants.R_OK);
    }

    assert.ok(versions.has(policy.currentVersion));
  }
});

test('policy documents render the shared version-history control', async () => {
  for (const documentType of documentTypes) {
    const policy = manifest.documents[documentType];
    const current = policy.versions.find(
      (version) => version.version === policy.currentVersion,
    );
    const html = await readFile(
      new URL(current.path.slice(1), publicRoot),
      'utf8',
    );
    assert.match(html, new RegExp(`data-policy-document="${documentType}"`));
    assert.match(html, /src="\/policies\/policy-history\.js"/);
  }
});
