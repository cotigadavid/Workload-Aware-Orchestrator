from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import pika
import json
import uuid

app = FastAPI()

RABBITMQ_URL = "amqp://guest:guest@rabbitmq:5672/"

class JobPayload(BaseModel):
    rows: Optional[int] = 1000
    estimated_runtime_sec: Optional[int] = 10
    priority: Optional[str] = "normal"  # "high" or "normal"
    latency_sensitive: Optional[bool] = False
    data: Optional[dict] = {}

@app.post("/submit-job")
def submit_job(payload: JobPayload):
    job_id = str(uuid.uuid4())
    
    job = {
        "job_id": job_id,
        "payload": payload.dict()
    }
    
    conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    ch = conn.channel()
    ch.queue_declare(queue="jobqueue", durable=True)
    
    ch.basic_publish(
        exchange="",
        routing_key="jobqueue",
        body=json.dumps(job),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    conn.close()
    
    return {
        "status": "submitted",
        "job_id": job_id
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/queues/status")
def queue_status():
    try:
        conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        ch = conn.channel()
        
        queues = ["jobqueue", "actor-jobs", "spark-jobs", "ml-jobs", "batch-jobs"]
        status = {}
        
        for queue in queues:
            try:
                result = ch.queue_declare(queue=queue, durable=True, passive=True)
                status[queue] = result.method.message_count
            except:
                status[queue] = 0
        
        conn.close()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
