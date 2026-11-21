"""Regressions for the visible freeze and breath-to-rest jump, independent of RIFE."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import bake


class IdleMotionContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = []
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.runtime') as temporary:
            public = Path(temporary)
            (public / 'poses').mkdir()
            Image.open(Path(__file__).resolve().parent / 'public/poses/idle.png').save(public / 'poses/idle.png')
            record = {'id': 'Action49', 'name': '待机呼吸休闲', 'poses': ['poses/idle.png'] * 4}
            def collect(path, image, *args):
                cls.frames.append(image.copy())
                return True
            with patch.object(bake, 'PUBLIC', public), patch.object(bake.cv2, 'imwrite', side_effect=collect):
                bake.bake_record(record)

    def test_idle_has_no_long_run_of_duplicate_frames(self):
        longest, run = 0, 0
        for previous, following in zip(self.frames, self.frames[1:]):
            run = run + 1 if np.array_equal(previous, following) else 0
            longest = max(longest, run)
        self.assertLessEqual(longest, 3, 'Idle breath must continue through the old .8/9.1-second stops.')

    def test_breath_does_not_snap_back_to_its_baseline(self):
        visible = [image[:, :, :3].astype('float32') * (image[:, :, 3:] / 255) for image in self.frames]
        differences = np.array([np.abs(b - a).mean() for a, b in zip(visible, visible[1:])])
        limit = np.percentile(differences, 95) * 1.75 + .05
        self.assertLessEqual(float(differences.max()), limit, 'Motion has a discontinuity.')
        self.assertTrue(np.array_equal(self.frames[0], self.frames[-1]), 'Idle loop must close exactly.')


if __name__ == '__main__':
    unittest.main()
