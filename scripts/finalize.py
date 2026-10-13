"""成片收尾工具（依赖 ffmpeg、Pillow）。日志：./log/finalize.log
  mux    <silent.mp4> <music.wav> <out.mp4> [--lufs -16] [--no-norm]   响度归一（loudnorm）后与画面合成，画面不重编码
  web    <in.mp4> <out.mp4> [--vbr 500k] [--abr 96k] [--height 1080]    两遍编码压体积 + faststart，放网页用
  poster <in.mp4> <秒> <out.jpg> [--width 1280]                           取封面帧
  sheet  <stills目录 | video.mp4> <out.jpg> [--every 2] [--cols 4]       拼关键帧总览图（每格标时间），审片用
  loud   <file>                                                          测整体响度（LUFS）与峰值
"""
import argparse, json, logging, re, subprocess, sys, tempfile
from pathlib import Path

Path('log').mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                    handlers=[logging.FileHandler('log/finalize.log'), logging.StreamHandler()])
log = logging.getLogger()
run = lambda *a: subprocess.run(['ffmpeg', '-y', '-v', 'error', *a], check=True)

def loudness(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(path), '-af', 'loudnorm=print_format=json', '-f', 'null', '-'], capture_output=True, text=True)
    return json.loads(re.findall(r'\{[^{}]+\}', r.stderr)[-1])

def mux(a):
    af = [] if a.no_norm else ['-af', f'loudnorm=I={a.lufs}:TP=-1.5:LRA=11', '-ar', '48000']
    run('-i', a.video, '-i', a.music, *af, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', a.out)
    log.info('mux %s + %s → %s  响度 %s LUFS', a.video, a.music, a.out, loudness(a.out)['input_i'])

def web(a):
    with tempfile.TemporaryDirectory() as d:
        common = ['-i', a.inp, '-vf', f'scale=-2:{a.height}', '-c:v', 'libx264', '-preset', 'slow', '-b:v', a.vbr, '-passlogfile', f'{d}/p']
        run(*common, '-pass', '1', '-an', '-f', 'mp4', '/dev/null')
        run(*common, '-pass', '2', '-c:a', 'aac', '-b:a', a.abr, '-movflags', '+faststart', a.out)
    log.info('web %s → %s  %.2f MB', a.inp, a.out, Path(a.out).stat().st_size / 1e6)

def poster(a):
    run('-ss', str(a.t), '-i', a.inp, '-frames:v', '1', '-vf', f'scale={a.width}:-2', '-q:v', '3', a.out)
    log.info('poster t=%s → %s', a.t, a.out)

def sheet(a):
    from PIL import Image, ImageDraw, ImageFont
    src = Path(a.src)
    with tempfile.TemporaryDirectory() as d:
        if src.is_dir(): frames = sorted(src.glob('*.jpg')) + sorted(src.glob('*.png'))
        else:
            # 用 select 取 0、every、2·every… 秒的帧（fps 滤镜会取区间中点，标注的时间就对不上了）
            run('-i', str(src), '-vf', f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{a.every}-0.001)'", '-fps_mode', 'vfr', f'{d}/f%04d.jpg')
            frames = sorted(Path(d).glob('*.jpg'))
        labels = [f.stem.lstrip('t').lstrip('0') or '0' for f in frames] if src.is_dir() else [f'{i * a.every:g}' for i in range(len(frames))]
        tw = 480; ims = [Image.open(f).convert('RGB') for f in frames]
        th = round(tw * ims[0].height / ims[0].width); rows = -(-len(ims) // a.cols)
        canvas = Image.new('RGB', (a.cols * tw + (a.cols + 1) * 8, rows * (th + 8) + 8), '#222')
        try: font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 22)
        except OSError: font = ImageFont.load_default()
        for i, (im, lb) in enumerate(zip(ims, labels)):
            x, y = 8 + (i % a.cols) * (tw + 8), 8 + (i // a.cols) * (th + 8)
            canvas.paste(im.resize((tw, th)), (x, y))
            dr = ImageDraw.Draw(canvas); dr.rectangle([x, y, x + 74, y + 30], fill='#000'); dr.text((x + 6, y + 3), f'{float(lb):.1f}s', fill='#fff', font=font)
        canvas.save(a.out, quality=88)
    log.info('sheet %d 格 → %s', len(ims), a.out)

def loud(a):
    r = loudness(a.file); log.info('%s  整体 %s LUFS  峰值 %s dBTP  LRA %s', a.file, r['input_i'], r['input_tp'], r['input_lra'])

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = p.add_subparsers(dest='cmd', required=True)
s = sp.add_parser('mux'); s.add_argument('video'); s.add_argument('music'); s.add_argument('out'); s.add_argument('--lufs', default='-16'); s.add_argument('--no-norm', action='store_true')
s = sp.add_parser('web'); s.add_argument('inp'); s.add_argument('out'); s.add_argument('--vbr', default='500k'); s.add_argument('--abr', default='96k'); s.add_argument('--height', default='1080')
s = sp.add_parser('poster'); s.add_argument('inp'); s.add_argument('t', type=float); s.add_argument('out'); s.add_argument('--width', default='1280')
s = sp.add_parser('sheet'); s.add_argument('src'); s.add_argument('out'); s.add_argument('--every', type=float, default=2); s.add_argument('--cols', type=int, default=4)
s = sp.add_parser('loud'); s.add_argument('file')
a = p.parse_args(); log.info('finalize %s', ' '.join(sys.argv[1:]))
globals()[a.cmd](a)
