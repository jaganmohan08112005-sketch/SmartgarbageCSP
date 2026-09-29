#!/usr/bin/env python3
"""Fine-tune MobileNetV3-Small for garbage vs. non-garbage → ONNX.

Consumes the dataset produced by scripts/fetch_photo_dataset.py
(_dataset/{train,val}/{garbage,non_garbage}/), fine-tunes the ImageNet
pretrained backbone with a two-logit head, evaluates, then exports:

    app/photo_classifier.onnx       NCHW float32 [1,3,H,W], ImageNet
                                    normalisation, static input size
    app/photo_classifier.onnx.json  label sidecar:
                                    {"labels": [...], "reject_label": ...}

The runtime hook (app/routes/__init__.py::_ai_verify_photo) reads the
sidecar, picks the reject label (non/clean/not), applies
PHOTO_CLASSIFIER_THRESHOLD on that class's softmax probability and fails
open on any error — so the exported contract here must match it.
"""
import argparse
import json
import random
import shutil
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
CLASSES = ['garbage', 'non_garbage']  # index 0 = garbage (accept), 1 = reject


def build_loaders(data_dir: Path, size: int, batch: int):
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(size, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.2, 0.2, 0.2),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    # Val/eval transform MUST match the runtime contract (direct resize to
    # the model input — see _classify_garbage_photo). The previous
    # Resize(256)+CenterCrop(224) inflated offline val_acc (~+6 pts) relative
    # to what production actually scores.
    val_tf = transforms.Compose([
        transforms.Resize((size, size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    train_ds = datasets.ImageFolder(str(data_dir / 'train'), transform=train_tf)
    val_ds = datasets.ImageFolder(str(data_dir / 'val'), transform=val_tf)
    # ImageFolder sorts class dirs alphabetically: garbage < non_garbage →
    # class_to_idx = {'garbage': 0, 'non_garbage': 1} = CLASSES. Assert it.
    assert train_ds.class_to_idx == {'garbage': 0, 'non_garbage': 1}, train_ds.class_to_idx
    train_loader = DataLoader(train_ds, batch_size=batch, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader = DataLoader(val_ds, batch_size=batch, shuffle=False, num_workers=0)
    return train_loader, val_loader


def evaluate(model, loader, device):
    model.eval()
    correct = total = 0
    tp = fp = fn = 0  # positive = garbage
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            pred = model(x).argmax(1)
            correct += (pred == y).sum().item()
            total += y.numel()
            tp += ((pred == 0) & (y == 0)).sum().item()
            fp += ((pred == 0) & (y == 1)).sum().item()
            fn += ((pred == 1) & (y == 0)).sum().item()
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return correct / max(total, 1), precision, recall


def export_onnx(model, size: int, out: Path):
    model.eval()
    dummy = torch.randn(1, 3, size, size)
    torch.onnx.export(
        model, dummy, str(out), input_names=['input'], output_names=['logits'],
        dynamic_axes=None,  # static shape: matches the runtime's resize contract
        opset_version=13,
        do_constant_folding=True,
    )
    # torch ≥2.14 writes weights >1 KB as an external '.onnx.data' sibling;
    # inline them so the runtime hook and the Docker image see ONE file.
    data_file = out.with_suffix('.onnx.data') if out.suffix == '.onnx' else out.with_suffix('.data')
    if data_file.exists():
        import onnx
        proto = onnx.load(str(out), load_external_data=True)
        onnx.save(proto, str(out))  # single-file model, tensors embedded
        data_file.unlink()
    labels = {'labels': CLASSES, 'reject_label': 'non_garbage',
              'input_size': size,
              'preprocess': {'resize': size, 'mean': IMAGENET_MEAN, 'std': IMAGENET_STD},
              'trained_on': 'TrashNet (garbage) + COCO val2017 + Wikimedia '
                            'hard negatives: Landfills/Dumpsters/Streets/Roads/'
                            'Parks as non_garbage (dump-yard + clean-scene), '
                            'MobileNetV3-Small'}
    out.with_suffix('.onnx.json').write_text(json.dumps(labels, indent=2), encoding='utf-8')


def oversample_hard_negatives(data_dir: Path, copies: int):
    """Duplicate hard-negative train files (dumpyard_/dumpster_/street_/
    road_/park_/streetin_/roadin_ prefixes) `copies` extra times so the
    small hard-negative set carries real weight against ~2k COCO scenes.
    Deterministic, filesystem-level, and self-cleaning on the next fetch
    (dup files are named <stem>__dup<k>.jpg)."""
    train_dir = data_dir / 'train' / 'non_garbage'
    n = 0
    for f in sorted(train_dir.iterdir()):
        if not f.name.endswith('.jpg') or '__dup' in f.name:
            continue
        if not f.name.startswith(('dumpyard_', 'dumpster_', 'street_',
                                  'road_', 'park_', 'streetin_', 'roadin_')):
            continue
        for k in range(1, copies + 1):
            dst = train_dir / f'{f.stem}__dup{k}.jpg'
            if not dst.exists():
                shutil.copyfile(f, dst)
            n += 1
    print(f'[oversample] +{n} hard-negative copies (x{copies + 1} effective)')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data', default=str(ROOT / '_dataset'))
    ap.add_argument('--size', type=int, default=224)
    ap.add_argument('--epochs', type=int, default=3)
    ap.add_argument('--batch', type=int, default=32)
    ap.add_argument('--out', default=str(ROOT / 'app' / 'photo_classifier.onnx'))
    ap.add_argument('--export-only', action='store_true',
                    help='re-export ONNX from the saved .pt checkpoint (no training)')
    ap.add_argument('--hard-neg-oversample', type=int, default=0,
                    help='duplicate hard-negative train files N extra times '
                         'before training (they are scarce by design)')
    args = ap.parse_args()

    data_dir = Path(args.data)
    if not args.export_only and not (data_dir / 'train' / 'garbage').exists():
        raise SystemExit(f'no dataset at {data_dir}; run scripts/fetch_photo_dataset.py first')

    device = torch.device('cpu')
    torch.manual_seed(42)
    random.seed(42)

    if args.hard_neg_oversample > 0:
        oversample_hard_negatives(data_dir, args.hard_neg_oversample)
    train_loader, val_loader = build_loaders(data_dir, args.size, args.batch)
    print(f'[data] train={len(train_loader.dataset)} val={len(val_loader.dataset)}')

    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 2)
    model.to(device)

    crit = nn.CrossEntropyLoss()
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)

    out = Path(args.out)
    ckpt = out.with_suffix('.pt')
    if ckpt.exists() and args.export_only:
        model.load_state_dict(torch.load(ckpt, map_location='cpu'))
        print(f'[resume] loaded {ckpt}')
    else:
        best_acc = 0.0
        for epoch in range(args.epochs):
            model.train()
            t0, running = time.time(), 0.0
            for i, (x, y) in enumerate(train_loader):
                opt.zero_grad()
                loss = crit(model(x), y)
                loss.backward()
                opt.step()
                running += loss.item()
                if i % 20 == 0:
                    print(f'[ep{epoch}] {i}/{len(train_loader)} loss={loss.item():.3f}', flush=True)
            acc, prec, rec = evaluate(model, val_loader, device)
            best_acc = max(best_acc, acc)
            print(f'[ep{epoch}] train_loss={running / max(len(train_loader), 1):.3f} '
                  f'val_acc={acc:.3f} garbage_p={prec:.3f} garbage_r={rec:.3f} '
                  f'({time.time() - t0:.0f}s)', flush=True)
        torch.save(model.state_dict(), ckpt)

    export_onnx(model, args.size, out)
    print(f'[export] {out}')
    print('OK best_val_acc={:.3f}'.format(
        best_acc if 'best_acc' in dir() else 0.0))


if __name__ == '__main__':
    sys.exit(main())
