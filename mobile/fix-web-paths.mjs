// Post-export patcher, run by `npm run export:web`:
//  1. Rewrites site-root asset paths (/_expo/...) to relative — the bundle
//     is served under /m/ by the backend, absolute paths 404 otherwise.
//  2. Copies the PWA manifest + icons into the export and injects the
//     <link rel="manifest"> and theme-color tags, making /m installable
//     as an app on phones (requires HTTPS — served via `tailscale serve`).
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, '..', 'backend', 'static', 'mobile');
const indexPath = join(outDir, 'index.html');
const pwaDir = join(here, 'pwa');

let html = readFileSync(indexPath, 'utf8');

// 1. relative asset paths
html = html
  .replace('src="/_expo/', 'src="_expo/')
  .replace('href="/favicon', 'href="favicon');

// 2. PWA tags (idempotent)
if (!html.includes('rel="manifest"')) {
  html = html.replace(
    '</head>',
    '  <link rel="manifest" href="manifest.webmanifest"/>\n' +
    '  <meta name="theme-color" content="#00f0ff"/>\n' +
    '  <meta name="mobile-web-app-capable" content="yes"/>\n' +
    '  <meta name="apple-mobile-web-app-capable" content="yes"/>\n' +
    '  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>\n' +
    '</head>'
  );
}

writeFileSync(indexPath, html);

// copy manifest + icons next to index.html
for (const f of ['manifest.webmanifest', 'icon-192.png', 'icon-512.png']) {
  const src = join(pwaDir, f);
  if (existsSync(src)) copyFileSync(src, join(outDir, f));
}

console.log('patched asset paths + PWA manifest for /m serving');
