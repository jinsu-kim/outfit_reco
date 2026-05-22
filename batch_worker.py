import os
import json
import time
from datetime import datetime
from typing import Optional, List

import gpustat
import redis

from outfit_gen import run_batch

redis_client = redis.Redis(
    host="redis",
    port=6379,
    db=0,
    decode_responses=True,
)

QUEUE_NAME = "outfit_batch"
GPU_LOCK_KEY = "gpu_lock"
VISIBLE_GPU = os.environ.get("CUDA_VISIBLE_DEVICES", "0")

def is_gpu_available(max_memory_used: int = 2000, max_volatility = 10) -> bool:

    stats = gpustat.GPUStatCollection.new_query()
    gpu   = stats.gpus[0]

    memory_used = gpu.memory_used
    gpu_util = gpu.utilization if gpu.utilization is not None else 0

    return memory_used <= max_memory_used and gpu_util <= max_volatility

def get_gpu_lock(job_id: str, gpu_id: int, ttl: int = 60 * 60) -> bool:

    lock_key = f"{GPU_LOCK_KEY}:{gpu_id}"

    return bool(
        redis_client.set(lock_key, job_id, nx=True,ex=ttl)
    )

def update_job_status(job_id: str, status: str, **kwargs) -> None:


def main() -> None:
    print("GPU worker started.")

    while True:
        # gpu status check
        gpu_list = gpu_status_check()

        if not gpu_list:
            time.sleep(30)
            continue

        gpu_id = gpu_list[0]

        # queued batch jobs
        result = redis_client.blpop(QUEUE_NAME, timeout=5)

        if result is None:
            continue

        _, raw_job = result

        # identify batch job from queue
        job = json.loads(raw_job)
        job_id = job["job_id"]
        params = job["params"]

        gpu_id = gpu_status_check()

        if gpu_id is None:
            continue


