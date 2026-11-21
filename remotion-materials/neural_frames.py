"""Generate dense intermediate poses on the local GPU, with a synchronized alpha panel."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from PIL import Image
from timing import CONFIG, ROOT, STEPS, records, timeline

PUBLIC = ROOT / 'public'
DEFAULT_TOOL = ROOT.parent / '.runtime/rife/rife-ncnn-vulkan-20221029-windows/rife-ncnn-vulkan.exe'


def prepare(record):
    points = timeline(record)
    if all(source == points[0][1] for _, source in points):
        return
    destination = PUBLIC / CONFIG['neuralFolder'] / record['id']
    inputs, outputs = destination / 'inputs', destination / 'raw'
    inputs.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(exist_ok=True)
    signature = {'poses': [sha256((PUBLIC / source).read_bytes()).hexdigest() for _, source in points],
                 'steps': STEPS, 'model': 'rife-v4.6', 'layout': 'premultiplied-rgb+alpha-panels-v1'}
    metadata = destination / 'meta.json'
    total = len(points) * STEPS
    if metadata.exists() and json.loads(metadata.read_text()) == signature and len(list(outputs.glob('*.png'))) == total:
        return
    for index, (_, source) in enumerate(points):
        rgba = np.array(Image.open(PUBLIC / source).convert('RGBA'))
        color = np.round(rgba[:, :, :3] * (rgba[:, :, 3:] / 255)).astype('uint8')
        matte = np.repeat(rgba[:, :, 3:], 3, axis=2)
        Image.fromarray(np.concatenate((color, matte), axis=1)).save(inputs / f'{index:03d}.png')
    executable = Path(os.environ.get('PET_RIFE', str(DEFAULT_TOOL)))
    model = executable.parent / 'rife-v4.6'
    assert executable.is_file() and model.is_dir(), 'Set PET_RIFE to the official rife-ncnn-vulkan executable.'
    started = time.monotonic()
    with (destination / 'rife.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(executable), '-m', str(model), '-i', str(inputs), '-o', str(outputs),
                        '-n', str(total), '-g', os.environ.get('PET_RIFE_GPU', '0'), '-j', '2:4:2', '-f', '%04d.png'],
                       check=True, stdout=log, stderr=log,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert len(list(outputs.glob('*.png'))) == total, record['id']
    metadata.write_text(json.dumps(signature), encoding='utf-8')
    print(f'Neural {record["id"]}: {(len(points) - 1) * STEPS + 1} intermediate samples, {time.monotonic()-started:.1f}s', flush=True)


if __name__ == '__main__':
    for record in records():
        prepare(record)
