import subprocess
import time
import sys
import os
import signal

LOG_FILE = "/home/student/pond-planning/service.log"
PID_FILE = "/home/student/pond-planning/supervisor.pid"
VENV_PYTHON = "/home/student/pond-planning/venv/bin/python"
APP_DIR = "/home/student/pond-planning"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except:
        pass

def kill_existing():
    log("Checking for existing uvicorn processes on ports 3000 and 6000...")
    os.system("pkill -9 -f 'uvicorn.*main:app.*3000' 2>/dev/null")
    os.system("pkill -9 -f 'uvicorn.*main:app.*6000' 2>/dev/null")
    os.system("pkill -9 -f 'python.*main.py' 2>/dev/null")
    time.sleep(1)

def run_worker(port):
    cmd = [
        VENV_PYTHON, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--access-log"
    ]
    log_path = f"/home/student/pond-planning/worker_{port}.log"
    log_f = open(log_path, "a")
    proc = subprocess.Popen(cmd, cwd=APP_DIR, stdout=log_f, stderr=subprocess.STDOUT)
    log(f"Started worker on port {port} (PID: {proc.pid}) -> logging to {log_path}")
    return proc

def main():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
        
    kill_existing()
    
    ports = [3000, 6000]
    procs = {}
    
    for p in ports:
        procs[p] = run_worker(p)
        
    log("AquaPlan AI Services are now active on ports 3000 and 6000.")
    log("Public access URLs:")
    log("  -> Frontend & API (Port 6000): http://10.1.75.51:6253")
    log("  -> Backend & API (Port 3000):  http://10.1.75.51:3253")
    
    # Watchdog loop
    while True:
        time.sleep(3)
        for p in ports:
            proc = procs.get(p)
            if proc is None or proc.poll() is not None:
                exit_code = proc.poll() if proc else "None"
                log(f"WARNING: Worker on port {p} exited with code {exit_code}. Restarting...")
                procs[p] = run_worker(p)

if __name__ == "__main__":
    main()
