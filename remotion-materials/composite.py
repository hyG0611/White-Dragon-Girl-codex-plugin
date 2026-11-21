"""Flatten prepared RGBA frames onto the same green canvas shown in Remotion Studio."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import cv2
import numpy as np
from timing import CONFIG, FRAME_COUNT, records

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
SAFE_ACTIONS = set(json.loads((ROOT / 'src/safe-actions.json').read_text(encoding='utf-8')))


def composite(record):
    source = PUBLIC / CONFIG['preparedFolder'] / record['id']
    destination = PUBLIC / CONFIG['compositedFolder'] / record['id']
    destination.mkdir(parents=True, exist_ok=True)
    for frame in range(FRAME_COUNT):
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
    cv2.setNumThreads(1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(composite, records()))
    print('Green frame sequences composited.', flush=True)
