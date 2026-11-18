"""Fast-forward a Git installation; preserve local config, voices and outputs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PROTECTED = ('data/', 'models/', 'weights/', '.venv/', 'venv/', '.env')


def git(*args, check=True):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Git command failed')
    return result


def validate_tree(paths):
    for path in paths:
        if path.startswith(PROTECTED):
            raise RuntimeError('更新包含本地数据或模型路径，已停止：' + path)
    for required in ('dist/client/index.html', 'backend/server.py', 'backend/worker.py', 'VERSION'):
        if required not in paths: raise RuntimeError('更新缺少必要文件：' + required)


def ensure_stopped():
    runtime = ROOT / 'data/server.json'
    if not runtime.exists(): return
    try:
        port = int(json.loads(runtime.read_text('utf-8'))['port'])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/state', timeout=2): pass
    except (urllib.error.URLError, TimeoutError, ConnectionError): return
    except (ValueError, KeyError): raise RuntimeError('无法读取服务状态，请先关闭网页服务并检查 data/server.json。')
    raise RuntimeError('网页服务仍在运行。请在启动它的终端按 Ctrl+C，然后重新更新。')


def main():
    if not shutil.which('git'): raise RuntimeError('找不到 Git，请先在 WSL 中安装 Git。')
    if git('rev-parse', '--show-toplevel', check=False).returncode:
        raise RuntimeError('这是 ZIP 安装目录。请先按 README 的 Git 迁移步骤克隆仓库并复制 data 文件夹。')
    if Path(git('rev-parse', '--show-toplevel').stdout.strip()).resolve() != ROOT:
        raise RuntimeError('当前目录不是独立的 Breeze Studio 仓库根目录。')
    ensure_stopped()
    if git('status', '--porcelain', '--untracked-files=normal').stdout.strip():
        raise RuntimeError('程序文件有本地修改或未跟踪文件，请先检查 git status 并保存修改；更新不会自动覆盖它们。')
    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD').stdout.strip()
    remote = git('config', '--get', f'branch.{branch}.remote').stdout.strip()
    if remote == '.': raise RuntimeError('当前分支未跟踪远程仓库。')
    git('rev-parse', '--verify', '@{u}')
    print('检查远程版本…', flush=True)
    git('fetch', '--prune', remote)
    before = git('rev-parse', 'HEAD').stdout.strip()
    target = git('rev-parse', '@{u}').stdout.strip()
    if before == target:
        print('已经是最新版本。'); return
    if git('merge-base', '--is-ancestor', before, target, check=False).returncode:
        raise RuntimeError('本地和远程历史已分叉，停止自动更新。请保留本地提交后人工处理。')
    paths = git('ls-tree', '-r', '--name-only', target).stdout.splitlines()
    validate_tree(paths)
    backup = ROOT / 'data/backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + before[:8])
    for name in ('config.json', 'state.json'):
        file = ROOT / 'data' / name
        if file.exists():
            backup.mkdir(parents=True, exist_ok=True); shutil.copy2(file, backup / name)
    git('merge', '--ff-only', target)
    print('更新完成：', before[:8], '→', target[:8])
    print('版本：', (ROOT / 'VERSION').read_text('utf-8').strip())
    if backup.exists(): print('项目与配置备份：', backup)
    print('运行 bash start.sh 重新启动。模型与音频未改动。')


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('更新未完成：' + str(exc), file=sys.stderr); sys.exit(1)
