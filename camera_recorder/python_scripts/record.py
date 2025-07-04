import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
import argparse
import signal
import sys
import json
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("rtsp_record.log"), logging.StreamHandler()],
)

# Example command to run ffmpeg as single process. Update the username, password, and IP address as needed.
# nohup ffmpeg -rtsp_transport tcp -i rtsp://[username]:[password]@192.168.50.150:201/live/ch0 -c copy -map 0 -reset_timestamps 1 -f segment -segment_time 600 -strftime 1 /files/recordings/%Y-%m-%d__%H-%M-%S.mp4 -vf fps=0.2 -update 1 -q:v 2 /files/screenshots/latest.jpg &


def start(
    rtsp_url, recording_dir, screenshot_dir, segment_time=600, screenshot_interval=15
):
    """Start both recording and screenshot processes."""
    # Create directories
    # recording_dir.mkdir(parents=True, exist_ok=True)
    # screenshot_dir.mkdir(parents=True, exist_ok=True)
    processes = []

    # Start screenshot process with higher frequency
    screenshot_cmd = [
        "ffmpeg",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-vf",
        f"fps=1/{screenshot_interval}",
        "-update",
        "1",
        "-q:v",
        "2",
        str(screenshot_dir / "latest.jpg"),
    ]

    screenshot_process = subprocess.Popen(
        screenshot_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    processes.append(screenshot_process)

    # Start continuous recording process
    record_cmd = [
        "ffmpeg",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-c",
        "copy",
        "-map",
        "0",
        "-reset_timestamps",
        "1",
        "-f",
        "segment",
        "-segment_time",
        str(segment_time),
        "-strftime",
        "1",
        str(recording_dir / "%Y-%m-%d__%H-%M-%S.mp4"),
    ]
    logging.info(f"Starting screenshot process: {' '.join(screenshot_cmd)}")
    record_process = subprocess.Popen(
        record_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    processes.append(record_process)

    processing_path = str(screenshot_dir / "processing")
    # Start copying screenshots for n8n processing
    while True:
        try:
            latest = str(screenshot_dir / "latest.jpg")
            if latest.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                process_file = str(processing_path / f"frame_{timestamp}.jpg")
                shutil.copy2(latest, process_file)

                # Keep only last 5 processing images
                files = sorted(processing_path.glob("frame_*.jpg"))[:-5]
                for old_file in files:
                    old_file.unlink()

            time.sleep(screenshot_interval)
        except Exception as e:
            print(f"Error copying screenshot: {e}")


def check_rtsp_stream(url, timeout=5):
    """Test RTSP stream connectivity"""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        url,
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        "-timeout",
        str(timeout * 1000000),  # microseconds
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logging.error(f"RTSP stream check timed out after {timeout} seconds")
        return False
    except Exception as e:
        logging.error(f"RTSP stream check failed: {e}")
        return False


def start_background_processes(
    rtsp_url, recording_dir, screenshot_dir, segment_time=600, screenshot_interval=15
):
    """Start FFmpeg processes in background and return their PIDs"""

    # Check stream first
    logging.info("Checking RTSP stream...")
    retry_count = 0
    max_retries = 5

    while retry_count < max_retries:
        if check_rtsp_stream(rtsp_url):
            logging.info("RTSP stream is accessible")
            break
        retry_count += 1
        if retry_count < max_retries:
            wait_time = retry_count * 5
            logging.warning(
                f"RTSP stream not available, retrying in {wait_time} seconds..."
            )
            time.sleep(wait_time)
    else:
        return {"status": "error", "message": "RTSP stream not accessible"}

    # Convert parameters to integers
    segment_time = int(segment_time)
    screenshot_interval = int(screenshot_interval)

    # Create absolute paths
    base_dir = Path("/files")  # Container base directory
    recording_path = (base_dir / recording_dir).resolve()
    screenshot_path = (base_dir / screenshot_dir).resolve()
    processing_path = screenshot_path / "processing"

    # Ensure directories exist with proper permissions
    for path in [recording_path, screenshot_path, processing_path]:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o777)  # Full permissions in container
        logging.info(f"Directory ready: {path} with permissions 777")

    frame_interval = 1 / screenshot_interval
    # Start screenshot process with full path
    combined_cmd = [
        "ffmpeg",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-c",
        "copy",
        "-map",
        "0",
        "-reset_timestamps",
        "1",
        "-f",
        "segment",
        "-segment_time",
        "600",
        "-strftime",
        "1",
        f"{recording_path}/%Y-%m-%d__%H-%M-%S.mp4",
        "-vf",
        f"fps={frame_interval}",
        "-update",
        "1",
        "-y",
        "-q:v",
        "2",
        f"{screenshot_path}/latest.jpg",
    ]

    logging.info(f"Starting screenshot process: {' '.join(combined_cmd)}")

    with open("ffmpeg_combined.log", "w") as log:
        screenshot_process = subprocess.Popen(
            combined_cmd, stdout=log, stderr=log, start_new_session=True
        )

    # Wait briefly to check for immediate failures
    time.sleep(2)

    # Check if processes are running
    if screenshot_process.poll() is not None:
        with open("ffmpeg_combined.log", "r") as f:
            logging.error(f"Combined process failed. FFmpeg output:\n{f.read()}")
        return {"status": "error", "message": "Combined process failed"}

    # Save PIDs
    pids = {
        "combined": screenshot_process.pid,
    }

    pid_file = screenshot_path / "rtsp_pids.json"
    with open(pid_file, "w") as f:
        json.dump(pids, f)

    return {
        "status": "started",
        "pids": pids,
        "pid_file": str(pid_file),
        "latest_screenshot": str(screenshot_path / "latest.jpg"),
        "processing_dir": str(processing_path),
        "recording_dir": str(recording_path),
    }


def main():
    parser = argparse.ArgumentParser(
        description="RTSP Stream Recorder and Screenshot Capture"
    )
    parser.add_argument("--url", required=True, help="RTSP URL")
    parser.add_argument(
        "--recordings", default="./recordings", help="Recording directory"
    )
    parser.add_argument(
        "--screenshots", default="./screenshots", help="Screenshot directory"
    )
    parser.add_argument(
        "--segment-time",
        type=int,
        default=600,
        help="Recording segment time in seconds",
    )
    parser.add_argument(
        "--screenshot-interval",
        type=int,
        default=5,
        help="Screenshot interval in seconds",
    )
    args = parser.parse_args()

    try:
        result = start_background_processes(
            args.url,
            args.recordings,
            args.screenshots,
            args.segment_time,
            args.screenshot_interval,
        )
        print(json.dumps(result))

        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
