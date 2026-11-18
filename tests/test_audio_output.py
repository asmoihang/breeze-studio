import copy
import io
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from audio_output import AudioOutput, output_settings
from server import Studio, signature
from test_backend import TestEngine, wav_bytes


def samples(data):
    with wave.open(io.BytesIO(data), 'rb') as f:
        return struct.unpack('<' + 'h' * f.getnframes(), f.readframes(f.getnframes())), f.getframerate()


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.processor = AudioOutput(self.base / 'processed')
        self.source = self.base / 'source.wav'
        self.source.write_bytes(wav_bytes((1000, -1000, 32000, -32000)))

    def tearDown(self): self.temp.cleanup()

    def test_defaults_bypass_ffmpeg_and_preserve_every_byte(self):
        original = self.source.read_bytes()
        with patch('audio_output.shutil.which', return_value=None), patch('audio_output.subprocess.run', side_effect=AssertionError):
            self.assertEqual(self.processor.render(self.source, {}), self.source)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list(self.processor.directory.iterdir()), [])

    def test_gain_and_silence_without_ffmpeg(self):
        with patch('audio_output.shutil.which', return_value=None):
            half = self.processor.render(self.source, {'volume': .5})
            silent = self.processor.render(self.source, {'volume': 0})
        self.assertEqual(samples(half.read_bytes())[0], (500, -500, 16000, -16000))
        self.assertEqual(samples(silent.read_bytes())[0], (0, 0, 0, 0))
        self.assertEqual(samples(half.read_bytes())[1], 24000)
        self.assertEqual(self.processor.render(self.source, {'volume': .5}), half)

    def test_clipping_is_rejected_and_original_unchanged(self):
        before = self.source.read_bytes()
        with self.assertRaisesRegex(ValueError, '破音'):
            self.processor.render(self.source, {'volume': 2})
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(list(self.processor.directory.iterdir()), [])

    def test_bad_settings_and_missing_ffmpeg(self):
        for value in ({'speed': float('nan')}, {'volume': float('inf')}, {'speed': .49}, {'volume': -1}, {'speed': 'oops'}, []):
            with self.assertRaises(ValueError): output_settings(value)
        with patch('audio_output.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'sudo apt install ffmpeg'):
                self.processor.render(self.source, {'speed': 1.1})

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not installed')
    def test_real_atempo_duration_pitch_and_source_integrity(self):
        rate = 24000
        self.source.write_bytes(wav_bytes(tuple(round(6000*math.sin(2*math.pi*440*i/rate)) for i in range(rate*3)), rate))
        original = self.source.read_bytes()
        for speed in (.5, 1.1, 2):
            path = self.processor.render(self.source, {'speed': speed, 'volume': .5})
            values, actual_rate = samples(path.read_bytes())
            self.assertEqual(rate, actual_rate)
            self.assertAlmostEqual(len(values)/rate, 3/speed, delta=.12)
            middle = values[rate//5:-rate//5]
            rising = sum(a<=0<b for a,b in zip(middle,middle[1:]))
            self.assertAlmostEqual(rising/(len(middle)/rate), 440, delta=3)
            self.assertLess(max(values), 3300)
        self.assertEqual(self.source.read_bytes(), original)


class OutputProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Studio(self.temp.name, TestEngine)
        self.p = self.app.save_project({'id':'project', 'mode':'segments', 'settings':{'instruction':'自然'},
            'single':{'text':'单段'}, 'pause_ms':100, 'segments':[
                {'id':'a','title':'第一段','text':'你好'}, {'id':'b','title':'第二段','text':'再见'}]})
        self.jobs=[]
        for s in self.p['segments']:
            path='outputs/'+s['id']+'.wav'; (self.app.data/path).write_bytes(wav_bytes((1000,-1000)*240,24000))
            self.jobs.append({'id':s['id'], 'project_id':self.p['id'], 'segment_id':s['id'],
                'signature':signature(s,self.p['settings']), 'settings':copy.deepcopy(self.p['settings']),
                'status':'completed', 'file':path, 'text':s['text']})
        self.app.state['jobs']=self.jobs

    def tearDown(self): self.app.close(); self.temp.cleanup()

    def test_inheritance_override_preview_export_identity_and_restart(self):
        self.p['output']={'speed':1,'volume':.5}
        self.p['segments'][1]['output']={'speed':1,'volume':.25}
        saved=self.app.save_project(self.p)
        rendered=self.app.render({'project_id':'project'})
        exported=self.app.export({'project_id':'project'})[0]
        path=self.app.audio_output.directory/(rendered['url'].rsplit('/',1)[-1]+'.wav')
        self.assertEqual(path.read_bytes(), exported)
        pcm,rate=samples(exported)
        self.assertEqual(pcm[:2],(500,-500));self.assertEqual(pcm[-2:],(250,-250))
        self.assertEqual(len(pcm),480*2+2400)
        self.assertAlmostEqual(rendered['duration'],len(pcm)/rate)
        self.assertEqual(self.app.engine.calls, [])
        self.assertEqual(self.jobs[0]['signature'],signature(saved['segments'][0],saved['settings']))
        other=Studio(self.temp.name,TestEngine)
        try:self.assertEqual(other.project('project')['output'],self.p['output'])
        finally:other.close()
        self.p['segments'][1]['output']=None;self.app.save_project(self.p)
        self.assertEqual(samples(self.app.export({'project_id':'project'})[0])[0][-2:],(500,-500))

    def test_original_zip_and_reference_remain_raw(self):
        self.p['output']={'speed':1,'volume':.5};self.app.save_project(self.p)
        raw=(self.app.data/'outputs/a.wav').read_bytes()
        data=self.app.export({'project_id':'project','format':'zip','variant':'original'})[0]
        with zipfile.ZipFile(io.BytesIO(data)) as z:self.assertEqual(z.read('01-第一段.wav'),raw)
        voice=self.app.voice({'name':'原声','job_id':'a','transcript':'你好'})
        self.assertEqual((self.app.data/voice['file']).read_bytes(),raw)
        preview=self.app.render({'project_id':'project','segment_id':'a','variant':'original'})
        self.assertEqual(preview['url'],'/api/audio/job/a')

    def test_stale_script_cannot_be_previewed_or_exported(self):
        self.p['segments'][0]['text']='改过';self.app.save_project(self.p)
        for method in (self.app.render,self.app.export):
            with self.assertRaisesRegex(ValueError,'已修改'):method({'project_id':'project'})

    def test_single_mode_uses_project_output(self):
        self.p['mode']='single';saved=self.app.save_project(self.p)
        job=copy.deepcopy(self.jobs[0]);job.update(id='single-job',segment_id=saved['single']['id'],signature=signature(saved['single'],saved['settings']))
        self.app.state['jobs'].append(job)
        self.assertEqual(self.app.export({'project_id':'project'})[0],(self.app.data/job['file']).read_bytes())
        self.p['output']={'speed':1,'volume':.5};self.app.save_project(self.p)
        self.assertEqual(samples(self.app.export({'project_id':'project'})[0])[0][:2],(500,-500))

    def test_mode_switch_retains_both_drafts_overrides_and_recordings(self):
        self.p['segments'][1]['settings']={**self.p['settings'],'seed':57}
        self.p['segments'][1]['output']={'speed':1.1,'volume':.8}
        before=copy.deepcopy(self.app.save_project(self.p))
        for mode in ('single','segments','single','segments'):
            before['mode']=mode
            saved=self.app.save_project(before)
            self.assertEqual(saved['single'],before['single'])
            self.assertEqual(saved['segments'],before['segments'])
        restarted=Studio(self.temp.name,TestEngine)
        try:
            self.assertEqual(restarted.project('project')['segments'],before['segments'])
            self.assertEqual(len(restarted.state['jobs']),2)
        finally:restarted.close()
        self.assertEqual(self.app.engine.calls,[])

    def test_export_one_segment_with_incomplete_sibling_and_output_override(self):
        self.p['segments'][0]['text']='尚未配音的新文案'
        self.p['segments'][1]['output']={'speed':1,'volume':.25}
        self.app.save_project(self.p)
        with self.assertRaisesRegex(ValueError,'已修改'):
            self.app.export({'project_id':'project'})
        data=self.app.export({'project_id':'project','segment_id':'b'})[0]
        pcm,rate=samples(data)
        self.assertEqual(len(pcm),480)
        self.assertEqual(pcm[:2],(250,-250))
        raw=(self.app.data/'outputs/b.wav').read_bytes()
        self.assertEqual(self.app.export({'project_id':'project','segment_id':'b','variant':'original'})[0],raw)
        with self.assertRaisesRegex(ValueError,'找不到'):
            self.app.export({'project_id':'project','segment_id':'missing'})


if __name__ == '__main__': unittest.main()
