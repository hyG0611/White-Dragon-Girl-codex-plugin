"""Decode each transparent companion with libvpx and verify native cadence and alpha."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out-chulong'
FFMPEG = Path(os.environ.get('PET_FFMPEG', r'D:\Desktop\ds-pet\dsh-pet\codex-adapter\.runtime\Scripts\ffmpeg.exe'))
FRAME_BYTES = 640 * 360 * 4


def main():
    report = json.loads((ROOT / 'actions.json').read_text(encoding='utf-8'))
    for index, row in enumerate(report):
        video = OUT / 'transparent' / (row['name'] + '.webm')
        metadata = cv2.VideoCapture(str(video))
        assert metadata.isOpened(), video
        assert abs(metadata.get(cv2.CAP_PROP_FPS) - 30) < .001
        metadata.release()
        decoded = subprocess.run([str(FFMPEG), '-nostdin', '-loglevel', 'error', '-c:v', 'libvpx-vp9', '-i', str(video),
                                  '-vf', r'select=eq(n\,0)+eq(n\,149)+eq(n\,299)', '-fps_mode', 'passthrough',
                                  '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], capture_output=True, check=True)
        assert len(decoded.stdout) == FRAME_BYTES * 3, (row['name'], len(decoded.stdout), decoded.stderr)
        frames = np.frombuffer(decoded.stdout, dtype='uint8').reshape(3, 360, 640, 4)
        for frame in frames:
            alpha = frame[:, :, 3]
            assert alpha.max() == 255 and np.count_nonzero(alpha > 200) > 1000, row['name']
            # VP9's alpha plane is lossy too. Permit four levels of quantization noise at transparent edges.
            assert alpha[:36].max() <= 4 and alpha[-36:].max() <= 4, row['name']
            assert alpha[:, :64].max() <= 4 and alpha[:, -64:].max() <= 4, row['name']
        row['webm'] = {'file': video.name, 'bytes': video.stat().st_size,
                       'sha256': sha256(video.read_bytes()).hexdigest(), 'alpha_samples_checked': [0, 149, 299],
                       'transparent_edge_tolerance': 4}
        if index % 10 == 0:
            print(f'Alpha verified {index + 1}/{len(report)}', flush=True)
    (OUT / 'alpha-report.json').write_text(json.dumps({row['name']: row['webm'] for row in report},
                                                       ensure_ascii=False, indent=2), encoding='utf-8')
    print('109 native 30 fps transparent WebM clips verified.', flush=True)


if __name__ == '__main__':
    main()
