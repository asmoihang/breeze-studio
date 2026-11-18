"""Local-only Breeze Studio service. Standard library; no changes to the TTS env."""
from __future__ import annotations
import argparse
import array
import base64
import copy
import hashlib
import io
import json
import math
import mimetypes
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
VERSION = (ROOT / 'VERSION').read_text('utf-8').strip() if (ROOT / 'VERSION').exists() else '0.1.0'
ACTIVE = {'queued', 'loading', 'running'}
TERMINAL = {'completed', 'failed', 'cancelled'}


def uid(): return uuid.uuid4().hex
def now(): return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def clone(value): return copy.deepcopy(value)
def text(value, maximum=10000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'文字格式错误或超过 {maximum} 字。')
    return value


def settings(value):
    v = value or {}
    cfg = float(v.get('cfg', 4))
    raw_seed = float(v.get('seed', 42))
    if not math.isfinite(raw_seed) or not raw_seed.is_integer():
        raise ValueError('随机种子必须是整数。')
    seed = int(raw_seed)
    if not math.isfinite(cfg) or not 0 < cfg <= 20 or not 0 <= seed <= 4294967295:
        raise ValueError('CFG 必须在 0～20 之间，种子须为 0～4294967295 的整数。')
    return {'voice_id': text(v.get('voice_id', ''), 80),
            'instruction': text(v.get('instruction', ''), 2000).strip(), 'cfg': int(cfg) if cfg.is_integer() else cfg, 'seed': seed}


def signature(segment, global_settings):
    s = settings(segment.get('settings') or global_settings)
    return json.dumps([segment['text'].strip(), s['voice_id'], s['instruction'], s['cfg'], s['seed']],
                      ensure_ascii=False, separators=(',', ':'))


def split_text(value, limit=180):
    value = text(value, 100000).strip()
    limit = max(40, min(int(limit), 500))
    result = []
    for paragraph in re.split(r'\n\s*\n', value):
        sentences = re.findall(r'.+?(?:[。！？!?；;]\s*|$)', paragraph.replace('\n', ' '))
        current = ''
        for sentence in sentences:
            while len(sentence) > limit:
                if current.strip(): result.append(current.strip()); current = ''
                pos = max(sentence.rfind('，', 0, limit), sentence.rfind(',', 0, limit), sentence.rfind(' ', 0, limit))
                cut = pos + 1 if pos >= limit // 2 else limit
                result.append(sentence[:cut].strip()); sentence = sentence[cut:]
            if current and len(current) + len(sentence) > limit:
                result.append(current.strip()); current = ''
            current += sentence
        if current.strip(): result.append(current.strip())
    return result


