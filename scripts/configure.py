"""Detect the existing install; no downloads and no modifications to it."""
import argparse
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--repo')
parser.add_argument('--model')
parser.add_argument('--python', dest='python_path')
args = parser.parse_args()
config_path = root / 'data/config.json'
config = json.loads(config_path.read_text('utf-8')) if config_path.exists() else {}
repo = Path(args.repo or config.get('repo') or Path.home() / 'breeze-work/breeze-tts').expanduser().absolute()
model = Path(args.model or config.get('model') or repo.parent / 'models/Breeze-TTS-2').expanduser().absolute()
python = Path(args.python_path or config.get('python') or repo / '.venv/bin/python').expanduser().absolute()
if args.repo or args.model or args.python_path or (repo / 'infer.py').exists():
    config.update(repo=str(repo), model=str(model), python=str(python))
    config.setdefault('stt_url', ''); config.setdefault('stt_model', 'whisper-1')
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp = config_path.with_suffix('.tmp')
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), 'utf-8'); temp.replace(config_path)
print('\nBreeze Studio - official model adapter')
print('Repo:  ', config.get('repo', '(set in the web Settings page)'))
print('Model: ', config.get('model', '(set in the web Settings page)'))
print('Python:', config.get('python', '(set in the web Settings page)'))
print('No packages or model weights will be installed or changed.\n')
