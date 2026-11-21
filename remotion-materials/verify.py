"""Validate rendered desktop-pet clips and produce a contact sheet and manifest."""
from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from timing import CONFIG, DURATION, FPS, FRAME_COUNT

ROOT = Path(__file__).resolve().parent
OUT = ROOT / CONFIG['outputFolder']


def main():
    actions = json.loads((ROOT / 'actions.json').read_text(encoding='utf-8'))
    report = []
    sheet = Image.new('RGB', (1280, ((len(actions) + 3) // 4) * 210), '#262536')
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    font = ImageFont.truetype(str(font_path), 15) if font_path.exists() else ImageFont.load_default()
    boundaries = {}
    margin_failures = []
    for index, action in enumerate(actions):
        path = OUT / (action['name'] + '.mp4')
        capture = cv2.VideoCapture(str(path))
        assert capture.isOpened(), path
        assert capture.get(cv2.CAP_PROP_FRAME_WIDTH) == 640
        assert capture.get(cv2.CAP_PROP_FRAME_HEIGHT) == 360
        assert abs(capture.get(cv2.CAP_PROP_FPS) - FPS) < 0.001
        frames, first, last, sample = 0, None, None, None
        outer_bad = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if first is None:
                first = frame.copy()
            if frames == round(4.67 * FPS):
                sample = frame.copy()
            # The background is exact RGB green before H.264 compression, with a tolerance after encoding.
            green = cv2.inRange(frame, (0, 243, 0), (12, 255, 12))
            outer_bad += int(not (green[:36].all() and green[-36:].all() and green[:, :64].all() and green[:, -64:].all()))
            last = frame
            frames += 1
        capture.release()
        assert frames == FRAME_COUNT, (path, frames)
        if outer_bad:
            margin_failures.append({'name': action['name'], 'id': action['id'], 'frames_outside_safe_area': outer_bad})
        boundaries[action['name']] = (first, last)
        boundary_error = float(np.abs(first.astype('float32') - last).mean())
        if action['name'] not in ('睡觉-开始', '睡觉-起来'):
            assert boundary_error < 1.5, (path, boundary_error)
        prepared = ROOT / 'public' / CONFIG['preparedFolder'] / action['id']
        fingerprints = [sha256((prepared / f'{index:03d}.png').read_bytes()).digest() for index in range(FRAME_COUNT)]
        duplicated = sum(a == b for a, b in zip(fingerprints, fingerprints[1:]))
        unique = len(set(fingerprints))
        assert duplicated <= 3 and unique >= FRAME_COUNT * .98, (action['name'], duplicated, unique)
        report.append({'name': action['name'], 'file': path.name, 'frames': frames, 'fps': FPS,
                       'seconds': DURATION, 'width': 640, 'height': 360, 'safe_margin': '10%',
                       'unique_prepared_frames': unique, 'adjacent_duplicate_frames': duplicated,
                       'first_last_mean_error': round(boundary_error, 5),
                       'sha256': sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size})
        thumb = Image.fromarray(cv2.cvtColor(sample, cv2.COLOR_BGR2RGB)).resize((320, 180))
        x, y = (index % 4) * 320, (index // 4) * 210
        sheet.paste(thumb, (x, y))
        ImageDraw.Draw(sheet).text((x + 8, y + 186), f'{index + 1:02d}  {action["name"]}', font=font, fill='white')
        print('Verified', action['name'], f'{unique}/{FRAME_COUNT} unique source frames', flush=True)
    sleep_first, sleep_last = boundaries['睡觉-循环']
    for frame in (boundaries['睡觉-开始'][1], boundaries['睡觉-起来'][0], sleep_last):
        error = np.abs(frame.astype('float32') - sleep_first).mean()
        assert error < 1.5, error
    (OUT / 'needs-margin-fix.json').write_text(json.dumps(margin_failures, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not margin_failures, margin_failures
    alpha_report = OUT / 'alpha-report.json'
    if alpha_report.exists():
        alphas = json.loads(alpha_report.read_text(encoding='utf-8'))
        for row in report:
            row['webm'] = alphas[row['name']]
    (OUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    sheet.save(OUT / '动作总览.jpg', quality=92)
    print(f'Validated {len(report)} clips, including the three sleep boundaries.')


if __name__ == '__main__':
    main()
