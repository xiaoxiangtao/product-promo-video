"""从页面里读出唯一的时间轴（<script id="timeline" type="application/json">），供配乐 / 人声脚本使用。
at 可以是秒，也可以是 [小节, 拍]；返回的对象把所有时间都换算成秒。"""
import json, re
from pathlib import Path

class Timeline:
    def __init__(self, page):
        html = Path(page).read_text(encoding='utf-8')
        m = re.search(r'<script id="timeline" type="application/json">(.*?)</script>', html, re.S)
        if not m: raise SystemExit(f'{page} 里找不到 <script id="timeline" type="application/json">')
        self.raw = d = json.loads(m.group(1))
        self.bpm, self.bars = d['bpm'], d['bars']
        self.beat = 60 / self.bpm; self.bar = 4 * self.beat; self.duration = self.bars * self.bar
        self.scenes = [{**s, 't0': s['bar'] * self.bar, 't1': (s['bar'] + s['bars']) * self.bar} for s in d['scenes']]
        self.events = [{**e, 't': self.at(e['at'])} for e in d.get('events', [])]
        self.voice = [{**v, 't0': self.at(v['at']), 't1': self.at(v['to'])} for v in d.get('voice', [])]
        self.music = d.get('music', {})

    def at(self, v):
        return v[0] * self.bar + (v[1] if len(v) > 1 else 0) * self.beat if isinstance(v, list) else float(v)

    def energy(self, bar):
        """第 bar 小节所在场景的配器密度 0–3。"""
        for s in self.scenes:
            if s['bar'] <= bar < s['bar'] + s['bars']: return s.get('energy', 2)
        return 1

    def scene_starts(self):
        return [s['bar'] for s in self.scenes]
