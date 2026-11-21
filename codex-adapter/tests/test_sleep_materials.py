from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
from pet import Pet


class SleepMaterialsTests(unittest.TestCase):
    def test_sleep_start_continues_with_loop(self):
        pet = SimpleNamespace(cap=SimpleNamespace(read=lambda: None, finished=True),
                              release_clip=MagicMock(), play=MagicMock(), idle='idle',
                              current='睡觉-开始', actions={'睡觉-开始': Path('start.webm'), '睡觉-循环': Path('loop.webm')})
        Pet.tick(pet)
        pet.play.assert_called_once_with('睡觉-循环')

    def test_loop_uses_shared_looping_decoder(self):
        pet = SimpleNamespace(actions={'睡觉-循环': Path('loop.webm')}, speed=100, idle='idle',
                              pool=MagicMock(), release_clip=MagicMock(), pause_walk=MagicMock(),
                              update_frame_interval=MagicMock())
        Pet.play(pet, '睡觉-循环')
        self.assertIsNone(pet.pool.acquire.call_args.args[0][2])
