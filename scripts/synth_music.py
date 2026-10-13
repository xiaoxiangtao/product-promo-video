"""按页面时间轴合成配乐 + 画面同步音效（纯 numpy/scipy 加性合成，不依赖音源和曲库）。
用法：python synth_music.py <promo.html> <out.wav> [--seed 7] [--no-sfx | --sfx-only] [--stems]
- 小节网格、场景 energy、和弦、音效点全部读页面里的 #timeline，改分镜后重跑即可，不用手工对时间。
- 编曲原则（来自多轮试听反馈）：
  1. 铺底和弦全程不断，任何 100ms 都不静音（段落之间的空洞会让人觉得"不连贯"）；
  2. 和弦按全局小节号循环，场景切换不重置（插入段落时循环被打断听起来很突兀）；
  3. 一个固定的 2 小节动机贯穿全曲，只靠 energy 加减配器，不换旋律（换旋律 = "像乱弹"）；
  4. 场景交界用一记三音上行"扫弦"做记号，不用大的冲击音效；
  5. 结尾只留一条线：扫弦 → 主和弦长音淡出，不堆多余音符。
日志：./log/synth_music.log"""
import argparse, logging
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve
from timeline import Timeline

Path('log').mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.FileHandler('log/synth_music.log'), logging.StreamHandler()])
log = logging.getLogger()
ap = argparse.ArgumentParser(); ap.add_argument('page'); ap.add_argument('out'); ap.add_argument('--seed', type=int, default=7)
ap.add_argument('--no-sfx', action='store_true'); ap.add_argument('--sfx-only', action='store_true', help='只出音效层（配合现成授权音乐）'); ap.add_argument('--stems', action='store_true', help='另存各声部 wav 便于调平衡')
A = ap.parse_args()
TL = Timeline(A.page)
SR = 48000; BEAT, BAR, STEP = TL.beat, TL.bar, TL.beat / 4
N = int(SR * (TL.duration + 2.5)); rng = np.random.default_rng(A.seed)
BUS = {k: np.zeros((N, 2)) for k in ('pad', 'keys', 'bass', 'drum', 'sfx')}
GAIN = {'pad': 0.20, 'keys': 0.42, 'bass': 0.36, 'drum': 0.42, 'sfx': 0.50}
hz = lambda m: 440 * 2 ** ((m - 69) / 12)
tt = lambda d: np.arange(int(SR * d)) / SR
bp = lambda x, lo, hi: sosfilt(butter(2, [lo, hi], btype='band', fs=SR, output='sos'), x)
lp = lambda x, fc: sosfilt(butter(2, fc, fs=SR, output='sos'), x)
hp = lambda x, fc: sosfilt(butter(2, fc, btype='high', fs=SR, output='sos'), x)

def add(bus, t0, sig, pan=0.0, gain=1.0):
    i = int(t0 * SR)
    if i >= N or i + len(sig) <= 0: return
    sig = sig[:N - i]
    BUS[bus][i:i + len(sig), 0] += sig * gain * np.sqrt(0.5 * (1 - pan))
    BUS[bus][i:i + len(sig), 1] += sig * gain * np.sqrt(0.5 * (1 + pan))

# ---------- 音色 ----------
def marimba(m, v=1.0):
    t = tt(0.9); f = hz(m)
    s = np.sin(2*np.pi*f*t)*np.exp(-t*7) + 0.35*np.sin(2*np.pi*3.93*f*t)*np.exp(-t*22) + 0.08*np.sin(2*np.pi*9.2*f*t)*np.exp(-t*45)
    return s * np.minimum(1, t / 0.002) * v
def kalimba(m, v=1.0):
    t = tt(1.6); f = hz(m)
    s = np.sin(2*np.pi*f*t)*np.exp(-t*3) + 0.3*np.sin(2*np.pi*5.4*f*t)*np.exp(-t*14) + 0.1*np.sin(2*np.pi*2*f*t)*np.exp(-t*5)
    return s * np.minimum(1, t / 0.003) * v
