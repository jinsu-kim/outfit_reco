import os
from uuid import uuid4
import json
import redis
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=0,
    decode_responses=True,
)

QUEUE_NAME = "outfit_batch"
JOB_KEY_PREFIX = "outfit_batch_job"

class OutfitBatchRequest(BaseModel):
    items_csv: str
    site_id: str
    guidelines_json: str
    compatibility_npy: str
    out_dir: str
    num_styles: int = 3
    min_candidates_per_slot: int = 1
    current_date: str


@app.post("/outfit-batch")
def enqueue_batch(req: OutfitBatchRequest):
    job_id = str(uuid4())

    params = req.model_dump()
    params["current_date"] = datetime.now().isoformat()

    job = {
        "job_id": job_id,
        "status": "queued",
        "params": params,
    }

    redis_client.hset(f"batch_job:{job_id}", mapping={
        "status": "queued",
        "params": json.dumps(req.model_dump(), ensure_ascii=False),
    })

    redis_client.rpush(QUEUE_NAME, json.dumps(job, ensure_ascii=False))

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Batch job has been queued.",
    }


@app.get("/outfit-batch/{job_id}")
def get_job_status(job_id: str):
    job_key = f"batch_job:{job_id}"
    job = redis_client.hgetall(job_key)

    if not job:
        return {
            "job_id": job_id,
            "status": "not_found",
        }

    return {
        "job_id": job_id,
        "status": job.get("status"),
    }