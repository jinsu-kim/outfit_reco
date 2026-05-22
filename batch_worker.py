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
JOB_KEY_PREFIX = "outfit_batch_job"

VISIBLE_GPU = os.environ.get("CUDA_VISIBLE_DEVICES", "0")

def is_gpu_available(max_memory_used: int = 2000, max_volatility = 10) -> bool:

    stats = gpustat.GPUStatCollection.new_query()
    gpu   = stats.gpus[0]

    memory_used = gpu.memory_used
    gpu_util = gpu.utilization if gpu.utilization is not None else 0

    return memory_used <= max_memory_used and gpu_util <= max_volatility


def update_job_status(job_id: str, status: str, **kwargs) -> None:

    mapping = {"status":status}
    mapping.update({
        key: str(value)
        for key, value in kwargs.items()
        if value is not None
    })

    redis_client.hset(
        f"{JOB_KEY_PREFIX}:{job_id}",
        mapping=mapping,
    )


def main() -> None:
    print(f"GPU worker started. CUDA_VISIBLE_DEVICES={VISIBLE_GPU}")

    while True:
        # gpu status check
        if not is_gpu_available():
            time.sleep(30)
            continue

        # queued batch jobs
        result = redis_client.blpop(QUEUE_NAME, timeout=5)

        if result is None:
            continue

        _, raw_job = result

        # identify batch job from queue
        job = json.loads(raw_job)
        job_id = job["job_id"]
        params = job["params"]

        try:
            update_job_status(job_id, "running", visible_gpu=VISIBLE_GPU)
            current_date = datetime.fromisoformat(params["current_date"])

            recommendations, failure_report, valid_items = run_batch(
                items_csv=params["items_csv"],
                site_id=params["site_id"],
                current_date=current_date,
                guidelines_json=params["guidelines_json"],
                compatibility_npy=params["compatibility_npy"],
                out_dir=params["out_dir"],
                num_styles=params["num_styles"],
                min_candidates_per_slot=params["min_candidates_per_slot"],
            )

            update_job_status(
                job_id,
                "completed",
                visible_gpu=VISIBLE_GPU,
                result_path=params["out_dir"],
                recommendation_count=len(recommendations),
                failure_count=len(failure_report),
                valid_item_count=len(valid_items),
            )

        except Exception as e:
            update_job_status(job_id, "failed", visible_gpu=VISIBLE_GPU, error=repr(e))


if __name__ == "__main__":
    main()

