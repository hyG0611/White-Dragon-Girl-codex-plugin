"""Collect MP4 and WebM assets from a local folder or ZIP into an import directory."""
from contextlib import nullcontext
from pathlib import Path, PurePosixPath, PureWindowsPath
import os
import re
import stat
from zipfile import ZipFile


VIDEO_TYPES = {'.mp4', '.webm'}
MAX_FILES = 256
MAX_BYTES = 512 * 1024 * 1024
CHUNK = 2 * 1024 * 1024


def validate_name(name):
    if (not name or name != name.strip() or name.startswith('.') or name.endswith('.') or len(name) > 80
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or PureWindowsPath(name).is_reserved()):
        raise ValueError('名称不符合 Windows 文件名规则，请使用不超过 80 字的名称。')
    return name


def role_actions(root):
    actions = {path.stem: path for path in sorted(root.rglob('*'))
               if path.is_file() and path.suffix.lower() in VIDEO_TYPES}
    idle = next((name for name in ('待机呼吸休闲', 'idle') if name in actions), None)
    if idle is None:
        idle = next((name for name, path in actions.items()
                     if name.casefold() == 'idle' or path.parent.name.casefold() == 'idle'), None)
    if idle is None:
        raise ValueError('角色包缺少待机动画。请放入 idle.mp4、idle.webm 或 idle 文件夹。')
    return actions, idle


def folder_items(root):
    for folder, dirs, names in os.walk(root):
        directory = Path(folder)
        dirs[:] = [name for name in dirs if (directory / name).resolve() == directory / name]
        for name in names:
            path = directory / name
            if path.suffix.lower() not in VIDEO_TYPES or path.is_symlink() or not path.is_file():
                continue
            yield path, path.relative_to(root), path.stat().st_size


def zip_items(archive):
    entries = archive.infolist()
    if len(entries) > 4096:
        raise ValueError('ZIP 条目过多，请将角色素材单独打包。')
    for item in entries:
        path = PurePosixPath(item.filename)
        if item.is_dir() or path.suffix.lower() not in VIDEO_TYPES:
            continue
        if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                or re.match(r'^[A-Za-z]:', item.filename) or stat.S_ISLNK(item.external_attr >> 16)):
            raise ValueError('ZIP 中包含不安全的动画路径。')
        yield item, path, item.file_size


def copy_role(source, destination, progress):
    """Copy into a private staging directory. Return False if the user cancels."""
    source = source.resolve()
    is_folder = source.is_dir()
    if not is_folder and source.stat().st_size > MAX_BYTES:
        raise ValueError('角色 ZIP 超过 512 MiB。')
    with (nullcontext() if is_folder else ZipFile(source)) as archive:
        candidates = folder_items(source) if is_folder else zip_items(archive)
        videos = []
        total = 0
        names = set()
        for item, relative, size in candidates:
            validate_name(relative.stem)
            key = relative.stem.casefold()
            if key in names:
                raise ValueError(f'角色包有重名动作：{relative.stem}。')
            names.add(key)
            total += size
            if len(names) > MAX_FILES or total > MAX_BYTES:
                raise ValueError('角色包最多 256 段动画，合计不能超过 512 MiB。')
            group = 'idle' if relative.parent.name.casefold() == 'idle' else 'videos'
            videos.append((item, destination / group / relative.name, size))
        if not videos:
            raise ValueError('没有找到 MP4 或 WebM 动画。')
        done = 0
        for item, target, expected in videos:
            if not progress(done, total):
                return False
            target.parent.mkdir(exist_ok=True)
            source_file = item.open('rb') if is_folder else archive.open(item)
            with source_file as original, target.open('xb') as output:
                while data := original.read(CHUNK):
                    expected -= len(data)
                    if expected < 0:
                        raise ValueError('素材在导入期间发生变化。')
                    output.write(data)
                    done += len(data)
                    if not progress(done, total):
                        return False
                if expected:
                    raise ValueError('素材不完整。')
    return True
