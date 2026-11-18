"""Optional output processing, independent of model inference and reference voices."""
import array
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import uuid
import wave


def output_settings(value=None):
    if value is None: value = {}
    if not isinstance(value, dict): raise ValueError('声音调节参数必须是对象。')
    try: speed, volume = float(value.get('speed', 1)), float(value.get('volume', 1))
    except (TypeError, ValueError): raise ValueError('语速和音量必须是数字。')
    if not math.isfinite(speed) or not .5 <= speed <= 2:
        raise ValueError('语速范围为 0.50～2.00 倍。')
    if not math.isfinite(volume) or not 0 <= volume <= 2:
        raise ValueError('音量范围为 0～200%。')
    return {'speed': round(speed, 2), 'volume': round(volume, 2)}


class AudioOutput:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(exist_ok=True)
        self.lock = threading.RLock()

    def capabilities(self):
        return {'speed_available': bool(shutil.which('ffmpeg')), 'volume_available': True}

    def render(self, source, values):
        """Return original bytes/path for defaults; cache alternate WAVs separately."""
        source = Path(source)
        values = output_settings(values)
        if values == {'speed': 1, 'volume': 1}: return source
        stat = source.stat()
        if stat.st_size > 128 * 1024 * 1024: raise ValueError('单段音频超过 128 MB，请拆分后调整。')
        key = hashlib.sha256(json.dumps([str(source), stat.st_mtime_ns, stat.st_size, values,
                                        'atempo-pcm16-v1'], sort_keys=True).encode()).hexdigest()
        target = self.directory / (key + '.wav')
        with self.lock:
            if target.exists(): return target
            token = uuid.uuid4().hex
            tempo = self.directory / (token + '.tempo.wav')
            pending = self.directory / (token + '.tmp.wav')
            try:
                current = source
                if values['speed'] != 1:
                    ffmpeg = shutil.which('ffmpeg')
                    if not ffmpeg:
                        raise ValueError('变速需要 FFmpeg。请在 WSL 运行 sudo apt install ffmpeg，然后重试；1.00 倍速和音量调整仍可使用。')
                    try:
                        result = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin',
                            '-y', '-i', str(source), '-map', '0:a:0', '-af', f"atempo={values['speed']}",
                            '-c:a', 'pcm_s16le', str(tempo)], capture_output=True, timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    except subprocess.TimeoutExpired:
                        raise ValueError('音频变速超时，请缩短段落后重试。')
                    if result.returncode:
                        raise ValueError('FFmpeg 变速失败：' + result.stderr.decode('utf-8', errors='replace')[-1200:])
                    current = tempo
                if values['volume'] == 1:
                    shutil.copyfile(current, pending)
                else:
                    with wave.open(str(current), 'rb') as src:
                        if src.getnchannels() != 1 or src.getsampwidth() != 2:
                            raise ValueError('仅支持官方 PCM16 单声道输出。')
                        samples = array.array('h', src.readframes(src.getnframes()))
                        if sys.byteorder != 'little': samples.byteswap()
                        gain = values['volume']
                        if any(round(x * gain) > 32767 or round(x * gain) < -32768 for x in samples):
                            raise ValueError('这个音量会导致破音，请降低音量后重试。原始音频未改变。')
                        samples = array.array('h', (round(x * gain) for x in samples))
                        if sys.byteorder != 'little': samples.byteswap()
                        with wave.open(str(pending), 'wb') as out:
                            out.setparams(src.getparams()); out.writeframes(samples.tobytes())
                os.replace(pending, target)
                return target
            finally:
                tempo.unlink(missing_ok=True); pending.unlink(missing_ok=True)
