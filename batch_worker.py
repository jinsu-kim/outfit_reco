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

def gpu_status(max_memory_used: int = 2000, max_volatility = 10) -> Optional[int]:

    stats = gpustat.GPUStatCollection.new_query()

    for gpu in stats.gpus:
        memory_used = gpu.memory_used
        gpu_util    = gpu.utilization if gpu.utilization is not None else 0

        if memory_used < max_memory_used and gpu_util < max_volatility:
            return gpu.index

    return None