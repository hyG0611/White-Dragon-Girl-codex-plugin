from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
from media import Clip


class MediaCadenceTests(unittest.TestCase):
    def test_webm_keeps_native_thirty_fps(self):
        clip = Clip.__new__(Clip)
        clip.path = Path('thirty-fps.webm')
        clip.ffmpeg = 'ffmpeg.exe'
        clip.speed = 100
        clip.cancelled = threading.Event()
        clip.process_lock = threading.Lock()
        capture = MagicMock()
        capture.get.return_value = 30
        process = MagicMock()
        process.stdout.read.return_value = b''
        process.poll.return_value = 0
        with patch('media.cv2.VideoCapture', return_value=capture), patch('media.subprocess.Popen', return_value=process) as start:
            self.assertEqual(list(clip.source_frames()), [])
            self.assertAlmostEqual(clip.interval, 1 / 30)
            self.assertNotIn('fps=24,scale=640:360', start.call_args.args[0])
            capture.release.assert_called_once()
