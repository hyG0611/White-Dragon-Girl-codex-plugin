"""Flatten prepared RGBA frames onto the same green canvas shown in Remotion Studio."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
SAFE_ACTIONS = set(json.loads((ROOT / 'src/safe-actions.json').read_text(encoding='utf-8')))


def composite(record):
    safe = record['id'] in SAFE_ACTIONS
    cache = 'frames-safe' if safe else 'frames-v3' if record['name'] == '睡觉-循环' else 'frames-v2' if int(record['id'][6:]) >= 100 else 'frames'
    source = PUBLIC / cache / record['id']
    destination = PUBLIC / ('composited-safe' if safe else 'composited') / record['id']
    destination.mkdir(parents=True, exist_ok=True)
    for frame in range(300):
        target = destination / f'{frame:03d}.png'
        if target.exists():
            continue
        image = cv2.imread(str(source / target.name), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise RuntimeError(f'Incomplete prepared frame: {record["id"]}/{target.name}')
        alpha = image[:, :, 3:] / 255
        canvas = np.full((360, 640, 3), (0, 255, 0), dtype='uint8')
        canvas[16:336, 160:480] = np.clip(np.round(image[:, :, :3] * alpha + np.array([0, 255, 0]) * (1 - alpha)), 0, 255)
        if not cv2.imwrite(str(target), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
            raise RuntimeError(f'Cannot write {target}')
    print('Composited', record['id'], flush=True)


if __name__ == '__main__':
    records = json.loads((ROOT / 'src/actions.json').read_text(encoding='utf-8'))
    cv2.setNumThreads(1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(composite, records))
    print('109 green frame sequences composited.', flush=True)
