// After `expo export --platform web`, index.html points at assets with
// site-root paths (/_expo/...). The bundle is served under /m/ by the
// backend, so rewrite them to relative paths or the page loads blank.
import { readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';

const target = fileURLToPath(new URL('../backend/static/mobile/index.html', import.meta.url));
let html = readFileSync(target, 'utf8');
html = html
  .replace('src="/_expo/', 'src="_expo/')
  .replace('href="/favicon', 'href="favicon');
writeFileSync(target, html);
console.log('patched asset paths for /m serving');
