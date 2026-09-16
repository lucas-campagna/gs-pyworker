"""PyWorker — lightweight HTTP proxy that runs on port 3000, forwards to model server on 18000."""

import os
import subprocess
import sys
import time
import traceback
import urllib.request
import json

LOG_DIR = "/var/log/model"
os.makedirs(LOG_DIR, exist_ok=True)


def _report_error(msg):
    """Report error to autoscaler (same as start_server.sh report_error_and_exit)."""
    try:
        container_id = int(os.environ.get("CONTAINER_ID", 0))
        master_token = os.environ.get("MASTER_TOKEN", "")
        report_addr = os.environ.get("REPORT_ADDR", "https://run.vast.ai")
        payload = json.dumps({
            "id": container_id,
            "mtoken": master_token,
            "version": os.environ.get("PYWORKER_VERSION", "0"),
            "error_msg": msg,
            "url": os.environ.get("URL", ""),
        }).encode()
        req = urllib.request.Request(
            f"{report_addr.rstrip('/')}/worker_status/",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.stderr.write("[worker.py] starting\n")
        sys.stderr.flush()

        # Import and init
        sys.stderr.write("[worker.py] importing vastai\n")
        sys.stderr.flush()
        from vastai import Worker, WorkerConfig, HandlerConfig, BenchmarkConfig, LogActionConfig
        sys.stderr.write("[worker.py] vastai imported OK\n")
        sys.stderr.flush()

        # Start model server
        sys.stderr.write("[worker.py] starting model server\n")
        sys.stderr.flush()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "model_server:app",
             "--host", "127.0.0.1", "--port", "18000"],
            cwd="/app",
            stdout=open(os.path.join(LOG_DIR, "server_stdout.log"), "a"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(3)
        if proc.poll() is not None:
            msg = f"Model server exited immediately with code {proc.returncode}"
            sys.stderr.write(f"[worker.py] ERROR: {msg}\n")
            sys.stderr.flush()
            _report_error(msg)
            sys.exit(1)
        sys.stderr.write(f"[worker.py] model server started (pid={proc.pid})\n")
        sys.stderr.flush()

        LOG_FILE = os.environ.get("MODEL_LOG", "/var/log/model/server.log")

        def workload_calculator(payload):
            return 100.0

        def request_parser(request):
            return request

        sys.stderr.write("[worker.py] building WorkerConfig\n")
        sys.stderr.flush()
        config = WorkerConfig(
            model_server_url="http://127.0.0.1",
            model_server_port=18000,
            model_log_file=LOG_FILE,
            handlers=[
                HandlerConfig(
                    route="/process",
                    allow_parallel_requests=False,
                    max_queue_time=600.0,
                    workload_calculator=workload_calculator,
                    request_parser=request_parser,
                    benchmark_config=BenchmarkConfig(
                        generator=lambda: {"video": ""},
                        runs=1,
                        concurrency=1,
                    ),
                )
            ],
            log_action_config=LogActionConfig(
                on_load=["Application startup complete."],
                on_error=["Traceback", "Error"],
                on_info=["Processing"],
            ),
        )
        sys.stderr.write("[worker.py] WorkerConfig built OK\n")
        sys.stderr.flush()

        sys.stderr.write("[worker.py] creating Worker and calling run()\n")
        sys.stderr.flush()
        w = Worker(config)
        sys.stderr.write(f"[worker.py] Worker created: {w}\n")
        sys.stderr.flush()
        w.run()
        sys.stderr.write("[worker.py] Worker.run() returned\n")
        sys.stderr.flush()

    except Exception as e:
        msg = f"worker.py FATAL: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
        _report_error(msg)
        sys.exit(1)
