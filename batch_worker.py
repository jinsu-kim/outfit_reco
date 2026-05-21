import json
import time
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