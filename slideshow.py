#!/usr/bin/python3
"""
Pimoroni Inky Impression 7.3" (Spectra6) 対応 スライドショープログラム
（汎用版：パスや設定を外部ファイルで管理し、再起動とファイル増減に自動対応）
"""

# ===== 標準ライブラリのインポート =====
import os
import time
import random
import logging
import json
from datetime import datetime

# ===== サードパーティライブラリのインポート =====
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import piexif
from inky.auto import auto
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# ==================== 設定定数（環境変数と固定値） ====================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.expanduser("~/.cache/slideshow_state_spectra6.json") # 状態保存ファイル

CONFIG = {
    # --- .envファイルから読み込む設定 ---
    "PHOTO_DIR": os.path.join(SCRIPT_DIR, os.getenv("PHOTO_DIR", "images")),
    "FONT_PATH": os.getenv("FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    "INTERVAL_SECONDS": int(os.getenv("INTERVAL_SECONDS", 1800)),

    # --- スクリプト内に記述する固定設定 ---
    "FONT_SIZE": 14,
    "DATE_FONT_SIZE": 16,
    "DATE_POSITIONS": ['bottom-right', 'top-right', 'top-left', 'bottom-left'],
    "MARGIN": 15,
    "BACKGROUND_PADDING": 10,
    "TEXT_PADDING": 8,
    "SATURATION": 0.5,
    "CONTRAST": 1.15
}

# ==================== ログシステムの初期化 ====================
def setup_logging():
    log_dir = os.path.expanduser("~/.logs/slideshow_logs")
    os.makedirs(log_dir, exist_ok=True)
    try:
        os.chmod(log_dir, 0o700)
    except Exception:
        pass
    log_file = os.path.join(log_dir, "slideshow_spectra6.log") # ログファイル名を変更
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==================== 状態管理関数 ====================
def save_state(queue, total_count):
    state = {"total_count": total_count, "queue": queue}
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
        logger.info(f"現在の状態を保存しました。残り: {len(queue)} / {total_count}枚")
    except Exception as e:
        logger.error(f"状態の保存に失敗しました: {e}")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                if isinstance(state, dict):
                    count = state.get("total_count", 0)
                    queue = state.get("queue", [])
                    logger.info(f"前回の状態を読み込みました。残り: {len(queue)} / {count}枚")
                    return count, queue
                elif isinstance(state, list):
                    logger.info("古い状態ファイルを検出しました。リセットします。")
                    return 0, state
        except Exception as e:
            logger.error(f"状態の読み込みに失敗しました: {e}")
    return 0, []

# ==================== 画像処理関連関数（変更なし） ====================
def extract_capture_date(image_path):
    if os.path.splitext(image_path)[1].lower() == '.png': return None
    try:
        exif_dict = piexif.load(image_path)
        date_str = exif_dict['Exif'].get(piexif.ExifIFD.DateTimeOriginal)
        if date_str: return datetime.strptime(date_str.decode('utf-8'), "%Y:%m:%d %H:%M:%S")
        return None
    except Exception as e:
        logger.warning(f"EXIF取得エラー ({os.path.basename(image_path)}): {e}")
        return None

def format_date_and_elapsed_time(capture_date):
    if not capture_date: return "Unknown date", "Unknown date"
    formatted_date = capture_date.strftime("%Y-%m-%d")
    delta = datetime.now() - capture_date
    years = delta.days // 365
    if years > 0: elapsed = f"{years} year{'s' if years > 1 else ''} ago"
    else:
        months = delta.days // 30
        if months > 0: elapsed = f"{months} month{'s' if months > 1 else ''} ago"
        else: elapsed = "Within a month"
    return formatted_date, elapsed

def enhance_image(img):
    return ImageEnhance.Contrast(img).enhance(CONFIG["CONTRAST"])

def add_date_overlay(img, capture_date):
    draw = ImageDraw.Draw(img, 'RGBA')
    elapsed_font = ImageFont.truetype(CONFIG["FONT_PATH"], CONFIG["FONT_SIZE"])
    date_font = ImageFont.truetype(CONFIG["FONT_PATH"], CONFIG["DATE_FONT_SIZE"])
    formatted_date, elapsed_time = format_date_and_elapsed_time(capture_date)
    date_bbox = draw.textbbox((0, 0), formatted_date, font=date_font)
    elapsed_bbox = draw.textbbox((0, 0), elapsed_time, font=elapsed_font)
    max_width = max(date_bbox[2], elapsed_bbox[2])
    date_height, elapsed_height = date_bbox[3] - date_bbox[1], elapsed_bbox[3] - elapsed_bbox[1]
    total_height = date_height + elapsed_height + CONFIG["TEXT_PADDING"]
    margin, padding = CONFIG["MARGIN"], CONFIG["BACKGROUND_PADDING"]
    position = random.choice(CONFIG["DATE_POSITIONS"])
    if 'right' in position: x = img.width - max_width - margin - padding
    else: x = margin + padding
    if 'bottom' in position: y = img.height - total_height - margin - padding
    else: y = margin + padding
    bg_left, bg_top = x - padding, y - padding
    bg_right, bg_bottom = x + max_width + padding, y + total_height + padding
    draw.rectangle((bg_left, bg_top, bg_right, bg_bottom), fill=(0, 0, 0, 128))
    draw.text((x, y), formatted_date, fill="white", font=date_font)
    draw.text((x, y + date_height + CONFIG["TEXT_PADDING"]), elapsed_time, fill="white", font=elapsed_font)
    return img

def prepare_image(image_path, inky_display):
    try:
        target_width, target_height = inky_display.resolution
        logger.info(f"画像処理開始: {os.path.basename(image_path)}")
        with Image.open(image_path) as original_img:
            base_img = original_img.convert('RGBA')
            enhanced_img = enhance_image(base_img)
            img_ratio = enhanced_img.width / enhanced_img.height
            target_ratio = target_width / target_height
            if img_ratio > target_ratio: new_height, new_width = target_height, int(target_height * img_ratio)
            else: new_width, new_height = target_width, int(target_width / img_ratio)
            resized_img = enhanced_img.resize((new_width, new_height), resample=Image.Resampling.LANCZOS)
            left, top = (new_width - target_width) // 2, (new_height - target_height) // 2
            cropped_img = resized_img.crop((left, top, left + target_width, top + target_height))
            capture_date = extract_capture_date(image_path)
            final_img_rgba = add_date_overlay(cropped_img, capture_date)
            return final_img_rgba.convert('RGB')
    except Exception as e:
        logger.error(f"画像処理エラー [{os.path.basename(image_path)}]: {str(e)[:100]}")
        return None

# ==================== メイン処理ループ（状態保存・自動リセット対応版） ====================
def main():
    logger.info("=== Inky Spectra6 スライドショーを起動します ===")
    try:
        inky_display = auto(verbose=True)
        logger.info(f"検出されたディスプレイ: {inky_display.colour} 解像度: {inky_display.resolution}")
    except Exception as e:
        logger.error(f"ディスプレイ初期化エラー: {e}")
        logger.error("Inkyライブラリが古い可能性があります。sudo pip install --upgrade pimoroni-inky をお試しください。")
        return

    inky_display.set_border(inky_display.WHITE)
    photo_dir = CONFIG["PHOTO_DIR"]
    if not os.path.isdir(photo_dir):
        logger.error(f"画像ディレクトリが見つかりません: {photo_dir}")
        return

    current_files = [os.path.join(photo_dir, f) for f in os.listdir(photo_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    current_file_count = len(current_files)
    saved_count, display_queue = load_state()

    if current_file_count != saved_count:
        logger.info(f"画像数の変動を検知しました (前回:{saved_count} -> 現在:{current_file_count})。キューをリセットします。")
        display_queue = []
    
    total_in_cycle = current_file_count

    while True:
        try:
            if not display_queue:
                logger.info("表示キューが空です。全画像リストを再生成します。")
                all_files = [os.path.join(photo_dir, f) for f in os.listdir(photo_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                if not all_files:
                    logger.error(f"画像ファイルが見つかりませんでした: {photo_dir}")
                    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
                    time.sleep(60)
                    continue
                
                random.shuffle(all_files)
                display_queue = all_files
                total_in_cycle = len(display_queue)

            image_path = display_queue.pop(0)
            
            logger.info(f"表示処理開始: {os.path.basename(image_path)}")
            processed_image = prepare_image(image_path, inky_display)

            if processed_image:
                try:
                    inky_display.set_image(processed_image, saturation=CONFIG["SATURATION"])
                    inky_display.show()
                    logger.info(f"表示に成功しました: {os.path.basename(image_path)}")
                    save_state(display_queue, total_in_cycle)
                except Exception as e:
                    logger.error(f"表示エラー: {str(e)[:100]}")
                    display_queue.insert(0, image_path) # 失敗した場合はキューの先頭に戻す
            
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
