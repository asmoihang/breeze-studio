import base64
import copy
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import wave
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from server import Studio, Handler, ThreadingHTTPServer, merge_wavs, split_text, settings, signature


def wav_bytes(samples=(1, -2, 300, -400), rate=24000):
    out = io.BytesIO()
    with wave.open(out, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
    return out.getvalue()


class TestEngine:
    """Only injected in tests, never an available production backend."""
    def __init__(self, app): self.state = 'unloaded'; self.error = ''; self.stopped = False; self.calls = []; self.delay = 0
    def start(self): self.state = 'ready'; self.stopped = False
    def stop(self): self.stopped = True; self.state = 'unloaded'
    def generate(self, task, callback):
        self.state = 'running'; self.calls.append(copy.deepcopy(task))
        until = time.monotonic() + self.delay
        while time.monotonic() < until:
            if self.stopped: raise RuntimeError('cancelled')
            time.sleep(.01)
        if task['text'] == 'FAIL': raise RuntimeError('injected failure')
        Path(task['output']).write_bytes(wav_bytes()); callback({'type': 'progress', 'seconds': 1})
        self.state = 'ready'


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Studio(self.tmp.name, TestEngine)
        self.p = self.app.save_project({'id': 'p', 'name': '教程', 'mode': 'segments',
            'settings': {'voice_id': '', 'instruction': '自然男声', 'cfg': 4, 'seed': 42},
            'single': {'text': '自由配音'},
            'segments': [{'id': 'a', 'title': '开场', 'text': '你好。'}, {'id': 'b', 'title': '操作', 'text': '点击按钮。'}]})
    def tearDown(self): self.app.close(); self.tmp.cleanup()
    def wait(self, jobs):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if all(self.app.job(j['id'])['status'] not in ('queued', 'loading', 'running') for j in jobs): return
            time.sleep(.02)
        self.fail('queue did not finish')
    def test_queue_preserves_reference_and_settings(self):
        data = wav_bytes(); v = self.app.voice({'name': '教程男声', 'transcript': '这是参考文字。', 'filename': 'a.wav', 'audio': base64.b64encode(data).decode()})
        self.assertEqual((self.app.data / v['file']).read_bytes(), data)
        self.p['settings'].update(voice_id=v['id'], instruction='', cfg=1)
        self.p['segments'][1]['settings'] = {**self.p['settings'], 'instruction': '语速慢', 'cfg': 4, 'seed': 7}
        self.app.save_project(self.p); jobs = self.app.submit({'project_id': 'p'}); self.wait(jobs)
        self.assertTrue(all(self.app.job(j['id'])['status'] == 'completed' for j in jobs))
        a, b = self.app.engine.calls
        self.assertEqual(a['ref_text'], '这是参考文字。'); self.assertEqual(a['cfg'], 1)
        self.assertEqual(b['instruction'], '语速慢'); self.assertEqual(b['seed'], 7)
        self.assertEqual(Path(a['ref_audio']).read_bytes(), data)
    def test_stale_output_rejected_then_partial_regeneration(self):
        jobs = self.app.submit({'project_id': 'p'}); self.wait(jobs)
        self.p['segments'][1]['text'] = '修改后的操作。'; self.app.save_project(self.p)
        with self.assertRaisesRegex(ValueError, '已修改'): self.app.export({'project_id': 'p'})
        jobs2 = self.app.submit({'project_id': 'p', 'segment_ids': ['b']}); self.wait(jobs2)
        self.assertEqual(len(self.app.engine.calls), 3)
        data, mime, _ = self.app.export({'project_id': 'p', 'format': 'zip'})
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(z.read('01-开场.wav'), wav_bytes())
            self.assertEqual(z.read('02-操作.wav'), wav_bytes())
    def test_merge_keeps_pcm_and_inserts_exact_silence(self):
        a = Path(self.tmp.name) / 'one.wav'; a.write_bytes(wav_bytes())
        merged = merge_wavs([a, a], 300)
        with wave.open(io.BytesIO(merged), 'rb') as f:
            self.assertEqual(f.getnframes(), 4 + 7200 + 4)
            pcm = struct.pack('<hhhh', 1, -2, 300, -400)
            self.assertEqual(f.readframes(f.getnframes()), pcm + b'\0' * 14400 + pcm)
        b = Path(self.tmp.name) / 'two.wav'; b.write_bytes(wav_bytes(rate=16000))
        with self.assertRaises(ValueError): merge_wavs([a, b], 300)
    def test_cancel_running_and_queued(self):
        self.app.engine.delay = .4
        jobs = self.app.submit({'project_id': 'p'})
        for _ in range(100):
            if self.app.current: break
            time.sleep(.01)
        self.app.cancel([j['id'] for j in jobs]); self.wait(jobs)
        time.sleep(.1)
        self.assertEqual([self.app.job(j['id'])['status'] for j in jobs], ['cancelled', 'cancelled'])
        self.assertLessEqual(len(self.app.engine.calls), 1)
    def test_failure_does_not_poison_next_job(self):
        self.p['segments'][0]['text'] = 'FAIL'; self.app.save_project(self.p)
        jobs = self.app.submit({'project_id': 'p'}); self.wait(jobs)
        self.assertEqual([self.app.job(j['id'])['status'] for j in jobs], ['failed', 'completed'])
    def test_single_mode_does_not_generate_segments(self):
        self.p['mode'] = 'single'; self.app.save_project(self.p)
        jobs = self.app.submit({'project_id': 'p'}); self.wait(jobs)
        self.assertEqual(len(jobs), 1); self.assertEqual(self.app.engine.calls[0]['text'], '自由配音')
    def test_duplicate_inflight_not_added(self):
        self.app.engine.delay = .2
        first = self.app.submit({'project_id': 'p'}); second = self.app.submit({'project_id': 'p'})
        self.assertEqual(second, []); self.wait(first)
    def test_restart_marks_interrupted_jobs(self):
        with self.app.lock:
            self.app.state['jobs'].append({'id': 'interrupted', 'status': 'running'}); self.app.save()
        other = Studio(self.tmp.name, TestEngine)
        try: self.assertEqual(other.job('interrupted')['status'], 'failed')
        finally: other.close()
    def test_long_split_preserves_chinese_punctuation(self):
        source = '第一步，点击上传。第二步，输入要求！' * 40
        rows = split_text(source, 100)
        self.assertEqual(''.join(rows), source); self.assertTrue(all(len(r) <= 100 for r in rows))
    def test_signature_matches_browser_json(self):
        self.assertEqual(signature(self.p['segments'][0], self.p['settings']), '["你好。","","自然男声",4,42]')
    def test_design_candidates_only_change_seed_and_preserve_project(self):
        before = copy.deepcopy(self.app.state['projects'])
        batch = self.app.design({'name': '甜妹教程女声', 'instruction': '普通话女声，清甜自然。',
                                 'text': '先点击上传按钮。', 'cfg': 4, 'seed': 42, 'count': 3})
        jobs = [self.app.job(jid) for jid in batch['job_ids']]; self.wait(jobs)
        self.assertEqual(self.app.state['projects'], before)
        self.assertEqual([j['settings']['seed'] for j in jobs], [42, 43, 44])
        self.assertTrue(all(j['status'] == 'completed' and j['kind'] == 'voice-design' for j in jobs))
        for call in self.app.engine.calls:
            self.assertEqual(call['text'], '先点击上传按钮。')
            self.assertEqual(call['instruction'], '普通话女声，清甜自然。')
            self.assertEqual(call['cfg'], 4); self.assertEqual(call['ref_audio'], '')
        voice = self.app.voice({'name': '甜妹', 'job_id': jobs[1]['id'], 'transcript': jobs[1]['text']})
        self.assertEqual((self.app.data / voice['file']).read_bytes(), wav_bytes())
        self.assertEqual(voice['source_settings']['seed'], 43)
        self.assertEqual(voice['source_job_id'], jobs[1]['id'])
        restored = Studio(self.tmp.name, TestEngine)
        try: self.assertEqual(restored.state['designs'], [batch])
        finally: restored.close()
    def test_design_retries_only_failed_candidate(self):
        batch = self.app.design({'name': '失败测试', 'instruction': '甜美女声', 'text': 'FAIL', 'count': 1})
        old = self.app.job(batch['job_ids'][0]); self.wait([old])
        retry = self.app.retry_design({'id': batch['id'], 'job_id': old['id']})
        self.wait([retry])
        self.assertEqual(self.app.state['designs'][0]['job_ids'], [retry['id']])
        self.assertEqual(old['status'], 'failed')
        self.assertEqual(retry['settings'], old['settings'])
        self.assertEqual(len(self.app.state['jobs']), 2)
        with self.assertRaises(ValueError): self.app.retry_design({'id': batch['id'], 'job_id': old['id']})
    def test_design_validation_is_atomic(self):
        valid = {'name': '甜妹', 'instruction': '甜美女声', 'text': '你好。', 'count': 3}
        for patch in [{'count':0}, {'count':7}, {'count':1.5}, {'seed':4294967295},
                      {'text':''}, {'instruction':''}, {'name':''}, {'cfg':float('nan')}]:
            with self.assertRaises(ValueError): self.app.design({**valid, **patch})
        self.assertEqual(self.app.state['designs'], [])
        self.assertEqual(self.app.state['jobs'], [])
    def test_invalid_cfg_and_missing_voice(self):
        for n in [1.5, float('nan'), float('inf'), -1, 4294967296]:
            with self.assertRaises(ValueError): settings({'seed': n})
        for n in [float('nan'), float('inf'), 0, -1]:
            with self.assertRaises(ValueError): settings({'cfg': n})
        self.p['settings']['voice_id'] = 'missing'; self.app.save_project(self.p)
        with self.assertRaisesRegex(ValueError, '音色不存在'): self.app.submit({'project_id': 'p'})


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Studio(self.tmp.name, TestEngine)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); self.server.app = self.app
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def tearDown(self): self.server.shutdown(); self.server.server_close(); self.app.close(); self.tmp.cleanup()
    def test_api_origin_and_validation(self):
        self.assertEqual(json.load(self.opener.open(self.base + '/api/state'))['engine'], 'unloaded')
        request = urllib.request.Request(self.base + '/api/projects', data=b'{}', headers={'Content-Type': 'application/json', 'Origin': 'https://untrusted.example'})
        with self.assertRaises(urllib.error.HTTPError) as err: self.opener.open(request)
        self.assertEqual(err.exception.code, 403)
        request = urllib.request.Request(self.base + '/api/split', data=json.dumps({'text': '你好。'}).encode(), headers={'Content-Type': 'application/json', 'Origin': self.base})
        self.assertEqual(json.load(self.opener.open(request))['segments'], ['你好。'])
    def test_local_stt_only(self):
        request = urllib.request.Request(self.base + '/api/config', data=json.dumps({'stt_url': 'https://outside.example/v1'}).encode(), headers={'Content-Type': 'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as err: self.opener.open(request)
        self.assertEqual(err.exception.code, 400)
    def test_zip_http_contains_all_segments_and_exact_original_audio(self):
        p = self.app.save_project({'id': 'zip-http', 'mode': 'segments',
            'settings': {'instruction': '自然'},
            'segments': [{'id': str(i), 'title': f'第 {i+1} 段', 'text': f'教程文案{i}。'} for i in range(10)]})
        raw = wav_bytes((1000, -1000) * 24000)
        for s in p['segments']:
            file = 'outputs/' + s['id'] + '.wav'
            (self.app.data / file).write_bytes(raw)
            self.app.state['jobs'].append({'id': s['id'], 'project_id': p['id'], 'segment_id': s['id'],
                'signature': signature(s, p['settings']), 'settings': p['settings'], 'status': 'completed', 'file': file})
        request = urllib.request.Request(self.base + '/api/export',
            data=json.dumps({'project_id': p['id'], 'format': 'zip', 'variant': 'original'}).encode(),
            headers={'Content-Type': 'application/json'})
        with self.opener.open(request) as response:
            data = response.read()
            self.assertEqual(response.headers['Content-Type'], 'application/zip')
            self.assertEqual(int(response.headers['Content-Length']), len(data))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()), 11)
            for i in range(10): self.assertEqual(archive.read(f'{i+1:02d}-第 {i+1} 段.wav'), raw)
            self.assertEqual(len(json.loads(archive.read('script.json'))), 10)
    def test_config_keeps_venv_executable_path(self):
        from unittest.mock import patch
        executable = str(Path(self.tmp.name) / '.venv' / 'bin' / 'python')
        request = urllib.request.Request(self.base + '/api/config',
            data=json.dumps({'python': executable}).encode(), headers={'Content-Type': 'application/json'})
        original = Path.resolve
        def resolve(path, *args, **kwargs):
            if str(path) == executable:
                self.fail('Resolving the venv executable loses its environment')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'resolve', resolve):
            self.opener.open(request).close()
        self.assertEqual(self.app.config['python'], str(Path(executable).absolute()))


if __name__ == '__main__': unittest.main()
