"""GPU-side acceptance: original CLI vs two requests through the resident adapter.

Stop/unload the web model first. Does not alter the original repo or checkpoint.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import wave

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'backend'))
from server import Engine

parser = argparse.ArgumentParser()
parser.add_argument('--text', default='今天教你把一份资料整理成对比表。')
parser.add_argument('--instruction', default='普通话清晰的年轻男声，声音自然亲切，语速适中。')
parser.add_argument('--cfg', type=float, default=4)
parser.add_argument('--seed', type=int, default=42)
parser.add_argument('--ref-audio')
parser.add_argument('--ref-text')
args = parser.parse_args()
if bool(args.ref_audio) != bool(args.ref_text): parser.error('reference audio and transcript must be supplied together')
data = root / 'data'
c = json.loads((data / 'config.json').read_text('utf-8'))
# Comparison must not load/save the live project's queue or mark its jobs failed.
engine = Engine(SimpleNamespace(data=data, config=c))
folder = root / 'data/comparison'; folder.mkdir(exist_ok=True)
cmd = [c['python'], str(Path(c['repo']) / 'infer.py'), c['model'], '--text', args.text,
       '--cfg-scale', str(args.cfg), '--seed', str(args.seed), '--no-fast-all', '--output', str(folder / 'official.wav')]
if args.instruction: cmd += ['--instruction', args.instruction]
if args.ref_audio: cmd += ['--ref-audio', str(Path(args.ref_audio).resolve()), '--ref-text', args.ref_text]
try:
    print('1/3 Original CLI (make sure the web model is unloaded)', flush=True)
    subprocess.run(cmd, cwd=c['repo'], check=True)
    for i in range(2):
        print(f'{i+2}/3 Resident adapter request', flush=True)
        engine.generate({'text': args.text, 'instruction': args.instruction, 'cfg': args.cfg, 'seed': args.seed,
                             'ref_audio': str(Path(args.ref_audio).resolve()) if args.ref_audio else '',
                             'ref_text': args.ref_text or '', 'output': str(folder / f'adapter-{i+1}.wav'), 'live': False}, lambda e: None)
    def read(path):
        with wave.open(str(path), 'rb') as f: return (f.getnchannels(), f.getsampwidth(), f.getframerate(), f.getnframes()), f.readframes(f.getnframes())
    baseline, pcm = read(folder / 'official.wav')
    report = {'official_params': baseline, 'official_pcm_sha256': hashlib.sha256(pcm).hexdigest(), 'comparisons': []}
    for i in range(2):
        params, other = read(folder / f'adapter-{i+1}.wav')
        report['comparisons'].append({'run': i+1, 'same_format_and_length': params == baseline,
                                      'pcm_byte_identical': other == pcm, 'pcm_sha256': hashlib.sha256(other).hexdigest()})
    report['note'] = 'Byte equality is a strict same-machine check, not a perceptual quality score. If different, listen to all WAVs and inspect environment/version.'
    (folder / 'report.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report, indent=2)); print('Saved comparison files:', folder)
finally: engine.stop()
