from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import json
import uuid
import os

app = FastAPI()

SERVICEBUS_CONNECTION_STRING = os.getenv("SERVICEBUS_CONNECTION_STRING")

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
    
    with ServiceBusClient.from_connection_string(SERVICEBUS_CONNECTION_STRING) as client:
        sender = client.get_queue_sender(queue_name="jobqueue")
        with sender:
            message = ServiceBusMessage(json.dumps(job))
            sender.send_messages(message)
    
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
        from azure.servicebus.management import ServiceBusAdministrationClient
        
        admin_client = ServiceBusAdministrationClient.from_connection_string(SERVICEBUS_CONNECTION_STRING)
        queues = ["jobqueue", "actor-jobs", "spark-jobs", "ml-jobs", "batch-jobs"]
        status = {}
        
        for queue in queues:
            try:
                queue_props = admin_client.get_queue_runtime_properties(queue)
                status[queue] = queue_props.total_message_count
            except:
                status[queue] = 0
        
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
