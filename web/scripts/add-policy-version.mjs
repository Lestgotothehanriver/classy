import { access, readFile, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const usage = `Usage: npm run policy:add -- <privacy|service-terms> <YYYY-MM-DD> [--dry-run]`;
const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const positional = args.filter((argument) => argument !== '--dry-run');
const [documentType, nextVersion] = positional;
const policySettingKey = {
  privacy: 'privacy',
  'service-terms': 'terms',
};

const fail = (message) => {
  throw new Error(`${message}\n${usage}`);
};

const isIsoDate = (value) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value ?? '')) return false;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};

const koreanEffectiveDate = (version) => {
  const [year, month, day] = version.split('-').map(Number);
  return `${year}년 ${month}월 ${day}일`;
};

const replaceRequired = (source, search, replacement, description) => {
  if (!source.includes(search)) fail(`Could not find ${description} in the current document.`);
  return source.replaceAll(search, replacement);
};

const replaceSingle = (source, pattern, replacement, description) => {
  const flags = pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`;
  const matches = source.match(new RegExp(pattern.source, flags)) ?? [];
  if (matches.length !== 1) {
    fail(`Expected exactly one ${description} in the current document.`);
  }
  return source.replace(pattern, replacement);
};

if (!policySettingKey[documentType]) fail('Document type must be privacy or service-terms.');
if (!isIsoDate(nextVersion)) fail('Version must be a real YYYY-MM-DD date.');

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const backendRoot = resolve(webRoot, '..');
const publicRoot = resolve(webRoot, 'public');
const manifestPath = resolve(publicRoot, 'policies/manifest.json');
const settingsPath = resolve(backendRoot, 'config/settings/base.py');
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
const policy = manifest.documents?.[documentType];

if (!policy?.currentVersion || !Array.isArray(policy.versions)) {
  fail(`Missing ${documentType} policy manifest entry.`);
}
if (policy.versions.some((version) => version.version === nextVersion)) {
  fail(`${documentType} ${nextVersion} already exists.`);
}

const current = policy.versions.find(
  (version) => version.version === policy.currentVersion,
);
if (!current?.path?.startsWith('/policies/')) {
  fail(`Missing current ${documentType} document path.`);
}

const sourcePath = resolve(publicRoot, current.path.slice(1));
const targetPath = resolve(
  publicRoot,
  'policies',
  documentType,
  `${nextVersion}.html`,
);
try {
  await access(targetPath, constants.F_OK);
  fail(`Target document already exists: ${targetPath}`);
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}

const sourceHtml = await readFile(sourcePath, 'utf8');
const nextPath = `/policies/${documentType}/${nextVersion}.html`;
let nextHtml = replaceRequired(
  sourceHtml,
  `data-policy-version="${policy.currentVersion}"`,
  `data-policy-version="${nextVersion}"`,
  'the current policy version marker',
);
nextHtml = replaceSingle(
  nextHtml,
  new RegExp(
    `href="/policies/${documentType}/[^"/]+\\.html"([^>]*)>시행일 \\d{4}-\\d{2}-\\d{2}`,
  ),
  `href="${nextPath}"$1>시행일 ${nextVersion}`,
  'the current policy version link',
);
nextHtml = replaceSingle(
  nextHtml,
  /<div class="meta">시행일 \d{4}년 \d{1,2}월 \d{1,2}일/,
  `<div class="meta">시행일 ${koreanEffectiveDate(nextVersion)}`,
  'document header effective date',
);

const settings = await readFile(settingsPath, 'utf8');
const settingPattern = new RegExp(
  `(\\"${policySettingKey[documentType]}\\"\\s*:\\s*\\")([^\\"]+)(\\")`,
);
const settingMatch = settings.match(settingPattern);
if (!settingMatch) fail(`Could not find ${policySettingKey[documentType]} in POLICY_VERSIONS.`);
if (settingMatch[2] !== policy.currentVersion) {
  fail(
    `POLICY_VERSIONS has ${settingMatch[2]}, but the web manifest has ${policy.currentVersion}. Resolve this mismatch before adding another version.`,
  );
}
const nextSettings = settings.replace(
  settingPattern,
  `$1${nextVersion}$3`,
);

const nextManifest = structuredClone(manifest);
nextManifest.documents[documentType].currentVersion = nextVersion;
nextManifest.documents[documentType].versions.unshift({
  version: nextVersion,
  path: nextPath,
});

if (!dryRun) {
  await writeFile(targetPath, nextHtml, 'utf8');
  await writeFile(manifestPath, `${JSON.stringify(nextManifest, null, 2)}\n`, 'utf8');
  await writeFile(settingsPath, nextSettings, 'utf8');
}

console.log(`${dryRun ? 'Would create' : 'Created'} ${targetPath}`);
console.log(`${dryRun ? 'Would update' : 'Updated'} ${manifestPath}`);
console.log(`${dryRun ? 'Would update' : 'Updated'} ${settingsPath}`);
console.log('Edit the new HTML body, then run: npm test && npm run build');
console.log('Deploy both web and API because POLICY_VERSIONS changed: bash deploy/aws/deploy.sh all');
