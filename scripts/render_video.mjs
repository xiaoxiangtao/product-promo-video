// 逐帧渲染 HTML 动画：无头 Chrome + CDP 调 render(t) 截图 → 管道交给 ffmpeg（H.264）。
// 页面约定：全局函数 render(t)（t 为秒，纯函数）、window.__ready（Promise，素材加载完）、window.DURATION（秒，可选）。
// 用法：
//   node render_video.mjs video  <page.html> <out.mp4> [--fps 30] [--dur 秒] [--from 秒] [--to 秒] [--query "lang=en&anon=1"] [--size 1920x1080]
//   node render_video.mjs stills <page.html> <outDir> <t1,t2,...> [--query ...]
//   node render_video.mjs sheet  <page.html> <outDir> [--every 2] [--query ...]   # 每隔 N 秒一张静帧，供 finalize.py sheet 拼总览
// 依赖：Node ≥ 22（原生 WebSocket）、ffmpeg、Chrome/Chromium（可用环境变量 CHROME 指定路径）。日志：./log/render_video.log
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, appendFileSync, rmSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [mode, page, out, ...rest] = process.argv.slice(2);
if (!mode || !page || !out) { console.error('用法见文件头注释'); process.exit(2); }
const opt = {}; const pos = [];
for (let i = 0; i < rest.length; i++) rest[i].startsWith('--') ? (opt[rest[i].slice(2)] = rest[++i]) : pos.push(rest[i]);
const [W, H] = (opt.size || '1920x1080').split('x').map(Number);

mkdirSync('log', { recursive: true });
const LOG = join('log', 'render_video.log');
const log = m => { const l = `[${new Date().toISOString()}] ${m}`; console.log(l); appendFileSync(LOG, l + '\n'); };

const CHROME = process.env.CHROME || ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  'C:/Program Files/Google/Chrome/Application/chrome.exe'].find(existsSync);
if (!CHROME) { console.error('找不到 Chrome，请用环境变量 CHROME 指定'); process.exit(2); }
const PORT = 9300 + Math.floor(Math.random() * 600);
const profile = join(process.env.TMPDIR || '/tmp', `promo-chrome-${PORT}`);
rmSync(profile, { recursive: true, force: true });
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, `--window-size=${W},${H}`,
  '--hide-scrollbars', '--force-device-scale-factor=1', '--allow-file-access-from-files', '--force-color-profile=srgb', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));

let ws, seq = 0, pageError = null; const pending = new Map();
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
async function connect() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const pg = l.find(x => x.type === 'page'); if (pg) return pg.webSocketDebuggerUrl; } catch {} await sleep(200); }
  throw new Error('chrome not reachable');
}
const evalJS = async expr => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || JSON.stringify(r.exceptionDetails)); return r.result.value; };

try {
  ws = new WebSocket(await connect());
  await new Promise(r => ws.addEventListener('open', r));
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.method === 'Runtime.exceptionThrown') pageError = m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text;
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
  });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  const url = pathToFileURL(resolve(page)).href + (opt.query ? '?' + opt.query : '');
  await send('Page.navigate', { url }); await sleep(800);
  await evalJS('window.__ready');
  if (pageError) throw new Error('页面脚本报错：' + pageError);
  const pageDur = await evalJS('window.DURATION||0');
  log(`ready ${url}  DURATION=${pageDur}`);
  const shot = async t => {
    await evalJS(`render(${t});true`);
    if (pageError) throw new Error(`t=${t} 页面脚本报错：${pageError}`);
    return Buffer.from((await send('Page.captureScreenshot', { format: 'jpeg', quality: 95 })).data, 'base64');
  };

  if (mode === 'stills' || mode === 'sheet') {
    mkdirSync(out, { recursive: true });
    const every = Number(opt.every || 2);
    const ts = mode === 'stills' ? pos[0].split(',').map(Number) : Array.from({ length: Math.ceil(pageDur / every) }, (_, i) => i * every);
    for (const t of ts) writeFileSync(join(out, `t${t.toFixed(2).padStart(6, '0')}.jpg`), await shot(t));
    log(`${mode}: ${ts.length} 张 → ${out}`);
  } else {
    const fps = Number(opt.fps || 30), dur = Number(opt.dur || pageDur);
    if (!dur) throw new Error('页面没有 window.DURATION，请用 --dur 指定时长');
    const f0 = Math.round(Number(opt.from || 0) * fps), f1 = Math.round(Number(opt.to || dur) * fps);
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(fps), '-i', '-',
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    for (let f = f0; f < f1; f++) {
      const buf = await shot(f / fps);
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if ((f - f0) % 150 === 0) log(`frame ${f - f0}/${f1 - f0}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
    ff.stdin.end(); await new Promise(r => ff.on('close', r));
    log(`video done → ${out} (${f1 - f0} frames @${fps}fps, ${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
} catch (e) { log('ERROR ' + (e.stack || e)); process.exitCode = 1; }
finally {
  ws?.close(); const exited = new Promise(r => chrome.once('exit', r)); chrome.kill(); await Promise.race([exited, sleep(3000)]);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 3 }); } catch {}
}
