import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
config_file = root / 'data/config.json'
if not config_file.exists():
    print('Please run bash start.sh first, or save paths in the Settings page.'); sys.exit(1)
c = json.loads(config_file.read_text('utf-8'))
report = {'config': c, 'checks': {}, 'source_sha256': {}}
for name, sub in [('repo', 'infer.py'), ('model', 'audio_tokenizer'), ('python', '')]:
    p = Path(c.get(name, '')) / sub
    report['checks'][name] = bool(c.get(name)) and p.exists()
for name in ['infer.py', 'breeze_infer/runtime.py', 'models/fast_streaming.py']:
    p = Path(c.get('repo', '')) / name
    if p.is_file(): report['source_sha256'][name] = hashlib.sha256(p.read_bytes()).hexdigest()
try:
    result = subprocess.run([c['python'], '-c',
        'import torch, soundfile, transformers; print("torch",torch.__version__); print("CUDA",torch.cuda.is_available()); print("GPU",torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")'],
        capture_output=True, text=True, timeout=90)
    report['environment'] = result.stdout + result.stderr; report['environment_exit_code'] = result.returncode
except Exception as e: report['environment_error'] = str(e)
log = root / 'data/worker.log'
report['worker_log_tail'] = log.read_text('utf-8', errors='replace')[-12000:] if log.exists() else ''
dest = root / 'data/diagnostics.json'
dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
print('Saved:', dest)
