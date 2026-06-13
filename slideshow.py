#!/usr/bin/python3
"""
Pimoroni Inky Impression 7.3" Spectra 6 対応 スライドショー

分類:
  images/photo/ 配下 → 写真用: Floyd-Steinberg ディザリング
  images/art/   配下 → イラスト用: ディザリングなし
"""

import os
import time
import random
import logging
import json
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import piexif
from inky.auto import auto
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.expanduser("~/.cache/slideshow_state_spectra6.json")

CONFIG = {
    "PHOTO_DIR": os.path.join(SCRIPT_DIR, os.getenv("PHOTO_DIR", "images")),
    "FONT_PATH": os.getenv(
        "FONT_PATH",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    "INTERVAL_SECONDS": int(os.getenv("INTERVAL_SECONDS", 1800)),

    "FONT_SIZE": 14,
    "DATE_FONT_SIZE": 16,
    "DATE_POSITIONS": ["bottom-right", "top-right", "top-left", "bottom-left"],
    "MARGIN": 15,
    "BACKGROUND_PADDING": 10,
    "TEXT_PADDING": 8,

    "SATURATION": 0.5,
    "PHOTO_CONTRAST": 1.15,
    "ART_CONTRAST": 1.04,

    # Spectra 6
    "OUTPUT_COLORS": 6,
}


def setup_logging():
    log_dir = os.path.expanduser("~/.logs/slideshow_logs")
    os.makedirs(log_dir, exist_ok=True)

    try:
        os.chmod(log_dir, 0o700)
    except Exception:
        pass

    log_file = os.path.join(log_dir, "slideshow_spectra6.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )

    return logging.getLogger(__name__)


logger = setup_logging()


def save_state(queue, total_count):
    state = {
        "total_count": total_count,
        "queue": queue,
    }

    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

        logger.info(f"現在の状態を保存しました。残り: {len(queue)} / {total_count}枚")

    except Exception as e:
        logger.error(f"状態の保存に失敗しました: {e}")


def load_state():
    if not os.path.exists(STATE_FILE):
        return 0, []

    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)

        if isinstance(state, dict):
            count = state.get("total_count", 0)
            queue = state.get("queue", [])
            logger.info(f"前回の状態を読み込みました。残り: {len(queue)} / {count}枚")
            return count, queue

        logger.info("古い形式の状態ファイルを検出しました。リセットします。")
        return 0, []

    except Exception as e:
        logger.error(f"状態の読み込みに失敗しました: {e}")
        return 0, []


def detect_image_mode(image_path: str) -> str:
    """
    images/photo/ 配下 → photo
    images/art/   配下 → art

    どちらでもなければ photo 扱い。
    """
    normalized = os.path.normpath(image_path).lower()
    parts = normalized.split(os.sep)

    if "art" in parts:
        return "art"

    if "photo" in parts:
        return "photo"

    return "photo"


def collect_images():
    image_paths = []

    for root, dirs, files in os.walk(CONFIG["PHOTO_DIR"]):
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for filename in files:
            if filename.startswith("."):
                continue

            if filename.lower().endswith((".jpg", ".jpeg", ".png")):
                image_paths.append(os.path.join(root, filename))

    return image_paths


def extract_capture_date(image_path):
    if os.path.splitext(image_path)[1].lower() == ".png":
        return None

    try:
        exif_dict = piexif.load(image_path)
        date_str = exif_dict["Exif"].get(piexif.ExifIFD.DateTimeOriginal)

        if date_str:
            return datetime.strptime(
                date_str.decode("utf-8"),
                "%Y:%m:%d %H:%M:%S",
            )

    except Exception as e:
        logger.warning(f"EXIF取得エラー ({os.path.basename(image_path)}): {e}")

    return None


def format_date_and_elapsed_time(capture_date):
    if not capture_date:
        return "Unknown date", "Unknown date"

    formatted_date = capture_date.strftime("%Y-%m-%d")
    delta = datetime.now() - capture_date

    years = delta.days // 365
    if years > 0:
        elapsed = f"{years} year{'s' if years > 1 else ''} ago"
    else:
        months = delta.days // 30
        if months > 0:
            elapsed = f"{months} month{'s' if months > 1 else ''} ago"
        else:
            elapsed = "Within a month"

    return formatted_date, elapsed


def enhance_image(img, image_mode: str):
    if image_mode == "art":
        return ImageEnhance.Contrast(img).enhance(CONFIG["ART_CONTRAST"])

    return ImageEnhance.Contrast(img).enhance(CONFIG["PHOTO_CONTRAST"])


def add_date_overlay(img, capture_date):
    draw = ImageDraw.Draw(img, "RGBA")

    try:
        elapsed_font = ImageFont.truetype(CONFIG["FONT_PATH"], CONFIG["FONT_SIZE"])
        date_font = ImageFont.truetype(CONFIG["FONT_PATH"], CONFIG["DATE_FONT_SIZE"])
    except OSError:
        logger.warning("フォント読み込みに失敗したため、デフォルトフォントを使用します。")
        elapsed_font = date_font = ImageFont.load_default()

    formatted_date, elapsed_time = format_date_and_elapsed_time(capture_date)

    date_bbox = draw.textbbox((0, 0), formatted_date, font=date_font)
    elapsed_bbox = draw.textbbox((0, 0), elapsed_time, font=elapsed_font)

    max_width = max(date_bbox[2], elapsed_bbox[2])
    date_height = date_bbox[3] - date_bbox[1]
    elapsed_height = elapsed_bbox[3] - elapsed_bbox[1]
    total_height = date_height + elapsed_height + CONFIG["TEXT_PADDING"]

    margin = CONFIG["MARGIN"]
    padding = CONFIG["BACKGROUND_PADDING"]
    position = random.choice(CONFIG["DATE_POSITIONS"])

    x = img.width - max_width - margin - padding if "right" in position else margin + padding
    y = img.height - total_height - margin - padding if "bottom" in position else margin + padding

    draw.rectangle(
        (
            x - padding,
            y - padding,
            x + max_width + padding,
            y + total_height + padding,
        ),
        fill=(0, 0, 0, 128),
    )

    draw.text((x, y), formatted_date, fill="white", font=date_font)
    draw.text(
        (x, y + date_height + CONFIG["TEXT_PADDING"]),
        elapsed_time,
        fill="white",
        font=elapsed_font,
    )

    return img


def apply_epaper_quantize(img: Image.Image, image_path: str) -> Image.Image:
    image_mode = detect_image_mode(image_path)

    if image_mode == "art":
        dither = Image.Dither.NONE
        logger.info(f"Quantize mode: art / no dither / {image_path}")
    else:
        dither = Image.Dither.FLOYDSTEINBERG
        logger.info(f"Quantize mode: photo / Floyd-Steinberg / {image_path}")

    rgb = img.convert("RGB")

    paletted = rgb.quantize(
        colors=CONFIG["OUTPUT_COLORS"],
        method=Image.Quantize.MEDIANCUT,
        dither=dither,
    )

    return paletted.convert("RGB")


def prepare_image(image_path, inky_display):
    try:
        target_width, target_height = inky_display.resolution
        image_mode = detect_image_mode(image_path)

        logger.info(
            f"画像処理開始: {os.path.basename(image_path)} "
            f"(target={target_width}x{target_height}, mode={image_mode})"
        )

        with Image.open(image_path) as original_img:
            base_img = original_img.convert("RGBA")

            if base_img.size == (target_width, target_height):
                logger.info(f"最適化済みサイズを検出: {base_img.size} → リサイズをスキップ")
                enhanced_img = enhance_image(base_img, image_mode)
            else:
                img_ratio = base_img.width / base_img.height
                target_ratio = target_width / target_height

                if img_ratio > target_ratio:
                    new_height = target_height
                    new_width = int(target_height * img_ratio)
                else:
                    new_width = target_width
                    new_height = int(target_width / img_ratio)

                resized_img = base_img.resize(
                    (new_width, new_height),
                    resample=Image.Resampling.LANCZOS,
                )

                left = (new_width - target_width) // 2
                top = (new_height - target_height) // 2

                cropped_img = resized_img.crop(
                    (
                        left,
                        top,
                        left + target_width,
                        top + target_height,
                    )
                )

                enhanced_img = enhance_image(cropped_img, image_mode)

            capture_date = extract_capture_date(image_path)
            final_img = add_date_overlay(enhanced_img, capture_date)

            final_img = apply_epaper_quantize(final_img, image_path)

            return final_img

    except Exception as e:
        logger.error(f"画像処理エラー [{os.path.basename(image_path)}]: {str(e)[:100]}")
        return None


def main():
    logger.info("=== Inky Spectra6 スライドショーを起動します ===")

    try:
        inky_display = auto(verbose=True)
        logger.info(
            f"検出されたディスプレイ: {inky_display.colour} "
            f"解像度: {inky_display.resolution}"
        )

    except Exception as e:
        logger.error(f"ディスプレイ初期化エラー: {e}")
        logger.error("Inkyライブラリが古い可能性があります。")
        return

    inky_display.set_border(inky_display.WHITE)

    photo_dir = CONFIG["PHOTO_DIR"]

    if not os.path.isdir(photo_dir):
        logger.error(f"画像ディレクトリが見つかりません: {photo_dir}")
        return

    current_files = collect_images()
    current_file_count = len(current_files)

    saved_count, display_queue = load_state()

    if current_file_count != saved_count:
        logger.info(
            f"画像数の変動を検知しました "
            f"(前回:{saved_count} -> 現在:{current_file_count})。"
            "キューをリセットします。"
        )
        display_queue = []

    total_in_cycle = current_file_count

    while True:
        try:
            if not display_queue:
                logger.info("表示キューが空です。全画像リストを再生成します。")

                all_files = collect_images()

                if not all_files:
                    logger.error(f"画像ファイルが見つかりませんでした: {photo_dir}")

                    if os.path.exists(STATE_FILE):
                        os.remove(STATE_FILE)

                    time.sleep(60)
                    continue

                random.shuffle(all_files)
                display_queue = all_files
                total_in_cycle = len(display_queue)

            image_path = display_queue.pop(0)

            if not os.path.exists(image_path):
                logger.warning(f"存在しない画像をスキップします: {image_path}")
                save_state(display_queue, total_in_cycle)
                continue

            logger.info(
                f"表示処理開始: {os.path.basename(image_path)} "
                f"/ mode={detect_image_mode(image_path)}"
            )

            processed_image = prepare_image(image_path, inky_display)

            if processed_image:
                try:
                    inky_display.set_image(
                        processed_image,
                        saturation=CONFIG["SATURATION"],
                    )
                    inky_display.show()

                    logger.info(f"表示に成功しました: {os.path.basename(image_path)}")
                    save_state(display_queue, total_in_cycle)

                except Exception as e:
                    logger.error(f"表示エラー: {str(e)[:100]}")
                    display_queue.insert(0, image_path)

            logger.info(f"{CONFIG['INTERVAL_SECONDS']}秒待機します...")
            time.sleep(CONFIG["INTERVAL_SECONDS"])

        except KeyboardInterrupt:
            logger.info("ユーザーの操作により中断されました")
            break

        except Exception as e:
            logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
    logger.info("=== プログラムを正常終了します ===")