def epiano(m, dur, v=1.0):
    t = tt(dur + 0.6); f = hz(m)
    s = (np.sin(2*np.pi*f*t + 0.8*np.sin(2*np.pi*f*t)*np.exp(-t*4))) * np.exp(-t*1.6)
    return s * np.minimum(1, t / 0.005) * np.clip((dur + 0.6 - t) / 0.3, 0, 1) * v
def pad(notes, dur):
    t = tt(dur + 0.4); s = np.zeros_like(t)
    for m in notes:
        for d in (-0.08, 0.08): s += np.sin(2*np.pi*hz(m)*(1 + d/100)*t) + 0.3*np.sin(2*np.pi*2*hz(m)*t)
    env = np.minimum(1, t / 0.35) * np.clip((dur + 0.4 - t) / 0.4, 0, 1)
    return lp(s, 1800) * env / len(notes)
def pbass(m, dur):
    t = tt(dur); f = hz(m) * (1 + 0.04*np.exp(-t*40)); ph = 2*np.pi*np.cumsum(f)/SR
    s = np.sin(ph) + 0.25*np.sin(2*ph) + 0.1*np.sin(3*ph)
    return s * np.minimum(1, t / 0.004) * np.exp(-t*2.2) * np.clip((dur - t) / 0.02, 0, 1)
def noise(d, lo, hi, dec): t = tt(d); return bp(rng.standard_normal(len(t)), lo, hi) * np.exp(-t*dec)
def kick(): t = tt(0.3); return np.tanh(2*np.sin(2*np.pi*(50*t + 110/32*(1 - np.exp(-32*t))))*np.exp(-t*10))
def snap(): t = tt(0.12); return noise(0.12, 1800, 5200, 45)*1.4 + np.sin(2*np.pi*2100*t)*np.exp(-t*90)*0.4
def shaker(v): t = tt(0.07); return hp(rng.standard_normal(len(t)), 6000) * np.minimum(1, t/0.012) * np.exp(-t*60) * v

# ---------- 画面同步音效（events.type） ----------
def sfx_click(t0, e): t = tt(0.05); add('sfx', t0, np.sin(2*np.pi*1300*t)*np.exp(-t*120) + 0.3*noise(0.05, 3000, 9000, 150), gain=0.9)
def sfx_tick(t0): add('sfx', t0, noise(0.03, 2500, 8000, 160), pan=rng.uniform(-.3, .3), gain=0.7)
def sfx_typing(t0, e):
    n, dur = e.get('n', 10), e.get('dur', 1.0)
    for k in range(n): sfx_tick(t0 + dur * k / max(1, n - 1) + rng.uniform(-0.02, 0.02))
def sfx_ding(t0, e):
    for j, m in enumerate((88, 95)): add('sfx', t0 + j*0.08, kalimba(m, 0.6), pan=0.2*(-1)**j, gain=0.8)
def sfx_pop(t0, e):
    t = tt(0.12); f = 900*np.exp(-t*30) + 250; ph = 2*np.pi*np.cumsum(f)/SR
    add('sfx', t0, np.sin(ph)*np.exp(-t*35) + 0.25*noise(0.12, 1500, 6000, 60), pan=rng.uniform(-.3, .3), gain=0.7)
def sfx_whoosh(t0, e, L=0.45):
    t = tt(L); x = rng.standard_normal(len(t)); out = np.zeros_like(x); seg = int(SR*0.02)
    for i in range(0, len(x), seg):
        fc = 500 * 14 ** (i / len(x)); out[i:i+seg] = bp(x[max(0, i-800):i+seg], fc*0.7, min(fc*1.4, 20000))[-len(x[i:i+seg]):]
    add('sfx', t0 - L*0.8, out*np.sin(np.pi*t/L), gain=0.6)   # 上扬在动作点前抵达
def strum(t0, chord, gain=0.9):
    for j, m in enumerate(chord[:3]): add('keys', t0 + j*0.045, kalimba(m + 12, 0.7), pan=-0.3 + 0.3*j, gain=gain)
SFX = {'click': sfx_click, 'typing': sfx_typing, 'ding': sfx_ding, 'pop': sfx_pop, 'whoosh': sfx_whoosh}

