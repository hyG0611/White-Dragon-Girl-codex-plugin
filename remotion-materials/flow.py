"""Precompute bidirectional flow maps for smooth 30 fps key-pose interpolation."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
POSES = ROOT / 'public/poses'
FLOWS = ROOT / 'public/flows'


def flow_name(a, b):
    return FLOWS / f'{Path(a).stem}--{Path(b).stem}.png'


def make_pair(pair):
    source, target = pair
    destination = flow_name(source, target)
    if destination.exists():
        return
    previous = np.array(Image.open(POSES / Path(source).name).convert('RGBA'))
    following = np.array(Image.open(POSES / Path(target).name).convert('RGBA'))
    def gray(image):
        rgb = (image[:, :, :3] * (image[:, :, 3:] / 255)).astype('uint8')
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    displacement = dis.calc(gray(previous), gray(following), None)
    packed = np.full((320, 320, 3), 128, dtype='uint8')
    packed[:, :, :2] = np.clip(np.round(displacement * 2 + 128), 0, 255).astype('uint8')
    Image.fromarray(packed).save(destination)


def main():
    FLOWS.mkdir(exist_ok=True)
    records = json.loads((ROOT / 'src/actions.json').read_text(encoding='utf-8'))
    pairs = set()
    for record in records:
        poses = record['poses']
        if not all((ROOT / 'public' / pose).exists() for pose in poses):
            continue
        if record['name'] == '睡觉-循环':
            continue
        first = 'poses/sleep.png' if record['name'] == '睡觉-起来' else 'poses/idle.png'
        last = 'poses/sleep.png' if record['name'] == '睡觉-开始' else 'poses/idle.png'
        if record['name'] == '睡觉-开始':
            poses = poses[:3]
        if record['name'] == '睡觉-起来':
            poses = poses[1:]
        timeline = [first, *poses, last]
        for a, b in zip(timeline, timeline[1:]):
            if a != b:
                pairs.add((a, b))
                pairs.add((b, a))
    cv2.setNumThreads(1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(make_pair, sorted(pairs)))
    print(f'{len(pairs)} motion maps ready.')


if __name__ == '__main__':
    main()
