#!/usr/bin/env node
/* Unified local-network server for Nature Shield Citizen Mobile App + Embedded Voice Agent.
   - Serves citizen_app/ at /app/ (and redirects / -> /app/)
   - Injects the app file manifest & content hash into /app/sw.js for offline PWA caching
   - Serves /public/ from the bundled local snapshot (public/), OR proxies /public/ to a live
     drone-vision backend when --api <url> or DRONE_VISION_API=<url> is set
   - Starts the embedded Voice_Agents LiveKit worker (voice_agent/.venv/bin/python -m voice.agent start)
     unless --no-voice-worker is passed
   - Exposes POST /api/voice/token (invokes voice_agent/voice/mint_token.py to mint a fresh LiveKit room JWT)
     and GET /api/voice/status
   - Supports --https (auto-generates a local self-signed TLS cert with SANs for localhost & LAN IPs)
     so phones on the current Wi-Fi network can grant Microphone + GPS access
*/

import {execFile, execFileSync, spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createReadStream, existsSync, mkdirSync, readdirSync, readFileSync, statSync} from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import {networkInterfaces} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.join(ROOT, 'citizen_app');
const PUBLIC_DIR = path.join(ROOT, 'public');
const VOICE_DIR = path.join(ROOT, 'voice_agent');
const VOICE_PYTHON = path.join(VOICE_DIR, '.venv', 'bin', 'python');
const CERT_DIR = path.join(ROOT, '.certs');

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
        "media-src 'self' blob:; connect-src 'self' wss: https:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Permissions-Policy': 'geolocation=(self), camera=(), microphone=(self)',
    'Cache-Control': 'no-cache',
};

function parseArgs(argv) {
    let port = Number(process.env.PORT || 3000);
    let host = process.env.HOST || '0.0.0.0';
    let api = process.env.DRONE_VISION_API || '';
    let useHttps = process.env.USE_HTTPS === '1' || process.env.USE_HTTPS === 'true';
    let startWorker = process.env.START_VOICE_WORKER !== '0';
    for (let i = 2; i < argv.length; i++) {
        if ((argv[i] === '--port' || argv[i] === '-p') && argv[i + 1]) port = Number(argv[++i]);
        else if (argv[i] === '--host' && argv[i + 1]) host = argv[++i];
        else if (argv[i] === '--api' && argv[i + 1]) api = argv[++i];
        else if (argv[i] === '--https') useHttps = true;
        else if (argv[i] === '--no-voice-worker') startWorker = false;
    }
    return {port, host, api: api.replace(/\/+$/, ''), useHttps, startWorker};
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

function ensureSelfSignedCert(ips) {
    mkdirSync(CERT_DIR, {recursive: true});
    const keyPath = path.join(CERT_DIR, 'local-key.pem');
    const certPath = path.join(CERT_DIR, 'local-cert.pem');
    if (!existsSync(keyPath) || !existsSync(certPath)) {
        const san = ['DNS:localhost', 'IP:127.0.0.1', ...ips.map(ip => `IP:${ip}`)].join(',');
        execFileSync('openssl', [
            'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', keyPath, '-out', certPath,
            '-days', '30',
            '-subj', '/CN=NatureShieldLocal',
            '-addext', `subjectAltName=${san}`,
        ], {stdio: 'pipe'});
    }
    return {key: readFileSync(keyPath), cert: readFileSync(certPath)};
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

function sendJson(res, status, data) {
    res.writeHead(status, {...CITIZEN_HEADERS, 'Content-Type': 'application/json; charset=utf-8'});
    res.end(JSON.stringify(data));
}

function sendFile(res, filePath) {
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
        ...CITIZEN_HEADERS,
        'Content-Type': MIME[ext] || 'application/octet-stream',
    });
    createReadStream(filePath).pipe(res);
}

function readJsonBody(req) {
    return new Promise((resolve, reject) => {
        let raw = '';
        req.on('data', chunk => {
            raw += chunk;
            if (raw.length > 65536) reject(new Error('Body too large'));
        });
        req.on('end', () => {
            if (!raw.trim()) return resolve({});
            try {
                resolve(JSON.parse(raw));
            } catch (err) {
                reject(err);
            }
        });
        req.on('error', reject);
    });
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
        sendJson(res, 502, {error: 'Upstream drone-vision API unreachable', detail: String(err.message || err)});
    }
}

