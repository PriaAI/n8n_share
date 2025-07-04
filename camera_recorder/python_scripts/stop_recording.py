import json
import os
import signal
from pathlib import Path
import sys


def stop_processes(pid_file_path):
    """Stop all RTSP recording processes."""
    try:
        pid_file = Path(pid_file_path)

        if not pid_file.exists():
            return {"status": "not_running", "message": "No recording processes found"}

        with open(pid_file) as f:
            pids = json.load(f)

        # Stop each process
        for process_name, pid in pids.items():
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"Stopped {process_name} process (PID: {pid})")
            except ProcessLookupError:
                print(f"Process {process_name} (PID: {pid}) not found")
            except Exception as e:
                print(f"Error stopping {process_name}: {e}")

        # Remove PID file
        pid_file.unlink()

        return {"status": "stopped", "stopped_processes": list(pids.keys())}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def main():
    # Default PID file location or from command line
    pid_file = sys.argv[1] if len(sys.argv) > 1 else "./screenshots/rtsp_pids.json"

    result = stop_processes(pid_file)
    print(json.dumps(result))

    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
