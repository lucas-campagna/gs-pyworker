"""PyWorker — lightweight HTTP proxy that runs on port 8080, forwards to model server on 18000."""

import os
import subprocess
import sys
import time

from vastai import Worker, WorkerConfig, HandlerConfig, BenchmarkConfig, LogActionConfig


def start_model_server():
    """Start the FastAPI model server as a subprocess."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "model_server:app",
         "--host", "127.0.0.1", "--port", "18000"],
        cwd="/app",
        stdout=open("/var/log/model/server_stdout.log", "a"),
        stderr=subprocess.STDOUT,
    )
    time.sleep(3)
    if proc.poll() is not None:
        print(f"ERROR: Model server exited immediately with code {proc.returncode}", flush=True)
        sys.exit(1)
    print(f"Model server started (pid={proc.pid})", flush=True)
    return proc


def workload_calculator(payload):
    """Constant cost per request — Gaussian Splatting takes ~minutes regardless."""
    return 100.0


def request_parser(request):
    """Forward the request body as-is to the model server."""
    return request


if __name__ == "__main__":
    # Debug: print env vars
    for v in ["WORKER_PORT", "CONTAINER_ID", "MASTER_TOKEN", "REPORT_ADDR",
              "PUBLIC_IPADDR", "SERVERLESS", "USE_SSL", "BACKEND", "MODEL_LOG"]:
        print(f"ENV {v}={os.environ.get(v, 'NOT SET')}", flush=True)
    for k, val in os.environ.items():
        if k.startswith("VAST_"):
            print(f"ENV {k}={val}", flush=True)

    model_proc = start_model_server()

    LOG_FILE = os.environ.get("MODEL_LOG", "/var/log/model/server.log")

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

    try:
        Worker(config).run()
    finally:
        model_proc.terminate()
