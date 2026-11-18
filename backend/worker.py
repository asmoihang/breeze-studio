"""Persistent adapter using the installed official infer.py helpers unchanged.

Stdout is JSON IPC. All upstream logs go to stderr. No model files are written.
"""
from __future__ import annotations
import argparse
import base64
import importlib.util
import json
import sys
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    wire = sys.stdout
    sys.stdout = sys.stderr

    def emit(event):
        wire.write(json.dumps(event, ensure_ascii=False) + '\n')
        wire.flush()

    try:
        repo = Path(args.repo).resolve()
        sys.path.insert(0, str(repo))
        spec = importlib.util.spec_from_file_location('breeze_official_cli', repo / 'infer.py')
        official = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(official)
        import soundfile as sf
        import numpy as np
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA 不可用。请在原来的官方虚拟环境中运行，并检查 nvidia-smi。')
        tokenizer, model, codec = official.load_runtime(
            Path(args.model), device=official.resolve_device(), attn_implementation='eager')
        official.update_generation_config_for_breeze(model)
        config = official.FastStreamingConfig(
            max_new_tokens=official.MAX_NEW_TOKENS,
            max_seq_len=official.MAX_SEQ_LEN,
            repetition_penalty=official.REPETITION_PENALTY,
            fast_all=False, fast_text_encoder=False, fast_backbone_prefill=False,
            fast_backbone_decode=False, fast_depth_decoder=False, fast_codec=False)
        runtime = official.FastBreezeStreamingRuntime(model, codec, config, tokenizer=tokenizer)
        emit({'type': 'ready', 'sample_rate': runtime.sample_rate, 'dtype': str(model.dtype)})
    except Exception:
        traceback.print_exc()
        emit({'type': 'error', 'error': traceback.format_exc()[-6000:]})
        return
    for line in sys.stdin:
        try:
            task = json.loads(line)
            request = {'id': 'single-request', 'text': task['text'], 'speaker': 'S0'}
            if task.get('instruction', '').strip():
                request['instruction'] = task['instruction'].strip()
            if task.get('ref_audio'):
                request['ref_audio_path'] = task['ref_audio']
                request['ref_text'] = task['ref_text'].strip()
            official.set_all_seeds(task['seed'])
            inputs = official.prepare_inputs(
                tokenizer, codec, model, [request],
                official.get_template(official.select_template_name(request)),
                guidance_scale=task['cfg'], guidance_scale_ref=None, guidance_scale_ins=None)
            output = Path(task['output'])
            output.parent.mkdir(parents=True, exist_ok=True)
            frames = 0
            with sf.SoundFile(output, mode='w', samplerate=runtime.sample_rate,
                              channels=1, subtype='PCM_16') as f:
                for chunk in runtime.iter_audio_chunks(inputs, request_id='single-request', seed=task['seed']):
                    f.write(chunk.audio)
                    f.flush()
                    frames += len(chunk.audio)
                    event = {'type': 'progress', 'seconds': frames / runtime.sample_rate}
                    if task.get('live'):
                        # Browser audition only. The downloadable WAV is the original sf.write output.
                        pcm = np.asarray(chunk.audio, dtype='<f4').reshape(-1)
                        event.update(pcm=base64.b64encode(pcm.tobytes()).decode(), rate=runtime.sample_rate)
                    emit(event)
            emit({'type': 'done'})
        except Exception:
            traceback.print_exc()
            emit({'type': 'error', 'error': traceback.format_exc()[-6000:]})


if __name__ == '__main__':
    main()
