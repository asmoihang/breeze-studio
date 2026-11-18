"""Create a portable source + built UI archive, excluding all local user data."""
import hashlib
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent.parent
out = root.parent / 'outputs'
out.mkdir(exist_ok=True)
destination = out / 'Breeze-Studio-WSL2.zip'
folders = ['backend', 'src', 'dist/client', 'scripts', 'tests', 'worker', '.openai', 'qa']
files = [root / name for name in ['README.md', 'start.sh', 'update.sh', 'VERSION', '.gitignore', '.gitattributes', 'AGENTS.md', 'index.html',
         'package.json', 'package-lock.json', 'vite.config.mjs', '.npmrc', 'design-qa.md']]
for folder in folders:
    files.extend(p for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
    for file in sorted(set(files)):
        if file.exists(): archive.write(file, 'breeze-studio/' + file.relative_to(root).as_posix())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert 'breeze-studio/dist/client/index.html' in archive.namelist()
    assert not any('/data/' in name or '/node_modules/' in name for name in archive.namelist())
    assert b'\r' not in archive.read('breeze-studio/start.sh'), 'start.sh must use LF in WSL'
checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
destination.with_suffix('.sha256').write_text(checksum + '  ' + destination.name + '\n', 'utf-8')
print(destination)
print(f'{destination.stat().st_size:,} bytes; SHA256 {checksum}')
