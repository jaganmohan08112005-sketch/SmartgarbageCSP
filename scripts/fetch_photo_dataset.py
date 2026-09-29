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
import urllib.parse
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


# ── Wikimedia Commons (generic, with continuation paging) ──────────────
def _commons_category_urls(category: str, pool: int):
    """Return up to `pool` image URLs from a Commons category, paging through
    gcmcontinue so categories bigger than the 500-per-page cap still yield."""
    api = ('https://commons.wikimedia.org/w/api.php?action=query&generator=categorymembers'
           f'&gcmtitle=Category:{urllib.parse.quote(category)}&gcmtype=file&gcmlimit=500'
           '&prop=imageinfo&iiprop=url&iiurlwidth=1024&format=json')
    urls, cont = [], None
    while len(urls) < pool:
        url = api + (f'&gcmcontinue={urllib.parse.quote(cont)}' if cont else '')
        req = urllib.request.Request(url, headers={'User-Agent': 'SmartGarbage-dataset/1.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        pages = data.get('query', {}).get('pages', {})
        urls += [pg['imageinfo'][0].get('thumburl') or pg['imageinfo'][0]['url']
                 for pg in pages.values() if pg.get('imageinfo')]
        cont = data.get('continue', {}).get('gcmcontinue')
        if not cont:
            break
    random.Random(42).shuffle(urls)
    return urls


def fetch_wikimedia_category(dataset_root: Path, category: str, prefix: str,
                             cap: int, val_frac: float = 0.15):
    """Download up to `cap` validated images from one Commons category into
    the NON_GARBAGE class (train gets 1-val_frac, val the rest, deterministic
    by index). Used for hard negatives — see HARD_NEGATIVE_SOURCES."""
    train_dir = dataset_root / 'train' / 'non_garbage'
    val_dir = dataset_root / 'val' / 'non_garbage'
    n = 0
    for url in _commons_category_urls(category, pool=4 * cap):
        if n >= cap:
            break
        tmp = train_dir / f'_{prefix}_tmp.jpg'
        try:
            blob = urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': 'SmartGarbage-dataset/1.0'}),
                timeout=30).read()
            tmp.write_bytes(blob)
            if not _valid_image(tmp):
                continue
            # Deterministic split: the first val_frac slice of every 100 goes to val.
            dst_dir = val_dir if (n % 100) < int(val_frac * 100) else train_dir
            with Image.open(tmp) as img:
                img.convert('RGB').save(dst_dir / f'{prefix}_{n:05d}.jpg', 'JPEG', quality=88)
            n += 1
        except Exception:
            continue
        finally:
            tmp.unlink(missing_ok=True)
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


# ── Hard negatives: scenes the gate must ACCEPT but the base data under- ─
# represents. Production false positives were dominated by photos taken at
# dump yards / municipal sites (waste is EXPECTED there) and by ordinary
# street scenes, so those domains are added as extra non_garbage examples.
HARD_NEGATIVE_SOURCES = [
    # (Commons category, filename prefix)
    ('Landfills', 'dumpyard'),
    ('Dumpsters', 'dumpster'),
    ('Streets', 'street'),
    ('Roads', 'road'),
    ('Parks', 'park'),
    # Bigger photographic pools for the clean-scene negatives.
    ('Streets in India', 'streetin'),
    ('Roads in India', 'roadin'),
]


def fetch_hard_negatives(out: Path, per_source: int):
    """Add dump-yard + clean-scene photos as extra non_garbage examples
    (hard negatives the classifier must learn to ACCEPT)."""
    counts = {}
    for category, prefix in HARD_NEGATIVE_SOURCES:
        n = fetch_wikimedia_category(out, category, prefix, per_source)
        counts[category] = n
        print(f'[hard-neg] {category}: {n} images', flush=True)
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--per-class', type=int, default=2000)
    ap.add_argument('--out', default=str(Path(__file__).resolve().parent.parent / '_dataset'))
    ap.add_argument('--val-frac', type=float, default=0.1)
    ap.add_argument('--skip-coco-download', action='store_true',
                    help='reuse an existing val2017.zip in the system temp dir')
    ap.add_argument('--hard-negatives', type=int, default=0,
                    help='also fetch N dump-yard / clean-scene photos per source '
                         'into non_garbage (hard negatives the gate must accept)')
    ap.add_argument('--skip-sources', action='store_true',
                    help='skip TrashNet/COCO fetch and the train/val split — only '
                         'run --hard-negatives against an existing dataset')
    args = ap.parse_args()

    out = Path(args.out)
    tmp = Path(__import__('tempfile').gettempdir())
    tmp.mkdir(exist_ok=True)
    for cls in ('garbage', 'non_garbage'):
        (out / 'train' / cls).mkdir(parents=True, exist_ok=True)
        (out / 'val' / cls).mkdir(parents=True, exist_ok=True)

    if not args.skip_sources:
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

    if args.hard_negatives > 0:
        print(f'[hard-neg] fetching {args.hard_negatives}/source into non_garbage...')
        fetch_hard_negatives(out, args.hard_negatives)

    print('OK dataset ready at', out.resolve())


if __name__ == '__main__':
    main()
