from pathlib import Path
import sys
import threading
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
from media import Clip, FRAME_BYTES


class LosslessLoopCacheTests(unittest.TestCase):
    def test_compressible_loop_reuses_source_and_releases_its_budget(self):
        frames = [bytes([value]) * FRAME_BYTES for value in (10, 20, 30)]
        seen = []
        def enqueue(frame):
            if frame is not None:
                seen.append(frame)
            return len(seen) < 8
        budget = threading.BoundedSemaphore(8)
        clip = SimpleNamespace(loop=True, cancelled=threading.Event(), cache_slots=budget,
                               source_frames=MagicMock(side_effect=lambda: (frame for frame in frames)), enqueue=enqueue)
        with patch('media.zlib.compress', wraps=zlib.compress) as compress:
            Clip.decode(clip)
            self.assertEqual(compress.call_count, 3)
        clip.source_frames.assert_called_once()
        self.assertEqual(seen[:8], (frames * 3)[:8])
        for _ in range(8):
            self.assertTrue(budget.acquire(False))

    def test_incompressible_frame_falls_back_without_leaking_partial_reservation(self):
        frame = os.urandom(FRAME_BYTES)
        seen = []
        def enqueue(pixels):
            if pixels is not None:
                seen.append(pixels)
            return len(seen) < 3
        budget = threading.BoundedSemaphore(2)
        clip = SimpleNamespace(loop=True, cancelled=threading.Event(), cache_slots=budget,
                               source_frames=lambda: (pixels for pixels in [frame]), enqueue=enqueue)
        Clip.decode(clip)
        self.assertEqual(seen, [frame] * 3)
        self.assertTrue(budget.acquire(False))
        self.assertTrue(budget.acquire(False))
