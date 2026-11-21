"""Copy the verified character to the named material library and DSH plugin installations."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
from timing import CONFIG

ROOT = Path(__file__).resolve().parent
OUT = ROOT / CONFIG['outputFolder']
WORKSPACE = ROOT.parent
LIBRARY = Path(r'D:\Desktop\素材库\雏龙娘')
BACKUP = LIBRARY / '备份' / '30fps-2026-11-21'
ROLE_ROOTS = [WORKSPACE / 'codex-adapter/plugins/dsh-dragon/assets/characters/雏龙娘',
              Path(r'D:\Desktop\ds-pet\dsh-pet\codex-adapter\plugins\dsh-dragon\assets\characters\雏龙娘'),
              Path(r'C:\Users\admin\.codex\plugins\cache\dsh-dragon-local\dsh-dragon\1.0.0\assets\characters\雏龙娘')]

DESCRIPTION = '''# 雏龙娘

独立桌宠角色，按 DSH 提示词库完整制作 109 个动作。提示词目录比口头提到的 108 个多一条「是啊，吃什么」，本包也包含该条。

每段 640×360、60 fps、10 秒、600 帧。四个主要插画姿势经 RIFE v4.6 加密为中间姿势样本（常规动作 161 个），再结合连续呼吸、摆动及细分运动制作成片。使用 Remotion 4.0.534 编排、预览和编码。600 帧不等于 600 张重新绘制的插画；复杂动作仍为二维概括表现，过渡可能形变。

本次修复取消了旧版约 1.6 秒重复静帧和末尾突然复位。旧版保存在本机素材库「备份/30fps-2026-11-21」。RIFE 工具来源：https://github.com/nihui/rife-ncnn-vulkan 。

「绿幕MP4」供剪辑或绿幕软件使用，「透明WebM」供桌宠播放。「制作源文件」包含图集、姿势、提示词与 Remotion 代码。中间帧可在本机重建。manifest.json 记录规格、逐文件哈希和验证结果。

角色以原白龙娘为参考，经内置图像工具生成新插画，按用户要求独立命名。原角色来自本机 BailongPet 0.4.1，原素材清单声明未额外授予美术素材商用或再分发许可。

在 DSH 白龙右键「切换角色 → 雏龙娘」进入，「播放动作（全部素材）」可选动作。睡觉开始会接入循环，选睡觉起来即可唤醒。
'''


def copy_verified(source, target, previous=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = sha256(source.read_bytes()).hexdigest()
    if target.exists() and sha256(target.read_bytes()).hexdigest() != fingerprint:
        if previous is not None and sha256(target.read_bytes()).hexdigest() != previous:
            raise RuntimeError(f'Unexpected modified video needs review: {target}')
        # Preserve even hand-edited source files before replacing this generated character.
        for number, role in enumerate(ROLE_ROOTS):
            if target.is_relative_to(role):
                backup = BACKUP / f'plugin-{number}' / target.relative_to(role)
                break
        else:
            backup = BACKUP / (target.relative_to(LIBRARY) if target.is_relative_to(LIBRARY) else Path('repository') / target.relative_to(WORKSPACE))
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(target, backup)
        else:
            assert sha256(backup.read_bytes()).hexdigest() == sha256(target.read_bytes()).hexdigest(), backup
        temporary = target.with_name(target.name + '.updating')
        shutil.copy2(source, temporary)
        temporary.replace(target)
    elif not target.exists():
        shutil.copy2(source, target)
    if sha256(target.read_bytes()).hexdigest() != fingerprint:
        raise RuntimeError(f'Copy verification failed: {target}')


def main():
    report = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    assert len(report) == 109 and all('webm' in item for item in report)
    assert all(item['fps'] == CONFIG['fps'] and item['frames'] == CONFIG['fps'] * CONFIG['durationSeconds'] for item in report)
    old = {row['name']: row for row in json.loads((ROOT / 'out-chulong/manifest.json').read_text(encoding='utf-8'))}
    # Reject source damage or unexpected user edits before replacing even one video.
    for row in report:
        expected_old = old[row['name']]
        mp4, webm = OUT / row['file'], OUT / 'transparent' / row['webm']['file']
        assert sha256(mp4.read_bytes()).hexdigest() == row['sha256']
        assert sha256(webm.read_bytes()).hexdigest() == row['webm']['sha256']
        destinations = [(LIBRARY / '绿幕MP4' / mp4.name, expected_old['sha256'], row['sha256']),
                        (WORKSPACE / 'materials/雏龙娘/绿幕MP4' / mp4.name, expected_old['sha256'], row['sha256']),
                        (LIBRARY / '透明WebM' / webm.name, expected_old['webm']['sha256'], row['webm']['sha256'])]
        destinations.extend((role / 'videos' / webm.name, expected_old['webm']['sha256'], row['webm']['sha256']) for role in ROLE_ROOTS)
        for target, previous, current in destinations:
            if target.exists():
                assert sha256(target.read_bytes()).hexdigest() in (previous, current), f'Unexpected modified video: {target}'
    for row in report:
        mp4, webm = OUT / row['file'], OUT / 'transparent' / row['webm']['file']
        assert sha256(mp4.read_bytes()).hexdigest() == row['sha256']
        assert sha256(webm.read_bytes()).hexdigest() == row['webm']['sha256']
        copy_verified(mp4, LIBRARY / '绿幕MP4' / mp4.name, old[row['name']]['sha256'])
        copy_verified(mp4, WORKSPACE / 'materials/雏龙娘/绿幕MP4' / mp4.name, old[row['name']]['sha256'])
        copy_verified(webm, LIBRARY / '透明WebM' / webm.name, old[row['name']]['webm']['sha256'])
        for role in ROLE_ROOTS:
            copy_verified(webm, role / 'videos' / webm.name, old[row['name']]['webm']['sha256'])
    for name in ('manifest.json', '动作总览.jpg', 'playback-report.json', 'continuity-comparison.json'):
        copy_verified(OUT / name, LIBRARY / name)
        copy_verified(OUT / name, WORKSPACE / 'materials/雏龙娘' / name)
    sources = ['package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'requirements.txt', 'README.md', 'actions.json', 'all-prompts.json', 'atlas-prompts.json',
               'prepare.py', 'flow.py', 'bake.py', 'timing.py', 'build_smooth.py', 'neural_frames.py', 'composite.py',
               'render.mjs', 'stitch.mjs', 'transparent.py', 'test_motion_continuity.py',
               'verify.py', 'verify_alpha.py', '.gitignore', 'src/index.tsx', 'src/actions.json', 'src/safe-actions.json', 'src/render-config.json']
    for name in sources:
        copy_verified(ROOT / name, LIBRARY / '制作源文件' / name)
    for atlas in (ROOT / 'public').glob('atlas-*.png'):
        copy_verified(atlas, LIBRARY / '制作源文件/public' / atlas.name)
    for pose in (ROOT / 'public/poses').glob('*.png'):
        copy_verified(pose, LIBRARY / '制作源文件/public/poses' / pose.name)
    description_source = OUT / 'ASSETS.md'
    description_source.write_text(DESCRIPTION, encoding='utf-8')
    for place in [LIBRARY, *ROLE_ROOTS, WORKSPACE / 'materials/雏龙娘']:
        copy_verified(description_source, place / 'ASSETS.md')
    for role in ROLE_ROOTS:
        copy_verified(OUT / 'manifest.json', role / 'manifest.json')
    print(f'Published 109 green MP4s, 109 transparent WebMs and source artwork to {LIBRARY}')
    print('Verified all three DSH role installations.')


if __name__ == '__main__':
    main()
