"""把时间轴里的 voice 台词合成为人声，叠到配乐上，并在说话时压低配乐（ducking）。
用法：python add_voice.py <promo.html> <music.wav> <out.wav> [--tts say|files] [--voice Daniel] [--style clean|speaker] [--gain -6] [--duck -6]
- 台词写在页面 #timeline 的 voice 数组：{"at": [小节,拍] 或秒, "to": ..., "text": "...", "file": "可选，录好的 wav"}。
  画面里的字幕可以读同一份 voice，保证字幕与人声对齐。
- --tts say：macOS 自带 say（-v 选声音；它几乎不响应语速参数，句子过长会被 atempo 压缩，最多 1.25 倍）。
  --tts files：每句用 file 字段指定的录音或外部 TTS 结果（推荐正式旁白用真人或高质量 TTS）。
- --style clean：干净旁白；speaker：模拟"外放的录音/课堂讲话"（带通 + 轻饱和 + 短房间混响），适合作为场景里的环境声。
日志：./log/add_voice.log"""
import argparse, logging, subprocess, tempfile
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve
from timeline import Timeline

Path('log').mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.FileHandler('log/add_voice.log'), logging.StreamHandler()])
log = logging.getLogger()
ap = argparse.ArgumentParser(); ap.add_argument('page'); ap.add_argument('music'); ap.add_argument('out')
ap.add_argument('--tts', default='say', choices=['say', 'files']); ap.add_argument('--voice', default='Daniel')
ap.add_argument('--style', default='clean', choices=['clean', 'speaker']); ap.add_argument('--gain', type=float, default=-6.0)
ap.add_argument('--duck', type=float, default=-6.0); ap.add_argument('--lead', type=float, default=0.1, help='比字幕提前多少秒开口')
A = ap.parse_args()
TL = Timeline(A.page)
if not TL.voice: raise SystemExit('时间轴里没有 voice 台词')
sr, music = wavfile.read(A.music)
m = music.astype(np.float64) / 32768.0
if m.ndim == 1: m = np.stack([m, m], 1)
N = len(m); t = np.arange(N) / sr; db = lambda x: 10 ** (x / 20)

def load(path):
    with tempfile.TemporaryDirectory() as d:
        w = Path(d) / 'a.wav'; subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-ac', '1', '-ar', str(sr), str(w)], check=True)
        _, x = wavfile.read(w)
    x = x.astype(np.float64) / 32768.0; nz = np.flatnonzero(np.abs(x) > 0.01)
    return x[nz[0]:nz[-1] + 1] if len(nz) else x

def say(text):
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / 'a.aiff'; subprocess.run(['say', '-v', A.voice, '-o', str(aiff), text], check=True)
        return load(aiff)

def fit(x, dur):
    L = len(x) / sr
    if L <= dur: return x, 1.0
    k = min(L / dur, 1.25)
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / 'i.wav', Path(d) / 'o.wav'; wavfile.write(a, sr, (x * 32767).astype(np.int16))
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(a), '-filter:a', f'atempo={k:.3f}', str(b)], check=True)
        _, y = wavfile.read(b)
    return y.astype(np.float64) / 32768.0, k

voice, env = np.zeros(N), np.zeros(N)
for v in TL.voice:
    x = load(v['file']) if A.tts == 'files' else say(v['text'])
    x, k = fit(x, v['t1'] - v['t0'] + A.lead)
    i = max(0, int((v['t0'] - A.lead) * sr)); voice[i:i + len(x)] += x[:N - i]
    env[i:i + len(x)] = 1
    if len(x) / sr > v['t1'] - v['t0'] + A.lead + 0.05: log.warning('台词超出窗口：%s', v['text'])
    log.info('%.2f–%.2fs  tempo x%.2f  %.2fs  %s', v['t0'], v['t1'], k, len(x) / sr, v['text'])
if A.style == 'speaker':
    voice = sosfilt(butter(2, [180, 5200], btype='band', fs=sr, output='sos'), voice); voice = np.tanh(voice * 1.6) / 1.6
    rng = np.random.default_rng(7); it = np.arange(int(sr * 0.45)) / sr; ir = rng.standard_normal(len(it)) * np.exp(-it / 0.09); ir[0] = 6
    voice = fftconvolve(voice, ir)[:N]
else:
    voice = sosfilt(butter(2, 90, btype='high', fs=sr, output='sos'), voice)
voice /= np.abs(voice).max() + 1e-9
k = int(0.3 * sr); env = np.convolve(env, np.ones(k) / k, 'same')            # 0.3s 平滑起落，避免压限"喘气"
peak = np.abs(m).max()
out = m * (1 - (1 - db(A.duck)) * env)[:, None] + (voice * db(A.gain) * peak)[:, None]
out *= min(1, 0.98 / np.abs(out).max())
wavfile.write(A.out, sr, (out * 32767).astype(np.int16))
log.info('%s + %d 句台词 → %s  style=%s gain=%+.0fdB duck=%+.0fdB', A.music, len(TL.voice), A.out, A.style, A.gain, A.duck)
