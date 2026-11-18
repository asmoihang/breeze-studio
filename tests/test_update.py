import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('studio_update', Path(__file__).resolve().parents[1] / 'scripts/update.py')
updater = importlib.util.module_from_spec(spec); spec.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def git(self, cwd, *args):
        result = subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@local', *args],
                                cwd=cwd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='breeze-git-test-')
        self.base = Path(self.temp.name); self.remote = self.base / 'remote'; self.remote.mkdir()
        self.git(self.remote, 'init', '-b', 'main')
        for name in ['dist/client/index.html', 'backend/server.py', 'backend/worker.py', 'VERSION']:
            p = self.remote / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('initial', 'utf-8')
        (self.remote / '.gitignore').write_text('/data/\n', 'utf-8')
        self.git(self.remote, 'add', '.'); self.git(self.remote, 'commit', '-m', 'Initial')
        self.local = self.base / 'local'
        self.git(self.base, 'clone', str(self.remote), str(self.local))
        self.previous_root = updater.ROOT; updater.ROOT = self.local
        (self.local / 'data/voices').mkdir(parents=True)
        (self.local / 'data/config.json').write_text('{"python":"/original/.venv/bin/python"}', 'utf-8')
        (self.local / 'data/state.json').write_text('{"voices":["mine"]}', 'utf-8')
        (self.local / 'data/voices/reference.wav').write_bytes(b'original reference audio')
    def tearDown(self):
        updater.ROOT = self.previous_root
        # Windows marks Git objects read-only; TemporaryDirectory handles those on supported Python.
        self.temp.cleanup()
    def new_version(self):
        (self.remote / 'VERSION').write_text('0.2.0', 'utf-8')
        self.git(self.remote, 'add', '.'); self.git(self.remote, 'commit', '-m', 'Update')
    def test_fast_forward_preserves_data_and_backs_up_metadata(self):
        self.new_version()
        config = (self.local / 'data/config.json').read_bytes()
        state = (self.local / 'data/state.json').read_bytes()
        with contextlib.redirect_stdout(io.StringIO()): updater.main()
        self.assertEqual((self.local / 'VERSION').read_text('utf-8'), '0.2.0')
        self.assertEqual((self.local / 'data/config.json').read_bytes(), config)
        self.assertEqual((self.local / 'data/state.json').read_bytes(), state)
        self.assertEqual((self.local / 'data/voices/reference.wav').read_bytes(), b'original reference audio')
        backups = list((self.local / 'data/backups').glob('*/state.json'))
        self.assertEqual(len(backups), 1); self.assertEqual(backups[0].read_bytes(), state)
    def test_dirty_program_refused(self):
        self.new_version(); (self.local / 'backend/server.py').write_text('local work', 'utf-8')
        with self.assertRaisesRegex(RuntimeError, '本地修改'): updater.main()
        self.assertEqual((self.local / 'VERSION').read_text('utf-8'), 'initial')
    def test_remote_data_file_refused_before_merge(self):
        self.new_version()
        (self.remote / 'data').mkdir()
        (self.remote / 'data/state.json').write_text('overwrite', 'utf-8')
        self.git(self.remote, 'add', '-f', 'data/state.json'); self.git(self.remote, 'commit', '-m', 'Unsafe data')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, '本地数据'):
            updater.main()
        self.assertEqual((self.local / 'data/state.json').read_text('utf-8'), '{"voices":["mine"]}')
        self.assertEqual((self.local / 'VERSION').read_text('utf-8'), 'initial')


if __name__ == '__main__': unittest.main()
