// Zero-missing-key check: every data-i18n key in index.html and every
// t('…') call in src must exist in both languages, and both languages
// must have the same keys. Unused keys are warnings, not failures.
import { readFileSync, readdirSync } from 'node:fs';
import { I18N } from '../src/i18n.js';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const htmlKeys = [...html.matchAll(/data-i18n="([^"]+)"/g)].map((m) => m[1]);
const srcFiles = readdirSync(new URL('../src', import.meta.url)).filter((f) => f.endsWith('.js'));
let jsKeys = [];
for (const f of srcFiles) {
  const src = readFileSync(new URL(`../src/${f}`, import.meta.url), 'utf8');
  jsKeys.push(...[...src.matchAll(/\bt\(\s*['"]([a-z][a-z0-9]*(?:\.[a-zA-Z0-9]+)+)['"]/g)].map((m) => m[1]));
}
const used = [...new Set([...htmlKeys, ...jsKeys])];
let fail = 0;
for (const lang of Object.keys(I18N)) {
  for (const k of used) {
    if (!(k in I18N[lang])) { console.error(`MISSING ${lang}: ${k}`); fail++; }
  }
  for (const k of Object.keys(I18N[lang])) {
    if (!used.includes(k)) console.warn(`UNUSED ${lang}: ${k}`);
  }
}
const enKeys = Object.keys(I18N.en).sort().join('\n');
const zhKeys = Object.keys(I18N.zh).sort().join('\n');
if (enKeys !== zhKeys) { console.error('KEY SETS DIFFER between en and zh'); fail++; }
console.log(fail === 0 ? `i18n OK: ${used.length} keys used, ${Object.keys(I18N.en).length} per language` : `i18n FAIL: ${fail} problems`);
process.exit(fail === 0 ? 0 : 1);
