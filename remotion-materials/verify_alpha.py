"""Decode each transparent companion with libvpx and verify native cadence and alpha."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

import cv2
import numpy as np
from timing import CONFIG, FPS, FRAME_COUNT

ROOT = Path(__file__).resolve().parent
OUT = ROOT / CONFIG['outputFolder']
FFMPEG = Path(os.environ.get('PET_FFMPEG', r'D:\Desktop\ds-pet\dsh-pet\codex-adapter\.runtime\Scripts\ffmpeg.exe'))
FRAME_BYTES = 640 * 360 * 4


def main():
    report = json.loads((ROOT / 'actions.json').read_text(encoding='utf-8'))
    for index, row in enumerate(report):
        video = OUT / 'transparent' / (row['name'] + '.webm')
        metadata = cv2.VideoCapture(str(video))
        assert metadata.isOpened(), video
        assert abs(metadata.get(cv2.CAP_PROP_FPS) - FPS) < .001
        metadata.release()
        decoded = subprocess.run([str(FFMPEG), '-nostdin', '-loglevel', 'error', '-c:v', 'libvpx-vp9', '-i', str(video),
                                  '-vf', f'select=not(mod(n\\,{FPS//2}))+eq(n\\,{FRAME_COUNT-1})', '-fps_mode', 'passthrough',
                                  '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], capture_output=True, check=True)
        samples = list(range(0, FRAME_COUNT, FPS//2)) + [FRAME_COUNT - 1]
        assert len(decoded.stdout) == FRAME_BYTES * len(samples), (row['name'], len(decoded.stdout), decoded.stderr)
        frames = np.frombuffer(decoded.stdout, dtype='uint8').reshape(len(samples), 360, 640, 4)
        for frame in frames:
            alpha = frame[:, :, 3]
            assert alpha.max() == 255 and np.count_nonzero(alpha > 200) > 1000, row['name']
            # VP9's alpha plane is lossy too. Permit four levels of quantization noise at transparent edges.
            assert alpha[:36].max() <= 4 and alpha[-36:].max() <= 4, row['name']
            assert alpha[:, :64].max() <= 4 and alpha[:, -64:].max() <= 4, row['name']
        row['webm'] = {'file': video.name, 'bytes': video.stat().st_size,
                       'sha256': sha256(video.read_bytes()).hexdigest(), 'alpha_samples_checked': samples,
                       'transparent_edge_tolerance': 4}
        if index % 10 == 0:
            print(f'Alpha verified {index + 1}/{len(report)}', flush=True)
    (OUT / 'alpha-report.json').write_text(json.dumps({row['name']: row['webm'] for row in report},
                                                       ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'109 native {FPS} fps transparent WebM clips verified.', flush=True)


if __name__ == '__main__':
    main()