def audio_info(path):
    with wave.open(str(path), 'rb') as f:
        if f.getsampwidth() != 2 or f.getnchannels() != 1:
            raise ValueError('输出必须是官方 PCM16 单声道 WAV。')
        count, rate = f.getnframes(), f.getframerate()
        data = array.array('h', f.readframes(count))
        if sys.byteorder != 'little': data.byteswap()
    step = max(1, len(data) // 100)
    peaks = [round(max((abs(x) for x in data[i:i + step]), default=0) / 32768, 4)
             for i in range(0, len(data), step)][:100]
    return {'duration': count / rate, 'sample_rate': rate, 'peaks': peaks}


def merge_wavs(paths, pause_ms):
    if not paths: raise ValueError('没有可合并的音频。')
    pause_ms = int(pause_ms)
    if not 0 <= pause_ms <= 10000: raise ValueError('段间停顿范围为 0～10000 ms。')
    target = io.BytesIO()
    with wave.open(target, 'wb') as out:
        params = None
        for i, path in enumerate(paths):
            with wave.open(str(path), 'rb') as source:
                actual = (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
                if params is None:
                    params = actual
                    out.setnchannels(actual[0]); out.setsampwidth(actual[1]); out.setframerate(actual[2])
                elif actual != params:
                    raise ValueError('音频格式不一致，已停止合并，避免重采样改变输出。')
                if i: out.writeframesraw(b'\0' * (round(params[2] * pause_ms / 1000) * params[0] * params[1]))
                out.writeframesraw(source.readframes(source.getnframes()))
    return target.getvalue()


class Engine:
    def __init__(self, app):
        self.app = app; self.proc = None; self.state = 'unloaded'; self.error = ''; self.log = None
        self.guard = threading.Lock(); self.events = queue.Queue()

    def start(self):
        with self.guard:
            if self.proc and self.proc.poll() is None: return
            c = self.app.config
            for field, required in [('repo', 'infer.py'), ('model', 'audio_tokenizer')]:
                if not c.get(field) or not (Path(c[field]) / required).exists():
                    raise ValueError('请先在设置中填写正确的官方项目和模型路径。')
            if not c.get('python') or not Path(c['python']).is_file():
                raise ValueError('找不到官方虚拟环境的 Python。')
            self.state = 'loading'; self.error = ''; self.events = queue.Queue()
            self.log = open(self.app.data / 'worker.log', 'a', encoding='utf-8')
            env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
            self.proc = subprocess.Popen([c['python'], '-u', str(ROOT / 'backend/worker.py'),
                                          '--repo', c['repo'], '--model', c['model']],
                                         cwd=c['repo'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=self.log, text=True, encoding='utf-8', env=env)
            proc, events = self.proc, self.events
            def reader():
                try:
                    for line in proc.stdout:
                        try: events.put(json.loads(line))
                        except json.JSONDecodeError: pass
                finally: events.put({'type': 'exit'})
            threading.Thread(target=reader, daemon=True).start()
        while True:
            event = self.next_event(900)
            if event['type'] == 'ready':
                self.state = 'ready'; return
            if event['type'] in ('error', 'exit'):
                self.error = event.get('error', '模型进程退出，请检查 worker.log。')
                self.stop(); self.state = 'error'; raise RuntimeError(self.error)

    def next_event(self, timeout=300):
        try: return self.events.get(timeout=timeout)
        except queue.Empty:
            self.stop(); self.state = 'error'
            raise RuntimeError('推理进程长时间没有响应，请检查日志后重试。')

    def generate(self, task, callback):
        self.start()
        self.proc.stdin.write(json.dumps(task, ensure_ascii=False) + '\n'); self.proc.stdin.flush()
        self.state = 'running'
        while True:
            event = self.next_event()
            if event['type'] == 'done': self.state = 'ready'; return
            if event['type'] in ('error', 'exit'):
                self.error = event.get('error', '推理已停止。')
                self.stop(); self.state = 'error'; raise RuntimeError(self.error)
            callback(event)

    def stop(self):
        with self.guard:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try: self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(timeout=10)
            self.proc = None
            if self.log: self.log.close(); self.log = None
            self.state = 'unloaded'


class Studio:
    def __init__(self, data, engine_factory=Engine):
        self.data = Path(data); self.data.mkdir(parents=True, exist_ok=True)
        for name in ('voices', 'outputs'): (self.data / name).mkdir(exist_ok=True)
        self.lock = threading.RLock(); self.events = {}; self.current = None; self.pending = queue.Queue()
        self.model_lock = threading.Lock(); self.closed = False
        self.config = {'repo': '', 'model': '', 'python': '', 'stt_url': '', 'stt_model': 'whisper-1'}
        if (self.data / 'config.json').exists(): self.config.update(json.loads((self.data / 'config.json').read_text('utf-8')))
        candidate = Path.home() / 'breeze-work/breeze-tts'
        if not self.config['repo'] and (candidate / 'infer.py').exists():
            self.config.update(repo=str(candidate), model=str(candidate.parent / 'models/Breeze-TTS-2'),
                               python=str(candidate / '.venv/bin/python'))
        self.state = {'projects': [], 'voices': [], 'jobs': [], 'designs': []}
        if (self.data / 'state.json').exists(): self.state.update(json.loads((self.data / 'state.json').read_text('utf-8')))
        for job in self.state['jobs']:
            if job['status'] in ACTIVE: job.update(status='failed', error='服务重启中断了任务，可重新生成。')
        self.engine = engine_factory(self)
        threading.Thread(target=self.run_queue, daemon=True).start()

    def write_json(self, name, value):
        dest = self.data / name; temp = dest.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8'); os.replace(temp, dest)

    def save(self): self.write_json('state.json', self.state)

    def snapshot(self):
        with self.lock:
            return {**clone(self.state), 'version': VERSION, 'config': clone(self.config), 'engine': self.engine.state,
                    'engine_error': self.engine.error}

    def project(self, pid):
        return next((x for x in self.state['projects'] if x['id'] == pid), None)

    def save_project(self, body):
        pid = text(body.get('id') or uid(), 80)
        global_settings = settings(body.get('settings'))
        rows = body.get('segments', [])
        if not isinstance(rows, list) or not 1 <= len(rows) <= 200: raise ValueError('一个项目需要 1～200 个段落。')
        segments = []
        for row in rows:
            segments.append({'id': text(row.get('id') or uid(), 80), 'title': text(row.get('title', '未命名'), 100),
                             'text': text(row.get('text', ''), 10000),
                             'settings': settings(row['settings']) if row.get('settings') else None})
        if len(set(s['id'] for s in segments)) != len(segments): raise ValueError('段落 ID 重复。')
        if sum(len(s['text']) for s in segments) > 100000: raise ValueError('项目文案过长。')
        result = {'id': pid, 'name': text(body.get('name', '未命名项目'), 100),
                  'mode': 'segments' if body.get('mode') == 'segments' else 'single',
                  'settings': global_settings, 'segments': segments,
                  'pause_ms': max(0, min(10000, int(body.get('pause_ms', 300)))), 'updated': now()}
        result['single'] = {'id': 'single-' + pid, 'title': '自由配音',
                            'text': text(body.get('single', {}).get('text', ''), 10000), 'settings': None}
        with self.lock:
            previous = self.project(pid)
            if previous: self.state['projects'][self.state['projects'].index(previous)] = result
            else: self.state['projects'].append(result)
            self.save()
        return result

    def submit(self, body):
        with self.lock:
            p = self.project(body.get('project_id'))
            if not p: raise ValueError('项目不存在。')
            source = [p['single']] if p['mode'] == 'single' else p['segments']
            selected = body.get('segment_ids') or [s['id'] for s in source]
            if not isinstance(selected, list): raise ValueError('段落列表格式错误。')
            if not set(selected) <= {s['id'] for s in source}: raise ValueError('找不到选中的段落。')
            tasks = []
            for segment in source:
                if segment['id'] not in selected: continue
                if not segment['text'].strip(): raise ValueError(f'「{segment["title"]}」的文案为空。')
                if len(segment['text']) > 800: raise ValueError('单段超过 800 字，请先自动分段。')
                effective = settings(segment.get('settings') or p['settings'])
                voice = next((v for v in self.state['voices'] if v['id'] == effective['voice_id']), None)
                if effective['voice_id'] and not voice: raise ValueError('所选音色不存在，请重新选择。')
                if not voice and not effective['instruction']: raise ValueError('声音设计需要填写声音描述。')
                sig = signature(segment, p['settings'])
                if any(j['project_id'] == p['id'] and j['segment_id'] == segment['id'] and j['signature'] == sig
                       and j['status'] in ACTIVE for j in self.state['jobs']): continue
                task = {'id': uid(), 'project_id': p['id'], 'project_name': p['name'], 'segment_id': segment['id'],
                        'title': segment['title'], 'text': segment['text'].strip(), 'settings': effective,
                        'signature': sig, 'voice_name': voice['name'] if voice else '声音设计',
                        'ref_audio': voice['file'] if voice else '', 'ref_text': voice['transcript'] if voice else '',
                        'created': now(), 'status': 'queued', 'error': '', 'seconds': 0, 'live': bool(body.get('live'))}
                tasks.append(task)
            if len([j for j in self.state['jobs'] if j['status'] in ACTIVE]) + len(tasks) > 200:
                raise ValueError('队列最多容纳 200 个任务。')
            self.state['jobs'].extend(tasks); self.save()
            for task in tasks: self.events[task['id']] = []; self.pending.put(task['id'])
            return clone(tasks)

    def job(self, jid): return next((j for j in self.state['jobs'] if j['id'] == jid), None)

    def design(self, body):
        name = text(body.get('name', '自定义音色'), 100).strip()
        script = text(body.get('text', ''), 800).strip()
        params = settings({'instruction': body.get('instruction', ''), 'cfg': body.get('cfg', 4),
                           'seed': body.get('seed', 42), 'voice_id': ''})
        count = body.get('count', 3)
        if type(count) is not int or not 1 <= count <= 6:
            raise ValueError('每批请选择 1～6 个候选。')
        if not name or not script or not params['instruction']:
            raise ValueError('请填写音色名称、声音描述和试听文案。')
        if params['seed'] + count - 1 > 4294967295:
            raise ValueError('候选种子超出范围，请减小起始种子。')
        did = uid()
        batch = {'id': did, 'name': name, 'text': script, 'settings': params, 'count': count,
                 'created': now(), 'job_ids': []}
        jobs = []
        for i in range(count):
            jid = uid(); effective = {**params, 'seed': params['seed'] + i}
            job = {'id': jid, 'kind': 'voice-design', 'design_id': did,
                   'project_id': 'design-' + did, 'project_name': '音色设计 · ' + name,
                   'segment_id': jid, 'title': f'{name} · 候选 {i+1}', 'text': script,
                   'settings': effective, 'signature': signature({'text': script}, effective),
                   'voice_name': '声音设计', 'ref_audio': '', 'ref_text': '', 'created': now(),
                   'status': 'queued', 'error': '', 'seconds': 0, 'live': False}
            batch['job_ids'].append(jid); jobs.append(job)
        with self.lock:
            if sum(j['status'] in ACTIVE for j in self.state['jobs']) + count > 200:
                raise ValueError('队列最多容纳 200 个任务。')
            self.state['designs'].append(batch); self.state['jobs'].extend(jobs); self.save()
            for job in jobs: self.events[job['id']] = []; self.pending.put(job['id'])
        return clone(batch)

    def retry_design(self, body):
        with self.lock:
            batch = next((d for d in self.state['designs'] if d['id'] == body.get('id')), None)
            if not batch or body.get('job_id') not in batch['job_ids']:
                raise ValueError('找不到这个候选。')
            previous = self.job(body['job_id'])
            if previous['status'] not in ('failed', 'cancelled'):
                raise ValueError('仅可重试失败或已取消的候选。')
            if sum(j['status'] in ACTIVE for j in self.state['jobs']) >= 200:
                raise ValueError('队列已满。')
            job = {k: clone(v) for k, v in previous.items()
                   if k not in ('finished', 'file', 'duration', 'sample_rate', 'peaks')}
            job.update(id=uid(), status='queued', error='', seconds=0, created=now())
            batch['job_ids'][batch['job_ids'].index(previous['id'])] = job['id']
            self.state['jobs'].append(job); self.save()
            self.events[job['id']] = []; self.pending.put(job['id'])
            return clone(job)

    def run_queue(self):
        while not self.closed:
            jid = self.pending.get()
            if jid is None: return
            with self.model_lock:
                with self.lock:
                    job = self.job(jid)
                    if not job or job['status'] != 'queued': continue
                    self.current = jid; job['status'] = 'loading'; self.save()
                try:
                    self.engine.start()
                    with self.lock:
                        if job['status'] == 'cancelled': continue
                        job['status'] = 'running'
                    output = self.data / 'outputs' / (jid + '.wav')
                    task = {**job['settings'], 'text': job['text'], 'output': str(output), 'live': job['live'],
                            'ref_audio': str(self.data / job['ref_audio']) if job['ref_audio'] else '', 'ref_text': job['ref_text']}
                    def progress(event):
                        with self.lock:
                            job['seconds'] = event.get('seconds', 0)
                            if 'pcm' in event:
                                events = self.events.setdefault(jid, [])
                                if len(events) < 3000: events.append(event)
                    self.engine.generate(task, progress)
                    info = audio_info(output)
                    with self.lock:
                        if job['status'] != 'cancelled':
                            job.update(status='completed', finished=now(), file='outputs/' + jid + '.wav', **info)
                except Exception as exc:
                    with self.lock:
                        if job['status'] != 'cancelled': job.update(status='failed', error=str(exc)[-6000:], finished=now())
                finally:
                    with self.lock:
                        self.current = None; self.save()
                        # Audio events are ephemeral; keep only recent live jobs.
                        for old in list(self.events)[:-5]: self.events.pop(old, None)

    def cancel(self, ids):
        with self.lock:
            kill = False
            for jid in ids:
                job = self.job(jid)
                if job and job['status'] in ACTIVE:
                    job.update(status='cancelled', finished=now())
                    kill |= self.current == jid
            self.save()
            if kill: self.engine.stop()

    def lifecycle(self, action):
        if action not in ('load', 'unload'): raise ValueError('未知模型操作。')
        if action == 'unload' and self.engine.state == 'loading' and not self.current:
            self.engine.stop()
            return
        if not self.model_lock.acquire(blocking=False): raise ValueError('模型正在执行任务，请先取消或等待完成。')
        if action == 'unload':
            try: self.engine.stop()
            finally: self.model_lock.release()
        else:
            self.engine.state = 'loading'
            def load():
                try: self.engine.start()
                except Exception as exc: self.engine.state = 'error'; self.engine.error = str(exc)
                finally: self.model_lock.release()
            threading.Thread(target=load, daemon=True).start()

    def voice(self, body):
        name = text(body.get('name', ''), 100).strip()
        transcript = text(body.get('transcript', ''), 10000).strip()
        if not name or not transcript: raise ValueError('请填写音色名称和参考音频的完整文字。')
        vid = uid()
        if body.get('job_id'):
            job = self.job(body['job_id'])
            if not job or job['status'] != 'completed': raise ValueError('请先生成完整音频。')
            source = self.data / job['file']; content = source.read_bytes(); suffix = '.wav'
        else:
            suffix = Path(text(body.get('filename', 'reference.wav'), 200)).suffix.lower()
            if suffix not in ('.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac'): raise ValueError('不支持该音频格式。')
            content = base64.b64decode(body.get('audio', ''), validate=True)
        if not content or len(content) > 40 * 1024 * 1024: raise ValueError('参考音频必须小于 40 MB 且不能为空。')
        file = 'voices/' + vid + suffix
        (self.data / file).write_bytes(content)
        voice = {'id': vid, 'name': name, 'transcript': transcript, 'file': file,
                 'description': text(body.get('description', ''), 1000), 'created': now(),
                 'sha256': hashlib.sha256(content).hexdigest()}
        if body.get('job_id'):
            voice['source_job_id'] = job['id']
            voice['source_settings'] = clone(job['settings'])
        with self.lock: self.state['voices'].append(voice); self.save()
        return voice

    def export(self, body):
        with self.lock:
            p = self.project(body.get('project_id'))
            if not p: raise ValueError('项目不存在。')
            rows = []
            for s in ([p['single']] if p['mode'] == 'single' else p['segments']):
                sig = signature(s, p['settings'])
                j = next((j for j in reversed(self.state['jobs']) if j['project_id'] == p['id']
                          and j['segment_id'] == s['id'] and j['signature'] == sig and j['status'] == 'completed'), None)
                if not j: raise ValueError(f'「{s["title"]}」尚未生成，或内容已修改。请先生成最新录音。')
                rows.append((clone(s), clone(j)))
            pause = int(body.get('pause_ms', p['pause_ms']))
        paths = [self.data / j['file'] for s, j in rows]
        if sum(f.stat().st_size for f in paths) > 512 * 1024 * 1024: raise ValueError('本次导出超过 512 MB，请拆分项目。')
        if body.get('format') == 'zip':
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
                for i, (s, j) in enumerate(rows):
                    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', s['title'])[:60]
                    z.write(self.data / j['file'], f'{i+1:02d}-{title}.wav')
                z.writestr('script.json', json.dumps([{'title': s['title'], 'text': s['text'], 'settings': j['settings']}
                                                     for s, j in rows], ensure_ascii=False, indent=2))
            return buffer.getvalue(), 'application/zip', 'narration.zip'
        return merge_wavs(paths, pause), 'audio/wav', 'narration.wav'

    def close(self):
        self.closed = True; self.pending.put(None); self.engine.stop()


class Handler(BaseHTTPRequestHandler):
    server_version = 'BreezeStudio/1.0'
    def log_message(self, fmt, *args): pass
    @property
    def app(self): return self.server.app

    def send(self, value, status=200, content_type='application/json; charset=utf-8', filename=None):
        data = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
        self.send_response(status); self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data))); self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff'); self.send_header('Referrer-Policy', 'no-referrer')
        if filename: self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        try: self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass

    def allowed(self):
        host = urllib.parse.urlsplit('http://' + self.headers.get('Host', '')).hostname
        if host not in ('localhost', '127.0.0.1', '::1'): return False
        origin = self.headers.get('Origin')
        if origin:
            u = urllib.parse.urlsplit(origin)
            if u.netloc != self.headers.get('Host') or u.scheme != 'http': return False
        return True

    def do_GET(self):
        try:
            if not self.allowed(): self.send({'error': '只允许本机访问。'}, 403); return
            url = urllib.parse.urlsplit(self.path); path = urllib.parse.unquote(url.path)
            if path == '/api/state': self.send(self.app.snapshot()); return
            if path == '/api/gpu':
                try:
                    r = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.used,memory.total', '--format=csv,noheader,nounits'],
                                       capture_output=True, text=True, timeout=5)
                    rows = [x.strip().split(', ') for x in r.stdout.strip().splitlines() if x.strip()]
                    gpus = [{'name': x[0], 'used': int(x[1]), 'total': int(x[2])} for x in rows if len(x) == 3]
                except (OSError, ValueError, subprocess.TimeoutExpired): gpus = []
                self.send({'gpus': gpus}); return
            if path == '/api/diagnostics':
                c = self.app.config
                files = ['infer.py', 'breeze_infer/runtime.py', 'models/fast_streaming.py']
                hashes = {}
                for f in files:
                    p = Path(c['repo']) / f
                    if c['repo'] and p.is_file(): hashes[f] = hashlib.sha256(p.read_bytes()).hexdigest()
                log = self.app.data / 'worker.log'
                self.send({'config': c, 'source_sha256': hashes, 'adapter': 'official-eager-v1',
                           'fast_all': False, 'precision': 'official load_runtime (not overridden)',
                           'engine': self.app.engine.state, 'error': self.app.engine.error,
                           'log_tail': log.read_text('utf-8', errors='replace')[-14000:] if log.exists() else ''}); return
            if path.startswith('/api/live/'):
                jid = path.rsplit('/', 1)[-1]; cursor = int(urllib.parse.parse_qs(url.query).get('after', ['0'])[0])
                with self.app.lock:
                    j = self.app.job(jid)
                    if not j: self.send({'error': '任务不存在。'}, 404); return
                    events = self.app.events.get(jid, [])
                    self.send({'events': events[cursor:cursor+50], 'cursor': min(len(events), cursor+50), 'status': j['status']})
                return
            if path.startswith('/api/audio/'):
                parts = path.split('/')
                if len(parts) != 5: raise ValueError('音频地址无效。')
                kind, itemid = parts[3:]
                with self.app.lock:
                    obj = self.app.job(itemid) if kind == 'job' else next((v for v in self.app.state['voices'] if v['id'] == itemid), None)
                    if not obj or not obj.get('file') or (kind == 'job' and obj['status'] != 'completed'):
                        self.send({'error': '音频尚未完成。'}, 404); return
                    file = self.app.data / obj['file']
                self.send(file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'audio/wav',
                          filename=(itemid + file.suffix) if 'download' in urllib.parse.parse_qs(url.query) else None); return
            if path.startswith('/api/'): self.send({'error': '接口不存在。'}, 404); return
            base = ROOT / 'dist/client'
            rel = path.lstrip('/') or 'index.html'; file = (base / rel).resolve()
            if not file.is_relative_to(base.resolve()): self.send({'error': '非法路径。'}, 403); return
            if not file.is_file(): self.send({'error': '页面不存在，请先构建前端。'}, 404); return
            self.send(file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
        except Exception as exc: self.send({'error': str(exc)}, 400)

    def do_POST(self):
        try:
            if not self.allowed(): self.send({'error': '不允许跨站请求。'}, 403); return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.send({'error': '请使用 application/json。'}, 415); return
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 56 * 1024 * 1024: self.send({'error': '请求体大小无效。'}, 413); return
            body = json.loads(self.rfile.read(size)); path = urllib.parse.urlsplit(self.path).path
            if not isinstance(body, dict): raise ValueError('请求必须是 JSON 对象。')
            if path == '/api/projects': self.send(self.app.save_project(body)); return
            if path == '/api/jobs': self.send(self.app.submit(body), 202); return
            if path == '/api/designs': self.send(self.app.design(body), 202); return
            if path == '/api/designs/retry': self.send(self.app.retry_design(body), 202); return
            if path == '/api/cancel': self.app.cancel(body.get('ids', [])); self.send({'ok': True}); return
            if path == '/api/model': self.app.lifecycle(body.get('action')); self.send({'ok': True}, 202); return
            if path == '/api/split': self.send({'segments': split_text(body.get('text', ''), body.get('limit', 180))}); return
            if path == '/api/voices': self.send(self.app.voice(body), 201); return
            if path == '/api/voices/delete':
                with self.app.lock:
                    vid = body.get('id')
                    if any(j['settings']['voice_id'] == vid and j['status'] in ACTIVE for j in self.app.state['jobs']):
                        raise ValueError('此音色有未完成任务，请先取消或等待。')
                    # Keep original file so history remains reproducible; remove from selectable library only.
                    self.app.state['voices'] = [v for v in self.app.state['voices'] if v['id'] != vid]; self.app.save()
                self.send({'ok': True}); return
            if path == '/api/config':
                with self.app.lock:
                    if self.app.engine.state in ('loading', 'ready', 'running') or any(j['status'] in ACTIVE for j in self.app.state['jobs']):
                        raise ValueError('请等队列完成并卸载模型后再修改路径。')
                    c = {k: text(body.get(k, self.app.config.get(k, '')), 2000).strip() for k in self.app.config}
                    for k in ('repo', 'model', 'python'):
                        if c[k]:
                            p = Path(c[k]).expanduser()
                            # Resolve the executable symlink only for display, never invocation:
                            # venv/bin/python must retain its path to locate pyvenv.cfg.
                            c[k] = str(p.absolute() if k == 'python' else p.resolve())
                    if c['stt_url']:
                        u = urllib.parse.urlsplit(c['stt_url'])
                        if u.scheme != 'http' or u.hostname not in ('localhost', '127.0.0.1', '::1'):
                            raise ValueError('此版本仅连接本机 HTTP 转写服务，参考录音不发送到外网。')
                    self.app.config = c; self.app.write_json('config.json', c)
                self.send(c); return
            if path == '/api/export':
                data, mime, filename = self.app.export(body); self.send(data, content_type=mime, filename=filename); return
            if path == '/api/transcribe': self.send(self.transcribe(body)); return
            self.send({'error': '接口不存在。'}, 404)
        except Exception as exc: self.send({'error': str(exc)}, 400)

    def transcribe(self, body):
        c = self.app.config
        if not c['stt_url']: raise ValueError('请先在设置中接入本地语音识别服务，也可以手动填写参考文字。')
        audio = base64.b64decode(body.get('audio', ''), validate=True)
        if not audio or len(audio) > 40 * 1024 * 1024: raise ValueError('参考文件为空或超过 40 MB。')
        boundary = 'breeze' + uid()
        filename = re.sub('[^a-zA-Z0-9._-]', '_', body.get('filename', 'reference.wav'))[:100]
        prefix = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{c["stt_model"]}\r\n'
                  f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                  'Content-Type: application/octet-stream\r\n\r\n').encode()
        request = urllib.request.Request(c['stt_url'].rstrip('/') + '/audio/transcriptions',
            data=prefix + audio + f'\r\n--{boundary}--\r\n'.encode(),
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **kw): raise ValueError('本地转写服务重定向已拒绝。')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=120) as response:
            result = json.loads(response.read(1024 * 1024))
        return {'text': text(result.get('text', ''), 10000)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=7860)
    parser.add_argument('--data', default=str(ROOT / 'data'))
    args = parser.parse_args()
    app = Studio(args.data)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler); server.app = app
    app.write_json('server.json', {'port': server.server_port, 'pid': os.getpid()})
    print(f'Breeze Studio: http://localhost:{args.port}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        app.close(); server.server_close()
        runtime = app.data / 'server.json'
        if runtime.exists() and json.loads(runtime.read_text('utf-8')).get('pid') == os.getpid(): runtime.unlink()


if __name__ == '__main__': main()
