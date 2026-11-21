"""Bake smooth pose interpolation once so Remotion only has to composite frame images."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
GRID_X, GRID_Y = np.meshgrid(np.arange(320, dtype='float32'), np.arange(320, dtype='float32'))
SAFE_ACTIONS = set(json.loads((ROOT / 'src/safe-actions.json').read_text(encoding='utf-8')))


def timeline(record):
    idle, sleep = 'poses/idle.png', 'poses/sleep.png'
    poses = record['poses']
    if record['name'] == '待机呼吸休闲':
        return [(0, idle), (10, idle)]
    if record['name'] == '睡觉-循环':
        return [(0, sleep), (10, sleep)]
    if record['name'] == '睡觉-开始':
        return [(0, idle), (.8, idle), (1.8, poses[0]), (3.2, poses[1]), (5, poses[2]), (7, sleep), (10, sleep)]
    if record['name'] == '睡觉-起来':
        return [(0, sleep), (.8, sleep), (2.6, poses[1]), (4.8, poses[2]), (7.2, poses[3]), (9, idle), (10, idle)]
    return [(0, idle), (.8, idle), (1.8, poses[0]), (3.4, poses[1]), (5.2, poses[2]),
            (7.2, poses[3]), (9.1, idle), (10, idle)]


def flow(a, b):
    path = PUBLIC / 'flows' / f'{Path(a).stem}--{Path(b).stem}.png'
    return (np.array(Image.open(path)).astype('float32')[:, :, :2] - 128) / 2


def bake_record(record):
    cache = 'frames-safe' if record['id'] in SAFE_ACTIONS else 'frames-v3' if record['name'] == '睡觉-循环' else 'frames-v2' if int(record['id'][6:]) >= 100 else 'frames'
    destination = PUBLIC / cache / record['id']
    destination.mkdir(parents=True, exist_ok=True)
    poses = {}
    for _, src in timeline(record):
        pixels = np.array(Image.open(PUBLIC / src).convert('RGBA')).astype('float32') / 255
        pixels[:, :, :3] *= pixels[:, :, 3:]
        poses[src] = pixels
    maps = {}
    frames = timeline(record)
    for i in range(300):
        path = destination / f'{i:03d}.png'
        if path.exists():
            continue
        seconds = i / 30
        index = max(j for j, frame in enumerate(frames) if frame[0] <= seconds)
        start, a = frames[index]
        end, b = frames[min(index + 1, len(frames) - 1)]
        pixels = poses[a]
        if a != b:
            linear = max(0, min(1, (seconds - start) / (end - start)))
            progress = linear * linear * (3 - 2 * linear)
            for pair in ((a, b), (b, a)):
                if pair not in maps:
                    maps[pair] = np.clip(flow(*pair), -12, 12) if record['id'] in SAFE_ACTIONS else flow(*pair)
            forward, backward = maps[(a, b)], maps[(b, a)]
            previous = cv2.remap(poses[a], GRID_X - progress * forward[:, :, 0],
                                 GRID_Y - progress * forward[:, :, 1], cv2.INTER_LINEAR)
            following = cv2.remap(poses[b], GRID_X - (1 - progress) * backward[:, :, 0],
                                  GRID_Y - (1 - progress) * backward[:, :, 1], cv2.INTER_LINEAR)
            pixels = previous * (1 - progress) + following * progress
        sleeping = record['name'] == '睡觉-循环'
        still = (i in (0, 299)) if sleeping else seconds < .8 or seconds >= 9.1
        if record['name'] == '睡觉-开始':
            still = seconds < .8 or seconds >= 7
        elif record['name'] == '睡觉-起来':
            still = seconds <= .8 or seconds >= 9
        breath = 0 if still else math.sin(seconds * math.pi * (.5 if sleeping else 1.2))
        matrix = cv2.getRotationMatrix2D((160, 290), 0 if sleeping else -breath * .65, 1)
        matrix[:, 1] *= 1 + breath * (.003 if sleeping else .007)
        matrix[:, 2] -= matrix[:, 1] * (290 * breath * (.003 if sleeping else .007))
        if breath:
            pixels = cv2.warpAffine(pixels, matrix, (320, 320), flags=cv2.INTER_LINEAR)
        rgba = pixels.copy()
        rgba[:, :, :3] = np.divide(pixels[:, :, :3], pixels[:, :, 3:],
                                   out=np.zeros_like(pixels[:, :, :3]), where=pixels[:, :, 3:] > .001)
        output = np.clip(np.round(rgba * 255), 0, 255).astype('uint8')[:, :, [2, 1, 0, 3]]
        if sleeping and 1 < seconds < 8.6:
            overlay = Image.new('RGBA', (320, 320))
            draw = ImageDraw.Draw(overlay)
            for symbol in range(3):
                cycle = ((seconds - 1 + symbol * .7) % 2.6) / 2.6
                alpha = round(math.sin(cycle * math.pi) * .7 * min(1, (8.6 - seconds) * 2) * 255)
                font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', round(14 + cycle * 7))
                draw.text((150 + symbol * 10, 142 - cycle * 48), 'Z', fill=(216, 208, 237, alpha), font=font)
            picture = Image.fromarray(output[:, :, [2, 1, 0, 3]])
            picture.alpha_composite(overlay)
            output = np.array(picture)[:, :, [2, 1, 0, 3]]
        if not cv2.imwrite(str(path), output, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
            raise RuntimeError(f'Cannot save {path}')
    print('Baked', record['id'], record['name'], flush=True)


def main():
    records = json.loads((ROOT / 'src/actions.json').read_text(encoding='utf-8'))
    cv2.setNumThreads(1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(bake_record, records))
    print('All 109 actions have 300 precomputed motion frames.', flush=True)


if __name__ == '__main__':
    main()
