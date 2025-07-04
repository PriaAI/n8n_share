import os
import time
import logging
from datetime import datetime
from pathlib import Path
import shutil
import argparse

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("rotate_images.log"), logging.StreamHandler()],
)


def rotate_images(screenshot_dir: str, interval: int = 5, max_images: int = 5):
    """Maintain a rotating set of recent screenshots."""
    screenshot_path = Path(screenshot_dir)
    processing_path = screenshot_path / "processing"

    # Ensure directories exist
    screenshot_path.mkdir(parents=True, exist_ok=True)
    processing_path.mkdir(parents=True, exist_ok=True)

    logging.info(f"Watching: {screenshot_path}")
    logging.info(f"Processing to: {processing_path}")
    logging.info(f"Interval: {interval} seconds")
    logging.info(f"Max images: {max_images}")

    while True:
        try:
            latest = screenshot_path / "latest.jpg"
            if latest.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                process_file = processing_path / f"frame_{timestamp}.jpg"
                shutil.copy2(latest, process_file)

                # Keep only most recent images
                files = sorted(list(processing_path.glob("frame_*.jpg")))
                if len(files) > max_images:
                    for old_file in files[:-max_images]:
                        old_file.unlink()
                        logging.debug(f"Removed old frame: {old_file.name}")

            time.sleep(interval)
        except KeyboardInterrupt:
            logging.info("Rotation stopped by user")
            break
        except Exception as e:
            logging.error(f"Error rotating images: {e}")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description="Maintain rotating set of recent screenshots"
    )
    parser.add_argument("--dir", default="./screenshots", help="Screenshot directory")
    parser.add_argument(
        "--interval", type=int, default=5, help="Check interval in seconds"
    )
    parser.add_argument(
        "--max", type=int, default=5, help="Maximum number of images to keep"
    )
    args = parser.parse_args()

    rotate_images(args.dir, args.interval, args.max)


if __name__ == "__main__":
    main()
