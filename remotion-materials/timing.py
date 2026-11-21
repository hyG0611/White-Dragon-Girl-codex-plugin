"""One timing and output contract for neural preparation, rendering and validation."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'src/render-config.json').read_text(encoding='utf-8'))
FPS = CONFIG['fps']
DURATION = CONFIG['durationSeconds']
FRAME_COUNT = FPS * DURATION
STEPS = CONFIG['neuralSteps']


def records():
    actions = json.loads((ROOT / 'src/actions.json').read_text(encoding='utf-8'))
    selected = set(os.environ.get('ACTIONS', '').split(',')) - {''}
    return [action for action in actions if not selected or action['id'] in selected]


def timeline(record):
    idle, sleep = 'poses/idle.png', 'poses/sleep.png'
    poses = record['poses']
    if record['name'] == '待机呼吸休闲':
        return [(0, idle), (2.8, poses[1]), (3.02, poses[2]), (3.2, poses[3]),
                (6.8, poses[0]), (8.4, poses[1]), (8.58, poses[2]), (8.78, poses[3]), (10, idle)]
    if record['name'] == '睡觉-循环':
        return [(0, sleep), (10, sleep)]
    if record['name'] == '睡觉-开始':
        return [(0, idle), (1.8, poses[0]), (3.7, poses[1]), (6, poses[2]), (9, sleep), (10, sleep)]
    if record['name'] == '睡觉-起来':
        return [(0, sleep), (2.2, poses[1]), (4.6, poses[2]), (7.2, poses[3]), (10, idle)]
    return [(0, idle), (1.6, poses[0]), (3.6, poses[1]), (5.8, poses[2]), (8, poses[3]), (10, idle)]