# ---------- 编曲 ----------
CH = TL.music.get('chords', [[62, 66, 69, 73], [59, 62, 66, 69], [55, 59, 62, 66], [57, 61, 64, 69]])   # 默认 Dmaj7 Bm7 Gmaj7 A
BS = TL.music.get('bass', [38, 35, 43, 45])
MOTIF = [[(0, 0), (3, 2), (6, 1), (8, 3), (10, 2), (11, 1), (14, 3)],          # (16 分位置, 和弦内音序号)，两小节一循环
         [(0, 1), (3, 3), (6, 2), (10, 0), (12, 1), (14, 2)]]
starts, last = set(TL.scene_starts()), TL.bars - 1
for b in range(0 if A.sfx_only else TL.bars):
    t0, ch, bs, en = b * BAR, CH[b % len(CH)], BS[b % len(BS)], TL.energy(b)
    if b == last:                                             # 结尾：一记扫弦 + 主和弦长音淡出
        strum(t0, CH[0]); add('pad', t0, pad(CH[0], BAR * 1.6), gain=1.2)
        for m in CH[0]: add('keys', t0 + 0.2, epiano(m, BAR * 1.2, 0.35))
        add('bass', t0, pbass(BS[0], BAR * 1.5)); continue
    add('pad', t0, pad(ch, BAR), gain=0.7 + 0.15 * en)
    if b in starts and b > 0: strum(t0, ch)
    up = 12 if en >= 3 else 0
    for s, k in MOTIF[b % 2]:
        if en <= 1 and s not in (0, 6, 10): continue           # 低能量：只留骨架音，用拇指琴
        voice = kalimba if en <= 1 else marimba
        add('keys', t0 + s * STEP, voice(ch[k] + up, 0.55 + 0.1 * en), pan=0.25 * np.sin(s))
    if en >= 2:
        for s, off, d in [(0, 0, 0.5), (6, 7, 0.25), (10, 12, 0.3), (14, 0, 0.12)]: add('bass', t0 + s * STEP, pbass(bs + off, d * BAR))
        for s in range(0, 16, 2): add('drum', t0 + s * STEP, shaker(0.5 if s % 4 else 0.3), pan=0.3)
    if en >= 3:
        for s in (0, 8): add('drum', t0 + s * STEP, kick(), gain=0.9)
        for s in (4, 12): add('drum', t0 + s * STEP, snap(), gain=0.5, pan=-0.1)
if not A.no_sfx:
    for e in TL.events:
        fn = SFX.get(e['type'])
        fn(e['t'], e) if fn else log.warning('未知音效类型 %s（跳过）', e['type'])

# ---------- 混音 ----------
ir_t = tt(1.2); ir = rng.standard_normal((len(ir_t), 2)) * np.exp(-ir_t / 0.35)[:, None]; ir[0] = 1
for k in ('pad', 'keys'):                                      # 短混响让合成音色不那么干
    wet = np.stack([fftconvolve(BUS[k][:, c], ir[:, c])[:N] for c in range(2)], 1)
    BUS[k] = BUS[k] + 0.12 * wet / (np.abs(wet).max() + 1e-9) * np.abs(BUS[k]).max()
mix = sum(BUS[k] * GAIN[k] for k in BUS)
mix = mix[:int(SR * (TL.duration + 0.5))]
fade = int(SR * 0.5); mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
mix *= 10 ** (-1 / 20) / np.abs(mix).max()                     # 峰值 -1 dBFS；最终响度交给 finalize.py mux 的 loudnorm
wavfile.write(A.out, SR, (mix * 32767).astype(np.int16))
w = int(SR * 0.1); rms = np.sqrt((mix[:len(mix) // w * w, 0].reshape(-1, w) ** 2).mean(1)); quiet = int((20 * np.log10(rms[:-6] + 1e-9) < -40).sum())
log.info('%s → %s  %.2fs  %d 小节 @%g BPM  音效 %d 个  <-40dB 的 100ms 窗：%d（纯配乐时应为 0）', A.page, A.out, TL.duration, TL.bars, TL.bpm, len(TL.events), quiet)
if A.stems:
    for k in BUS: wavfile.write(Path(A.out).with_suffix(f'.{k}.wav'), SR, (BUS[k] / (np.abs(BUS[k]).max() + 1e-9) * 0.9 * 32767).astype(np.int16))
