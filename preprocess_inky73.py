#!/usr/bin/env python3
"""
Inky Impression 7.3\"(800x480) 用 画像プリプロセススクリプト

- 入力ディレクトリ内の JPEG / PNG を読み込み
- 800x480 に合わせてリサイズ＆センタークロップ
- 出力ディレクトリに保存
- JPEG の場合は EXIF（日付など）を可能な範囲で維持

使い方例:
    python3 preprocess_inky73.py \
        --input ./photos_raw \
        --output ./photos_inky73
"""

import os
import argparse
from pathlib import Path

from PIL import Image, ImageOps

# Inky Impression 7.3" の解像度
TARGET_WIDTH = 800
TARGET_HEIGHT = 480

# 対象とする拡張子
VALID_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}


def auto_orient(img: Image.Image) -> Image.Image:
    """
    EXIF の Orientation に従って画像を回転・反転する。
    Pillow の ImageOps.exif_transpose を利用。
    """
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def resize_and_crop_to_panel(img: Image.Image) -> Image.Image:
    """
    画像をパネル解像度(800x480)に合わせてリサイズ＆センタークロップする。

    - アスペクト比を維持しつつ、「短い辺」がちょうど収まるように拡大/縮小
    - はみ出た長い辺を中央でトリミング
    """
    # 最終的なキャンバスサイズ
    target_w, target_h = TARGET_WIDTH, TARGET_HEIGHT

    # 元画像のサイズ
    src_w, src_h = img.size
    if src_w == 0 or src_h == 0:
        raise ValueError("画像のサイズが 0 です")

    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    # リサイズ後の仮サイズを計算
    if src_ratio > target_ratio:
        # 横長すぎる → 高さを基準に拡大/縮小
        new_h = target_h
        new_w = int(new_h * src_ratio)
    else:
        # 縦長 (またはほぼ同じ) → 幅を基準に拡大/縮小
        new_w = target_w
        new_h = int(new_w / src_ratio)

    # 高品質リサイズ
    img_resized = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

    # 中央で 800x480 にトリミング
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    right = left + target_w
    bottom = top + target_h

    img_cropped = img_resized.crop((left, top, right, bottom))
    return img_cropped


def process_one_image(src_path: Path, dst_path: Path, overwrite: bool = False) -> None:
    """
    1枚の画像を読み込んで 800x480 に変換して保存。
    JPEG の場合は EXIF を可能な範囲で維持。
    """
    if not overwrite and dst_path.exists():
        print(f"  [skip] {dst_path} (すでに存在)")
        return

    try:
        with Image.open(src_path) as im:
            im = auto_orient(im)
            im = im.convert("RGB")  # Inky は基本 RGB 扱い

            # EXIF を取得（JPEG のときのみ保存に使う）
            exif = im.getexif()
            exif_bytes = exif.tobytes() if exif else None

            out_img = resize_and_crop_to_panel(im)

            dst_path.parent.mkdir(parents=True, exist_ok=True)

            # 拡張子に応じて保存形式を決定（ここでは全部 JPEG でもよい）
            ext = src_path.suffix.lower()
            if ext in [".png"]:
                # PNG として保存（EXIF はほぼ期待できないので無視）
                out_img.save(dst_path.with_suffix(".png"))
            else:
                # JPEG として保存（EXIF を出来るだけ維持）
                if exif_bytes:
                    out_img.save(
                        dst_path.with_suffix(".jpg"),
                        format="JPEG",
                        quality=90,
                        optimize=True,
                        progressive=True,
                        exif=exif_bytes,
                    )
                else:
                    out_img.save(
                        dst_path.with_suffix(".jpg"),
                        format="JPEG",
                        quality=90,
                        optimize=True,
                        progressive=True,
                    )

        print(f"  [ok] {src_path.name} → {dst_path.name}")

    except Exception as e:
        print(f"  [error] {src_path}: {e}")


def walk_and_process(input_dir: Path, output_dir: Path, overwrite: bool = False) -> None:
    """
    input_dir 以下を再帰的にたどり、画像だけ output_dir に変換して保存。
    ディレクトリ構造はそのまま保つ。
    """
    files = [p for p in input_dir.rglob("*") if p.suffix in VALID_EXTS]

    if not files:
        print(f"入力ディレクトリ {input_dir} に画像が見つかりません。")
        return

    print(f"{len(files)} 枚の画像を変換します。")

    for src in sorted(files):
        # 入力ディレクトリからの相対パスを保ったまま保存先を決定
        rel = src.relative_to(input_dir)
        dst = output_dir / rel
        # 拡張子は中で付け直しているので、ここでは元のままでOK
        process_one_image(src, dst, overwrite=overwrite)


def main():
    parser = argparse.ArgumentParser(
        description="Inky Impression 7.3\"(800x480) 向け画像プリプロセッサ"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="元画像ディレクトリ（再帰的に探索）",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="変換後画像の出力ディレクトリ",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="出力ファイルが存在しても上書きする",
    )

    args = parser.parse_args()

    if not args.input.is_dir():
        print(f"入力ディレクトリが見つかりません: {args.input}")
        return

    args.output.mkdir(parents=True, exist_ok=True)

    print("=== Inky Impression 7.3\" 用 画像プリプロセス開始 ===")
    print(f"入力:  {args.input}")
    print(f"出力:  {args.output}")
    print(f"サイズ: {TARGET_WIDTH}x{TARGET_HEIGHT}")
    walk_and_process(args.input, args.output, overwrite=args.overwrite)
    print("=== 完了しました ===")


if __name__ == "__main__":
    main()
