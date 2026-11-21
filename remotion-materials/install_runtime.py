"""Install the reviewed decoder changes with backups and select the new character."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
from PySide6.QtCore import QSettings

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'codex-adapter/plugins/dsh-dragon/runtime'
TARGETS = [Path(r'D:\Desktop\ds-pet\dsh-pet\codex-adapter\plugins\dsh-dragon\runtime'),
           Path(r'C:\Users\admin\.codex\plugins\cache\dsh-dragon-local\dsh-dragon\1.0.0\runtime')]
EXPECTED = {'pet.py': '1ddcaecf52545a260449e278666e6c928dece403f0d88a145b553d53e1d005ae',
            'media.py': '872fc625912e61cad81ef055780ff42799eafbc41462c0c09c08f91ff3e33352'}
BACKUP = ROOT.parent / '.runtime/chulong-install-backup-20261121'


def main():
    for target in TARGETS:
        for name, expected in EXPECTED.items():
            actual = sha256((target / name).read_bytes()).hexdigest()
            assert actual in (expected, sha256((SOURCE / name).read_bytes()).hexdigest()), (target, name, actual)
    BACKUP.mkdir(exist_ok=True)
    settings = QSettings('DSH Dragon', 'Codex Material Pet')
    settings_backup = BACKUP / 'previous-role.json'
    if not settings_backup.exists():
        settings_backup.write_text(json.dumps({'role': settings.value('role', '默认白龙')}, ensure_ascii=False), encoding='utf-8')
    for number, target in enumerate(TARGETS):
        folder = BACKUP / str(number)
        folder.mkdir(exist_ok=True)
        for name in EXPECTED:
            if not (folder / name).exists():
                shutil.copy2(target / name, folder / name)
            shutil.copy2(SOURCE / name, target / name)
            assert sha256((target / name).read_bytes()).digest() == sha256((SOURCE / name).read_bytes()).digest()
        assert len(list((target.parent / 'assets/characters/雏龙娘/videos').glob('*.webm'))) == 109
    settings.setValue('role', '雏龙娘')
    settings.sync()
    assert settings.status() == QSettings.NoError, settings.status()
    print('Both plugin installations updated; selected 雏龙娘. Previous files and role backed up.')


if __name__ == '__main__':
    main()
