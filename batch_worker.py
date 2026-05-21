import json
import time
from datetime import datetime
from typing import Optional

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

def gpu_status_check(max_memory_used: int = 2000, max_volatility = 10) -> Optional[int]:

    stats = gpustat.GPUStatCollection.new_query()

    for gpu in stats.gpus:
        memory_used = gpu.memory_used
        gpu_util    = gpu.utilization if gpu.utilization is not None else 0

        if memory_used < max_memory_used and gpu_util < max_volatility:
            return gpu.index

    return None

def get_gpu_lock(job_id: str, gpu_id: int, ttl: int = 60 * 60) -> bool:

    lock_key = f"{GPU_LOCK_KEY}:{gpu_id}"

    return bool(
        redis_client.set(lock_key, job_id, nx=True,ex=ttl)
    )

def main() -> None:
    print("GPU worker started.")

    while True:
        _, raw_job = redis_client.blpop(QUEUE_NAME)

        # identify batch job from queue
        job = json.loads(raw_job)
        job_id = job["job_id"]
        params = job["params"]

        gpu_id = gpu_status_check()

        if gpu_id is None:
            continue


