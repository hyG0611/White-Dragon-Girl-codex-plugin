"""Measure real Qt decoder/cached-loop cadence using the same code as the desktop pet."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'codex-adapter/plugins/dsh-dragon/runtime'))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
import media


def main():
    app = QGuiApplication([])
    pool = media.ClipPool(lambda frame: frame)
    path = ROOT / 'out-chulong/transparent/待机呼吸休闲.webm'
    key = (path, 100, None)
    observed, failures = [], []
    previous = None
    original = media.subprocess.Popen
    with patch('media.subprocess.Popen', wraps=original) as starts:
        clip = pool.acquire(key)

        def sample():
            nonlocal previous
            try:
                frame = clip.read()
                if frame is None or frame.cacheKey() == previous:
                    return
                previous = frame.cacheKey()
                observed.append(time.monotonic())
                image = frame.toImage()
                assert image.pixelColor(0, 0).alpha() <= 4
                assert not clip.finished
                if observed[-1] - observed[0] >= 12.3:
                    app.quit()
            except BaseException as error:
                failures.append(str(error))
                app.quit()

        timer = QTimer()
        timer.timeout.connect(sample)
        timer.start(8)
        QTimer.singleShot(30000, app.quit)
        app.exec()
        duration = observed[-1] - observed[0] if len(observed) > 1 else 0
        gaps = [b - a for a, b in zip(observed, observed[1:])]
        result = {'frames_observed': len(observed), 'duration_seconds': round(duration, 3),
                  'observed_fps': round((len(observed) - 1) / duration, 2) if duration else 0,
                  'native_fps': round(1 / clip.interval, 2), 'decoder_starts': starts.call_count,
                  'maximum_frame_gap_ms': round(max(gaps) * 1000, 2) if gaps else None,
                  'errors': failures, 'measurement': 'Qt Clip.read at 8 ms; includes the 10-second loop boundary'}
        pool.close()
        clip.worker.join(timeout=5)
    (ROOT / 'out-chulong/playback-report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    assert not failures and duration >= 12.3 and result['observed_fps'] >= 28
    assert starts.call_count == 1, 'The loop should reuse losslessly cached frames.'


if __name__ == '__main__':
    main()
