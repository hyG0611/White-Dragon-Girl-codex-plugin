"""Bake 60 fps from dense neural poses and continuous, exactly closing secondary motion."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from timing import CONFIG, DURATION, FRAME_COUNT, ROOT, STEPS, records, timeline

PUBLIC = ROOT / 'public'
GRID_X, GRID_Y = np.meshgrid(np.arange(320, dtype='float32'), np.arange(320, dtype='float32'))
SIDES = np.clip((np.abs(GRID_X - 160) - 62) / 55, 0, 1) * np.exp(-((GRID_Y - 200) / 100) ** 2)


def bake_record(record):
    destination = PUBLIC / CONFIG['preparedFolder'] / record['id']
    destination.mkdir(parents=True, exist_ok=True)
    points = timeline(record)
    sleeping = record['name'] == '睡觉-循环'
    neural = PUBLIC / CONFIG['neuralFolder'] / record['id'] / 'raw'

    @lru_cache(maxsize=16)
    def source_image(source):
        rgba = np.array(Image.open(PUBLIC / source).convert('RGBA')).astype('float32') / 255
        rgba[:, :, :3] *= rgba[:, :, 3:]
        return rgba

    @lru_cache(maxsize=8)
    def neural_image(index):
        packed = np.array(Image.open(neural / f'{index + 1:04d}.png').convert('RGB')).astype('float32') / 255
        alpha = packed[:, 320:].mean(axis=2, keepdims=True)
        alpha[alpha < 3 / 255] = 0
        alpha[alpha > 254 / 255] = 1
        return np.concatenate((np.minimum(packed[:, :320], alpha), alpha), axis=2)

    for frame in range(FRAME_COUNT):
        path = destination / f'{frame:03d}.png'
        if path.exists():
            continue
        seconds = frame * DURATION / (FRAME_COUNT - 1)
        phase = seconds / DURATION
        segment = min(len(points) - 2, max(j for j, point in enumerate(points) if point[0] <= seconds))
        start, a = points[segment]
        end, b = points[segment + 1]
        linear = min(1, max(0, (seconds - start) / (end - start)))
        progress = .35 * linear + .65 * linear * linear * (3 - 2 * linear)
        if a == b:
            pixels = source_image(a)
        elif linear < 1e-7:
            pixels = source_image(a)
        elif linear > 1 - 1e-7:
            pixels = source_image(b)
        else:
            position = segment * STEPS + progress * STEPS
            first = math.floor(position)
            mix = position - first
            pixels = neural_image(first) * (1 - mix) + neural_image(first + 1) * mix
        # Whole cycles, no hard hold gate: no .8/9.1-second snap.
        breath = math.sin(phase * math.tau * (2 if sleeping else 4))
        sway = math.sin(phase * math.tau * 3)
        strength = .4 if sleeping else 1
        matrix = cv2.getRotationMatrix2D((160, 290), sway * .55 * strength, 1)
        matrix[:, 1] *= 1 + breath * .006 * strength
        matrix[:, 2] -= matrix[:, 1] * (290 * breath * .006 * strength)
        matrix[0, 2] += math.sin(phase * math.tau * 2) * .65 * strength
        matrix[1, 2] += sway * .45 * strength
        pixels = cv2.warpAffine(pixels, matrix, (320, 320), flags=cv2.INTER_LINEAR)
        pixels = cv2.remap(pixels, GRID_X + SIDES * math.sin(phase * math.tau * 4) * .9 * strength,
                           GRID_Y + SIDES * sway * .5 * strength, cv2.INTER_LINEAR)
        rgba = pixels.copy()
        rgba[:, :, :3] = np.divide(pixels[:, :, :3], pixels[:, :, 3:], out=np.zeros_like(pixels[:, :, :3]),
                                   where=pixels[:, :, 3:] > .001)
        output = np.clip(np.round(rgba * 255), 0, 255).astype('uint8')
        if sleeping:
            picture = Image.fromarray(output)
            overlay = Image.new('RGBA', (320, 320))
            draw = ImageDraw.Draw(overlay)
            envelope = math.sin(math.pi * phase) ** 2
            for symbol in range(3):
                cycle = (phase * 3 + symbol / 3) % 1
                alpha = round(math.sin(cycle * math.pi) ** 2 * envelope * 180)
                font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 17)
                draw.text((150 + symbol * 10, 142 - cycle * 44), 'Z', fill=(216, 208, 237, alpha), font=font)
            picture.alpha_composite(overlay)
            output = np.array(picture)
        if not cv2.imwrite(str(path), output[:, :, [2, 1, 0, 3]], [cv2.IMWRITE_PNG_COMPRESSION, 1]):
            raise RuntimeError(f'Cannot save {path}')
    print('Baked', record['id'], record['name'], FRAME_COUNT, 'frames', flush=True)


if __name__ == '__main__':
    cv2.setNumThreads(1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(bake_record, records()))
