"""Encode transparent VP9 directly from original RGBA poses, preserving colored props."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out-chulong'
DEST = OUT / 'transparent'
FFMPEG = Path(os.environ.get('PET_FFMPEG', r'D:\Desktop\ds-pet\dsh-pet\codex-adapter\.runtime\Scripts\ffmpeg.exe'))
SAFE_ACTIONS = set(json.loads((ROOT / 'src/safe-actions.json').read_text(encoding='utf-8')))


def encode(record):
    target = DEST / (record['name'] + '.webm')
    if target.is_file() and target.stat().st_size > 1000:
        return
    cache = 'frames-safe' if record['id'] in SAFE_ACTIONS else 'frames-v3' if record['name'] == '睡觉-循环' else 'frames-v2' if int(record['id'][6:]) >= 100 else 'frames'
    source = ROOT / 'public' / cache / record['id']
    assert all((source / f'{frame:03d}.png').is_file() for frame in range(300)), source
    temporary = target.with_suffix('.partial.webm')
    subprocess.run([str(FFMPEG), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                    '-framerate', '30', '-start_number', '0', '-i', str(source / '%03d.png'),
                    '-vf', 'format=rgba,pad=640:360:160:16:color=black@0.0,format=yuva420p',
                    '-frames:v', '300', '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p',
                    '-b:v', '0', '-crf', '24', '-deadline', 'realtime', '-cpu-used', '5',
                    '-threads', '2', '-row-mt', '1', '-auto-alt-ref', '0', str(temporary)],
                   check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    temporary.replace(target)
    print('Transparent RGBA', record['id'], record['name'], flush=True)


def main():
    DEST.mkdir(exist_ok=True)
    actions = json.loads((ROOT / 'actions.json').read_text(encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(encode, actions))
    print('All 109 transparent companions completed.', flush=True)


if __name__ == '__main__':
    main()
