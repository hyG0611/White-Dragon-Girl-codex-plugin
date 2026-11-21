"""Copy the verified character to the named material library and DSH plugin installations."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out-chulong'
WORKSPACE = ROOT.parent
LIBRARY = Path(r'D:\Desktop\素材库\雏龙娘')
ROLE_ROOTS = [WORKSPACE / 'codex-adapter/plugins/dsh-dragon/assets/characters/雏龙娘',
              Path(r'D:\Desktop\ds-pet\dsh-pet\codex-adapter\plugins\dsh-dragon\assets\characters\雏龙娘'),
              Path(r'C:\Users\admin\.codex\plugins\cache\dsh-dragon-local\dsh-dragon\1.0.0\assets\characters\雏龙娘')]

DESCRIPTION = '''# 雏龙娘

独立桌宠角色，按 DSH 提示词库完整制作 109 个动作。提示词目录比口头提到的 108 个多一条「是啊，吃什么」，本包也包含该条。

每段 640×360、30 fps、10 秒。新插画关键姿势经过双向光流补间，使用 Remotion 4.0.534 编排、预览和图像序列编码。复杂动作采用二维概括表现，部分姿势过渡可能有插画补间的形变。

「绿幕MP4」供剪辑或绿幕软件使用，「透明WebM」供桌宠播放。「制作源文件」包含图集、姿势、提示词与 Remotion 代码。中间帧可在本机重建。manifest.json 记录规格、逐文件哈希和验证结果。

角色以原白龙娘为参考，经内置图像工具生成新插画，按用户要求独立命名。原角色来自本机 BailongPet 0.4.1，原素材清单声明未额外授予美术素材商用或再分发许可。

在 DSH 白龙右键「切换角色 → 雏龙娘」进入，「播放动作（全部素材）」可选动作。睡觉开始会接入循环，选睡觉起来即可唤醒。
'''


def copy_verified(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = sha256(source.read_bytes()).hexdigest()
    if target.exists() and sha256(target.read_bytes()).hexdigest() != fingerprint:
        raise RuntimeError(f'Existing different file needs review: {target}')
    if not target.exists():
        shutil.copy2(source, target)
    if sha256(target.read_bytes()).hexdigest() != fingerprint:
        raise RuntimeError(f'Copy verification failed: {target}')


def main():
    report = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    assert len(report) == 109 and all('webm' in item for item in report)
    for row in report:
        mp4, webm = OUT / row['file'], OUT / 'transparent' / row['webm']['file']
        assert sha256(mp4.read_bytes()).hexdigest() == row['sha256']
        assert sha256(webm.read_bytes()).hexdigest() == row['webm']['sha256']
        copy_verified(mp4, LIBRARY / '绿幕MP4' / mp4.name)
        copy_verified(webm, LIBRARY / '透明WebM' / webm.name)
        for role in ROLE_ROOTS:
            copy_verified(webm, role / 'videos' / webm.name)
    for name in ('manifest.json', '动作总览.jpg'):
        copy_verified(OUT / name, LIBRARY / name)
    sources = ['package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'requirements.txt', 'README.md', 'actions.json', 'all-prompts.json', 'atlas-prompts.json',
               'prepare.py', 'flow.py', 'bake.py', 'composite.py', 'render.mjs', 'stitch.mjs', 'transparent.py',
               'verify.py', 'verify_alpha.py', '.gitignore', 'src/index.tsx', 'src/actions.json', 'src/safe-actions.json']
    for name in sources:
        copy_verified(ROOT / name, LIBRARY / '制作源文件' / name)
    for atlas in (ROOT / 'public').glob('atlas-*.png'):
        copy_verified(atlas, LIBRARY / '制作源文件/public' / atlas.name)
    for pose in (ROOT / 'public/poses').glob('*.png'):
        copy_verified(pose, LIBRARY / '制作源文件/public/poses' / pose.name)
    for place in [LIBRARY, *ROLE_ROOTS]:
        (place / 'ASSETS.md').write_text(DESCRIPTION, encoding='utf-8')
    for role in ROLE_ROOTS:
        copy_verified(OUT / 'manifest.json', role / 'manifest.json')
    print(f'Published 109 green MP4s, 109 transparent WebMs and source artwork to {LIBRARY}')
    print('Verified all three DSH role installations.')


if __name__ == '__main__':
    main()
