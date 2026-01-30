from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module
from opencensus.tags import tag_map as tag_map_module
import json
import uuid
import os
import time
import logging

app = FastAPI()

# Azure Application Insights configuration
APPINSIGHTS_CONNECTION_STRING = os.getenv("APPINSIGHTS_CONNECTION_STRING")
SERVICEBUS_CONNECTION_STRING = os.getenv("SERVICEBUS_CONNECTION_STRING")

# Setup logging with Application Insights
logger = logging.getLogger(__name__)
if APPINSIGHTS_CONNECTION_STRING:
    logger.addHandler(AzureLogHandler(connection_string=APPINSIGHTS_CONNECTION_STRING))
    logger.setLevel(logging.INFO)
    
    # Setup custom metrics
    stats = stats_module.stats
    view_manager = stats.view_manager
    exporter = metrics_exporter.new_metrics_exporter(connection_string=APPINSIGHTS_CONNECTION_STRING)
    view_manager.register_exporter(exporter)
    
    # Define metrics
    jobs_submitted_measure = measure_module.MeasureInt("jobs_submitted", "Number of jobs submitted", "jobs")
    jobs_submitted_view = view_module.View("jobs_submitted_total", "Total jobs submitted",
                                           [], jobs_submitted_measure, aggregation_module.CountAggregation())
    view_manager.register_view(jobs_submitted_view)
    
    request_duration_measure = measure_module.MeasureFloat("request_duration", "Request duration", "ms")
    request_duration_view = view_module.View("api_request_duration", "API request duration",
                                            [], request_duration_measure, aggregation_module.DistributionAggregation())
    view_manager.register_view(request_duration_view)
    
    mmap = stats.stats_recorder.new_measurement_map()

class JobPayload(BaseModel):
    rows: Optional[int] = 1000
    estimated_runtime_sec: Optional[int] = 10
    priority: Optional[str] = "normal"  # "high" or "normal"
    latency_sensitive: Optional[bool] = False
    data: Optional[dict] = {}

@app.post("/submit-job")
def submit_job(payload: JobPayload):
    start_time = time.time()
    job_id = str(uuid.uuid4())
    
    job = {
        "job_id": job_id,
        "payload": payload.dict()
    }
    
    try:
        with ServiceBusClient.from_connection_string(SERVICEBUS_CONNECTION_STRING) as client:
            sender = client.get_queue_sender(queue_name="jobqueue")
            with sender:
                message = ServiceBusMessage(json.dumps(job))
                sender.send_messages(message)
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Log to Application Insights
        if APPINSIGHTS_CONNECTION_STRING:
            logger.info(f"Job submitted: {job_id}", extra={
                'custom_dimensions': {
                    'job_id': job_id,
                    'rows': payload.rows,
                    'priority': payload.priority,
                    'latency_sensitive': payload.latency_sensitive,
                    'duration_ms': duration_ms
                }
            })
            mmap.measure_int_put(jobs_submitted_measure, 1)
            mmap.measure_float_put(request_duration_measure, duration_ms)
            mmap.record()
        
        return {
            "status": "submitted",
            "job_id": job_id
        }
    except Exception as e:
        if APPINSIGHTS_CONNECTION_STRING:
            logger.error(f"Job submission failed: {str(e)}", extra={
                'custom_dimensions': {'job_id': job_id}
            })
        raise HTTPException(status_code=500, detail=str(e))

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
                count = queue_props.total_message_count
                status[queue] = count
            except:
                status[queue] = 0
        
        if APPINSIGHTS_CONNECTION_STRING:
            logger.info("Queue status checked", extra={
                'custom_dimensions': status
            })
        
        return status
    except Exception as e:
        if APPINSIGHTS_CONNECTION_STRING:
            logger.error(f"Queue status check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
