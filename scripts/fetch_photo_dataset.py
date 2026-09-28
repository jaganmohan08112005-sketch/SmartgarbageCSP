#!/usr/bin/env python3
"""Fetch + prepare the labelled garbage / non-garbage photo dataset.

Layout produced under --out (default: _dataset/, git-ignored):
    train/garbage/*.jpg        train/non_garbage/*.jpg
    val/garbage/*.jpg          val/non_garbage/*.jpg

Sources
-------
garbage     TrashNet via kagglehub ('techsash/waste-classification-data',
            25k ORGANIC/RECYCLABLE photos — both are waste). Fallback:
            Wikimedia Commons 'Litter' category via the public API.
non_garbage COCO val2017 (photorealistic everyday scenes: streets, parks,
            people, food, animals — no waste focus), capped.

Balance and split are deterministic; images are validated with Pillow
(min 48 px, decodable) and re-encoded as JPEG so the training folder is
uniform. Roughly 2,000 images per class trains a binary head in minutes
on CPU; raise --per-class for more.
"""
import argparse
import json
import random
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

VALID_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def _valid_image(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            return min(img.size) >= 48
    except Exception:
        return False


def _save_jpeg(src: Path, dst: Path) -> bool:
    try:
        with Image.open(src) as img:
            img.convert('RGB').save(dst, 'JPEG', quality=88)
        return True
    except Exception:
        return False


# ── Garbage: TrashNet via kagglehub, Wikimedia fallback ────────────────
TRASHNET_CLASS_DIRS = {'O', 'R', 'ORGANIC', 'RECYCLABLE'}


def fetch_trashnet(out_dir: Path, cap: int):
    import kagglehub
    base = Path(kagglehub.dataset_download('techsash/waste-classification-data'))
    # The dataset nests class folders as DATASET/{TRAIN,TEST}/{O,R} — accept
    # both the short and long spellings.
    roots = [p for p in base.rglob('*')
             if p.is_dir() and p.name.upper() in TRASHNET_CLASS_DIRS]
    if not roots:
        raise RuntimeError(f'TrashNet layout not recognised under {base}')
    files = []
    for root in roots:
        files.extend(p for p in root.iterdir() if p.suffix.lower() in VALID_EXT)
    random.Random(42).shuffle(files)
    n = 0
    for f in files:
        if n >= cap:
            break
        if _save_jpeg(f, out_dir / f'trash_{n:05d}.jpg'):
            n += 1
    return n


def fetch_wikimedia_litter(out_dir: Path, cap: int):
    """Fallback: commons category 'Litter' via the public API (no key)."""
    api = ('https://commons.wikimedia.org/w/api.php?action=query&generator=categorymembers'
           '&gcmtitle=Category:Litter&gcmtype=file&gcmlimit=500&prop=imageinfo&iiprop=url'
           '&iiurlwidth=1024&format=json')
    req = urllib.request.Request(api, headers={'User-Agent': 'SmartGarbage-dataset/1.0'})
    data = __import__('json').loads(urllib.request.urlopen(req, timeout=30).read())
    pages = data.get('query', {}).get('pages', {})
    urls = [pg['imageinfo'][0].get('thumburl') or pg['imageinfo'][0]['url']
            for pg in pages.values() if pg.get('imageinfo')]
    random.Random(42).shuffle(urls)
    n = 0
    for url in urls:
        if n >= cap:
            break
        try:
            blob = urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': 'SmartGarbage-dataset/1.0'}),
                timeout=30).read()
            src = out_dir / f'wiki_{n:05d}.jpg'
            src.write_bytes(blob)
            if _valid_image(src):
                with Image.open(src) as img:
                    img.convert('RGB').save(out_dir / f'trash_{n:05d}.jpg', 'JPEG', quality=88)
                src.unlink()
                n += 1
            else:
                src.unlink()
        except Exception:
            continue
    return n


# ── Non-garbage: COCO val2017 ──────────────────────────────────────────
def fetch_coco(out_dir: Path, cap: int, tmp: Path):
    zip_path = tmp / 'val2017.zip'
    if not zip_path.exists():
        print('[coco] downloading val2017 (~778 MB, one-time)...')
        urllib.request.urlretrieve('http://images.cocodataset.org/zips/val2017.zip', zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist()
                 if n.lower().endswith(('.jpg', '.png')) and not n.endswith('/')]
        random.Random(42).shuffle(names)
        n = 0
        for name in names:
            if n >= cap:
                break
            dst = out_dir / f'coco_{n:05d}.jpg'
            with zf.open(name) as src, open(dst, 'wb') as fh:
                fh.write(src.read())
            if _valid_image(dst) and _save_jpeg(dst, dst.with_suffix('.tmp.jpg')):
                dst.with_suffix('.tmp.jpg').replace(dst)
                n += 1
            else:
                dst.unlink(missing_ok=True)
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--per-class', type=int, default=2000)
    ap.add_argument('--out', default=str(Path(__file__).resolve().parent.parent / '_dataset'))
    ap.add_argument('--val-frac', type=float, default=0.1)
    ap.add_argument('--skip-coco-download', action='store_true',
                    help='reuse an existing val2017.zip in the system temp dir')
    args = ap.parse_args()

    out = Path(args.out)
    tmp = Path(__import__('tempfile').gettempdir())
    tmp.mkdir(exist_ok=True)
    for cls in ('garbage', 'non_garbage'):
        (out / 'train' / cls).mkdir(parents=True, exist_ok=True)
        (out / 'val' / cls).mkdir(parents=True, exist_ok=True)

    counts = {}
    print('[garbage] fetching TrashNet...')
    try:
        counts['garbage'] = fetch_trashnet(out / 'train' / 'garbage', args.per_class)
    except Exception as exc:
        print(f'[garbage] kagglehub failed ({exc}); falling back to Wikimedia Commons')
        counts['garbage'] = fetch_wikimedia_litter(out / 'train' / 'garbage', args.per_class)
    print(f'[garbage] {counts["garbage"]} images')

    print('[non_garbage] fetching COCO val2017...')
    counts['non_garbage'] = fetch_coco(out / 'train' / 'non_garbage',
                                       args.per_class, tmp)
    print(f'[non_garbage] {counts["non_garbage"]} images')

    # Deterministic train/val split (move the tail 10% of each class).
    rng = random.Random(42)
    for cls in ('garbage', 'non_garbage'):
        files = sorted((out / 'train' / cls).glob('*.jpg'))
        rng.shuffle(files)
        n_val = max(1, int(len(files) * args.val_frac))
        for f in files[:n_val]:
            f.rename(out / 'val' / cls / f.name)
        print(f'[split] {cls}: train={len(files) - n_val} val={n_val}')

    print('OK dataset ready at', out.resolve())


if __name__ == '__main__':
    main()
