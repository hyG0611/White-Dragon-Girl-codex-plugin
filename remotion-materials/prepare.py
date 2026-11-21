"""Extract generated atlas cells and normalize their baseline for Remotion."""
from pathlib import Path
import json

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'


def clean_cell(image):
    pixels = np.array(image.convert('RGBA'))
    count, labels, stats, _ = cv2.connectedComponentsWithStats((pixels[:, :, 3] >= 64).astype('uint8'))
    keep = np.zeros(labels.shape, dtype=bool)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= 35:
            keep |= labels == label
    keep = cv2.dilate(keep.astype('uint8'), np.ones((3, 3), 'uint8'))
    pixels[:, :, 3] *= keep
    return Image.fromarray(pixels)


def normalize(image, scale):
    crop = image.crop(image.getbbox())
    size = (round(crop.width * scale), round(crop.height * scale))
    crop = crop.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (320, 320))
    canvas.alpha_composite(crop, (160 - crop.width // 2, 290 - crop.height))
    return canvas


def main():
    out = PUBLIC / 'poses'
    out.mkdir(exist_ok=True)
    actions = json.loads((ROOT / 'actions.json').read_text(encoding='utf-8'))
    for group in range((len(actions) + 5) // 6):
        if not (PUBLIC / f'atlas-{group}.png').is_file():
            continue
        atlas = Image.open(PUBLIC / f'atlas-{group}.png').convert('RGBA')
        assert atlas.size == (1536, 1024), atlas.size
        for column in range(6):
            if group * 6 + column >= len(actions):
                continue
            for row in range(4):
                cell = clean_cell(atlas.crop((column * 256, row * 256, (column + 1) * 256, (row + 1) * 256)))
                normalize(cell, 0.94).save(out / f'{group * 6 + column + 1:02d}-{row}.png')

    (out / 'idle.png').write_bytes((out / '49-0.png').read_bytes())
    (out / 'sleep.png').write_bytes((out / '46-3.png').read_bytes())
    for action in actions:
        action['poses'] = [f'poses/{int(action["id"][6:]):02d}-{row}.png' for row in range(4)]
    (ROOT / 'src/actions.json').write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Prepared {len(actions) * 4} key poses and two shared boundary poses.')


if __name__ == '__main__':
    main()
