#!/usr/bin/env node
/* Builds a self-contained static site in dist/ for GitHub Pages (or any static HTTPS host).
   Layout:
     dist/
       .nojekyll
       index.html   -> redirects to ./app/
       app/         -> citizen_app/ with sw.js pre-filled with FILES & VERSION
       public/      -> bundled offline area pack snapshot
*/

import {createHash} from 'node:crypto';
import {cpSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(ROOT, '..');
const APP_SRC = path.join(REPO, 'citizen_app');
const PUBLIC_SRC = path.join(REPO, 'public');
const DIST = path.join(REPO, 'dist');

function citizenShell(folder) {
    const files = [];
    const hash = createHash('sha256');
    function walk(dir) {
        const entries = readdirSync(dir, {withFileTypes: true}).sort((a, b) => a.name.localeCompare(b.name));
        for (const entry of entries) {
            if (entry.name.startsWith('.')) continue;
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                walk(full);
            } else {
                const rel = path.relative(folder, full).split(path.sep).join('/');
                if (entry.name.endsWith('.md') || entry.name.endsWith('.txt') || rel === 'sw.js' || rel === 'package.json') continue;
                const fileDigest = createHash('sha256').update(readFileSync(full)).digest();
                hash.update(Buffer.from(`${rel}\0`));
                hash.update(fileDigest);
                files.push(rel === 'index.html' ? './' : rel);
            }
        }
    }
    walk(folder);
    return {files, version: hash.digest('hex').slice(0, 16)};
}

rmSync(DIST, {recursive: true, force: true});
mkdirSync(DIST, {recursive: true});

cpSync(APP_SRC, path.join(DIST, 'app'), {recursive: true});
cpSync(PUBLIC_SRC, path.join(DIST, 'public'), {recursive: true});

const {files, version} = citizenShell(APP_SRC);
const swPath = path.join(DIST, 'app', 'sw.js');
const swBuilt = readFileSync(swPath, 'utf8')
    .replace('/*FILES*/[]', JSON.stringify(files))
    .replace('/*VERSION*/', version);
writeFileSync(swPath, swBuilt, 'utf8');

writeFileSync(path.join(DIST, '.nojekyll'), '', 'utf8');
writeFileSync(
    path.join(DIST, 'index.html'),
    `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url=./app/">
<title>Safe places · Nature Shield</title>
</head>
<body>
<p>Opening <a href="./app/">Safe places · Nature Shield</a>…</p>
</body>
</html>
`,
    'utf8',
);

console.log(`Built static GitHub Pages bundle in dist/ (${files.length} app files, sw version ${version})`);
