#!/usr/bin/env node
/* Standalone mobile-ready server for the Nature Shield Citizen App.
   - Serves citizen_app/ at /app/ (and redirects / -> /app/)
   - Injects the app file manifest & content hash into /app/sw.js for offline PWA caching
   - Applies the exact same strict Content-Security-Policy & privacy headers as drone_vision/service.py
   - Serves /public/ from the bundled local snapshot (public/), OR proxies /public/ to a live
     drone-vision backend when --api <url> or DRONE_VISION_API=<url> is set
   - Binds to 0.0.0.0 by default so phones on the same Wi-Fi can open it directly
*/

import {createHash} from 'node:crypto';
import {createReadStream, existsSync, readdirSync, readFileSync, statSync} from 'node:fs';
import http from 'node:http';
import {networkInterfaces} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.join(ROOT, 'citizen_app');
const PUBLIC_DIR = path.join(ROOT, 'public');

const MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.webmanifest': 'application/manifest+json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.pbf': 'application/x-protobuf',
    '.ico': 'image/x-icon',
};

const CITIZEN_HEADERS = {
    'Content-Security-Policy':
        "default-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; child-src blob:; " +
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Permissions-Policy': 'geolocation=(self), camera=(), microphone=(self)',
    'Cache-Control': 'no-cache',
};

function parseArgs(argv) {
    let port = Number(process.env.PORT || 3000);
    let host = process.env.HOST || '0.0.0.0';
    let api = process.env.DRONE_VISION_API || '';
    let voiceApi = process.env.VOICE_API_URL || 'http://127.0.0.1:8001';
    for (let i = 2; i < argv.length; i++) {
        if ((argv[i] === '--port' || argv[i] === '-p') && argv[i + 1]) port = Number(argv[++i]);
        else if (argv[i] === '--host' && argv[i + 1]) host = argv[++i];
        else if (argv[i] === '--api' && argv[i + 1]) api = argv[++i];
        else if (argv[i] === '--voice-api' && argv[i + 1]) voiceApi = argv[++i];
    }
    return {port, host, api: api.replace(/\/+$/, ''), voiceApi: voiceApi.replace(/\/+$/, '')};
}

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

function safePath(baseDir, urlPath) {
    const clean = decodeURIComponent(urlPath).replace(/^\/+/, '');
    const resolved = path.resolve(baseDir, clean);
    if (resolved !== baseDir && !resolved.startsWith(baseDir + path.sep)) return null;
    return resolved;
}

function sendFile(res, filePath) {
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
        ...CITIZEN_HEADERS,
        'Content-Type': MIME[ext] || 'application/octet-stream',
    });
    createReadStream(filePath).pipe(res);
}

async function proxyPublic(req, res, apiBase, urlPath) {
    try {
        const upstream = await fetch(`${apiBase}${urlPath}`, {headers: {Accept: 'application/json'}});
        const body = Buffer.from(await upstream.arrayBuffer());
        res.writeHead(upstream.status, {
            ...CITIZEN_HEADERS,
            'Content-Type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
        });
        res.end(body);
    } catch (err) {
        res.writeHead(502, {...CITIZEN_HEADERS, 'Content-Type': 'application/json; charset=utf-8'});
        res.end(JSON.stringify({error: 'Upstream drone-vision API unreachable', detail: String(err.message || err)}));
    }
}

async function proxyVoice(req, res, voiceBase, urlPath) {
    try {
        const chunks = [];
        for await (const chunk of req) chunks.push(chunk);
        const body = chunks.length ? Buffer.concat(chunks) : undefined;
        const upstream = await fetch(`${voiceBase}${urlPath}`, {
            method: req.method,
            headers: {'Content-Type': req.headers['content-type'] || 'application/json', Accept: 'application/json'},
            body: req.method === 'GET' || req.method === 'HEAD' ? undefined : body,
        });
        const reply = Buffer.from(await upstream.arrayBuffer());
        res.writeHead(upstream.status, {
            ...CITIZEN_HEADERS,
            'Content-Type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
        });
        res.end(reply);
    } catch (err) {
        res.writeHead(502, {...CITIZEN_HEADERS, 'Content-Type': 'application/json; charset=utf-8'});
        res.end(JSON.stringify({error: 'Voice agent service unreachable', detail: String(err.message || err)}));
    }
}

function lanAddresses() {
    const out = [];
    for (const iface of Object.values(networkInterfaces())) {
        for (const info of iface || []) {
            if (info.family === 'IPv4' && !info.internal) out.push(info.address);
        }
    }
    return out;
}

const {port, host, api, voiceApi} = parseArgs(process.argv);

const server = http.createServer(async (req, res) => {
    const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
    const pathname = url.pathname;

    if (pathname.startsWith('/api/voice/')) {
        if (req.method !== 'GET' && req.method !== 'POST') {
            res.writeHead(405, {...CITIZEN_HEADERS, 'Content-Type': 'text/plain; charset=utf-8'});
            return res.end('Method Not Allowed');
        }
        return proxyVoice(req, res, voiceApi, pathname + url.search);
    }

    if (req.method !== 'GET' && req.method !== 'HEAD') {
        res.writeHead(405, {...CITIZEN_HEADERS, 'Content-Type': 'text/plain; charset=utf-8'});
        return res.end('Method Not Allowed');
    }

    if (pathname === '/' || pathname === '/app') {
        res.writeHead(302, {Location: `/app/${url.search}`});
        return res.end();
    }

    if (pathname === '/app/sw.js') {
        const swPath = path.join(APP_DIR, 'sw.js');
        if (!existsSync(swPath)) {
            res.writeHead(404, CITIZEN_HEADERS);
            return res.end('sw.js not found');
        }
        const {files, version} = citizenShell(APP_DIR);
        const script = readFileSync(swPath, 'utf8')
            .replace('/*FILES*/[]', JSON.stringify(files))
            .replace('/*VERSION*/', version);
        res.writeHead(200, {...CITIZEN_HEADERS, 'Content-Type': 'text/javascript; charset=utf-8'});
        return res.end(script);
    }

    if (pathname.startsWith('/app/')) {
        let rel = pathname.slice('/app/'.length);
        if (!rel || rel.endsWith('/')) rel += 'index.html';
        const filePath = safePath(APP_DIR, rel);
        if (!filePath || !existsSync(filePath) || !statSync(filePath).isFile()) {
            res.writeHead(404, CITIZEN_HEADERS);
            return res.end('Not found');
        }
        return sendFile(res, filePath);
    }

    if (pathname.startsWith('/public/')) {
        if (api) return proxyPublic(req, res, api, pathname + url.search);
        const rel = pathname.slice('/public/'.length);
        const filePath = safePath(PUBLIC_DIR, rel);
        if (!filePath || !existsSync(filePath) || !statSync(filePath).isFile()) {
            res.writeHead(404, CITIZEN_HEADERS);
            return res.end('Not found');
        }
        return sendFile(res, filePath);
    }

    res.writeHead(404, CITIZEN_HEADERS);
    res.end('Not found');
});

server.listen(port, host, () => {
    console.log(`\nNature Shield Citizen Mobile App running:`);
    console.log(`  Local:        http://127.0.0.1:${port}/app/`);
    console.log(`  Mobile View:  http://127.0.0.1:${port}/app/?view=mobile`);
    for (const ip of lanAddresses()) {
        console.log(`  Phone (LAN):  http://${ip}:${port}/app/`);
    }
    console.log(`  Data source:  ${api ? `Live proxy -> ${api}` : 'Bundled offline snapshot (public/)'}`);
    console.log(`  Voice Agent:  ${voiceApi}\n`);
});