/* ---- Embedded Voice_Agents LiveKit worker management ---- */

let workerProc = null;

function startVoiceWorker() {
    if (!existsSync(VOICE_PYTHON)) {
        console.warn('[voice-worker] Python venv not found at', VOICE_PYTHON, '— skipping auto-start.');
        return;
    }
    if (!existsSync(path.join(VOICE_DIR, '.env'))) {
        console.warn('[voice-worker] voice_agent/.env not found — skipping auto-start.');
        return;
    }
    console.log('[voice-worker] Starting embedded Voice_Agents LiveKit worker...');
    workerProc = spawn(VOICE_PYTHON, ['-m', 'voice.agent', 'start'], {
        cwd: VOICE_DIR,
        stdio: ['ignore', 'pipe', 'pipe'],
    });
    workerProc.stdout.on('data', chunk => process.stdout.write(`[voice-worker] ${chunk}`));
    workerProc.stderr.on('data', chunk => process.stderr.write(`[voice-worker] ${chunk}`));
    workerProc.on('exit', (code, signal) => {
        console.log(`[voice-worker] Exited (code=${code}, signal=${signal})`);
        workerProc = null;
    });
}

function stopVoiceWorker() {
    if (workerProc && !workerProc.killed) {
        workerProc.kill('SIGTERM');
    }
}

function mintLiveKitToken(lang) {
    const safeLang = ['el', 'tr', 'en', 'fr'].includes(lang) ? lang : 'en';
    return new Promise((resolve, reject) => {
        if (!existsSync(VOICE_PYTHON)) {
            return reject(new Error('Voice agent Python venv not installed in voice_agent/.venv'));
        }
        execFile(
            VOICE_PYTHON,
            ['-m', 'voice.mint_token', '--lang', safeLang],
            {cwd: VOICE_DIR, timeout: 10000},
            (err, stdout, stderr) => {
                if (err) {
                    let detail = stderr.trim() || err.message;
                    try {
                        detail = JSON.parse(stderr).error || detail;
                    } catch {
                        // plain text stderr
                    }
                    return reject(new Error(detail));
                }
                try {
                    resolve(JSON.parse(stdout));
                } catch {
                    reject(new Error('Invalid token response from voice.mint_token'));
                }
            },
        );
    });
}

const {port, host, api, useHttps, startWorker} = parseArgs(process.argv);

async function handleRequest(req, res) {
    const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
    const pathname = url.pathname;

    if (pathname === '/api/voice/status' && req.method === 'GET') {
        return sendJson(res, 200, {
            workerRunning: !!workerProc,
            workerPid: workerProc?.pid ?? null,
            venvReady: existsSync(VOICE_PYTHON),
            envReady: existsSync(path.join(VOICE_DIR, '.env')),
        });
    }

    if (pathname === '/api/voice/token' && req.method === 'POST') {
        try {
            const body = await readJsonBody(req);
            const data = await mintLiveKitToken(body.lang || 'en');
            return sendJson(res, 200, data);
        } catch (err) {
            return sendJson(res, 500, {error: String(err.message || err)});
        }
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
}

const ips = lanAddresses();
const scheme = useHttps ? 'https' : 'http';
const server = useHttps
    ? https.createServer(ensureSelfSignedCert(ips), handleRequest)
    : http.createServer(handleRequest);

if (startWorker) startVoiceWorker();

for (const sig of ['SIGINT', 'SIGTERM']) {
    process.on(sig, () => {
        stopVoiceWorker();
        server.close(() => process.exit(0));
    });
}

server.listen(port, host, () => {
    console.log(`\nNature Shield Citizen Mobile App + Voice Agent running:`);
    console.log(`  Local:        ${scheme}://127.0.0.1:${port}/app/`);
    console.log(`  Mobile View:  ${scheme}://127.0.0.1:${port}/app/?view=mobile`);
    for (const ip of ips) {
        console.log(`  Phone (LAN):  ${scheme}://${ip}:${port}/app/`);
    }
    console.log(`  Voice Worker: ${startWorker ? (workerProc ? `running (pid ${workerProc.pid})` : 'not started') : 'external (--no-voice-worker)'}`);
    console.log(`  Data source:  ${api ? `Live proxy -> ${api}` : 'Bundled offline snapshot (public/)'}\n`);
});
