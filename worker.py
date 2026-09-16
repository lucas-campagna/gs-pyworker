"""PyWorker — lightweight HTTP proxy that runs on port 3000, forwards to model server on 18000."""

import os
import subprocess
import sys
import time
import traceback

LOG_DIR = "/var/log/model"
os.makedirs(LOG_DIR, exist_ok=True)

WORKER_LOG = os.path.join(LOG_DIR, "worker.log")
_model_log = open(WORKER_LOG, "a")


def _log(msg):
    line = f"[worker.py] {msg}\n"
    _log_raw(line)


def _log_raw(line):
    sys.stdout.write(line)
    sys.stdout.flush()
    _model_log.write(line)
    _model_log.flush()


if __name__ == "__main__":
    _log("=== worker.py starting ===")
    _log(f"argv={sys.argv}")
    _log(f"cwd={os.getcwd()}")
    _log(f"pid={os.getpid()}")

    for v in ["WORKER_PORT", "CONTAINER_ID", "MASTER_TOKEN", "REPORT_ADDR",
              "PUBLIC_IPADDR", "SERVERLESS", "USE_SSL", "BACKEND", "MODEL_LOG"]:
        _log(f"ENV {v}={os.environ.get(v, 'NOT SET')}")
    for k, val in sorted(os.environ.items()):
        if k.startswith("VAST_"):
            _log(f"ENV {k}={val}")

    try:
        _log("Importing vastai SDK...")
        from vastai import Worker, WorkerConfig, HandlerConfig, BenchmarkConfig, LogActionConfig
        _log("vastai SDK imported OK")

        _log("Starting model server...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "model_server:app",
             "--host", "127.0.0.1", "--port", "18000"],
            cwd="/app",
            stdout=open(os.path.join(LOG_DIR, "server_stdout.log"), "a"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(3)
        if proc.poll() is not None:
            _log(f"ERROR: Model server exited immediately with code {proc.returncode}")
            sys.exit(1)
        _log(f"Model server started (pid={proc.pid})")

        LOG_FILE = os.environ.get("MODEL_LOG", "/var/log/model/server.log")

        def workload_calculator(payload):
            return 100.0

        def request_parser(request):
            return request

        _log("Building WorkerConfig...")
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
        _log("WorkerConfig built OK")

        _log("Creating Worker and calling run()...")
        w = Worker(config)
        _log(f"Worker created: {w}")
        w.run()
        _log("Worker.run() returned")

    except Exception as e:
        _log(f"FATAL EXCEPTION: {type(e).__name__}: {e}")
        _log(traceback.format_exc())
        sys.exit(1)
    finally:
        _log("=== worker.py exiting ===")
        _model_log.close()
