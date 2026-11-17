"""Read-only, bounded views of one media directory at a time."""
import math
import os
import json

from echoview.utils import is_ignored_folder, media_aspect_label

PAGE_SIZE = 48
SORTS = ('name_asc', 'name_desc', 'date_asc', 'date_desc')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.gif')
MEDIA_EXT = IMAGE_EXT + ('.mp4', '.mov', '.avi', '.mkv', '.webm')


def parse_folder_order(value):
    """Use JSON for comma-containing names, accepting older controller forms."""
    try:
        folders = json.loads(value) if value.lstrip().startswith('[') else value.split(',')
    except (TypeError, ValueError):
        raise ValueError('Invalid mixed-folder selection.') from None
    if not isinstance(folders, list) or any(not isinstance(folder, str) for folder in folders):
        raise ValueError('Invalid mixed-folder selection.')
    return [folder for folder in folders if folder and not is_ignored_folder(folder)]


def resolve_folder(root, folder=''):
    # Folder selectors refer only to the root or its immediate children.
    if folder and (folder in ('.', '..') or '/' in folder or '\\' in folder or is_ignored_folder(folder)):
        raise ValueError('Invalid media folder.')
    root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, folder))
    if os.path.commonpath((root, path)) != root:
        raise ValueError('Invalid media folder.')
    return path


def resolve_file(root, folder, filename):
    path = resolve_folder(root, folder)
    if not filename or filename in ('.', '..') or '/' in filename or '\\' in filename:
        raise ValueError('Invalid media filename.')
    candidate = os.path.realpath(os.path.join(path, filename))
    if os.path.commonpath((path, candidate)) != path:
        raise ValueError('Invalid media filename.')
    if not filename.lower().endswith(MEDIA_EXT):
        raise ValueError('Unsupported media type.')
    if not os.path.isfile(candidate):
        raise FileNotFoundError('Media file is no longer available.')
    return candidate


def folder_page(root, folder='', sort='name_asc', page=1, query='', images=False, aspect='any'):
    path = resolve_folder(root, folder)
    sort = sort if sort in SORTS else 'name_asc'
    query = query[:256]
    needle = query.casefold()
    files = []
    with os.scandir(path) as entries:
        for entry in entries:
            if not entry.name.lower().endswith(IMAGE_EXT if images else MEDIA_EXT):
                continue
            if needle not in entry.name.casefold() or not entry.is_file(follow_symlinks=False):
                continue
            try:
                if images and aspect in ('square', 'landscape', 'portrait'):
                    if media_aspect_label(entry.path) != aspect:
                        continue
                modified = entry.stat().st_mtime_ns if sort.startswith('date') else 0
            except OSError:
                continue  # A file may disappear during a NAS directory scan.
            files.append((entry.name, modified))
    files.sort(key=lambda item: (item[1], item[0].casefold(), item[0]), reverse=sort.endswith('desc'))
    total = len(files)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, pages))
    return dict(files=[name for name, _ in files[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]],
                total=total, page=page, pages=pages, query=query, sort=sort, folder=folder)
