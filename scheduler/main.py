from azure.servicebus import ServiceBusClient, ServiceBusMessage
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module
from opencensus.ext.azure import metrics_exporter
from batch_submitter import BatchJobSubmitter
import json
import time
import sys
import os
import logging

# Environment variables
SERVICEBUS_CONNECTION_STRING = os.getenv("SERVICEBUS_CONNECTION_STRING")
BATCH_ACCOUNT_NAME = os.getenv("BATCH_ACCOUNT_NAME")
BATCH_ACCOUNT_KEY = os.getenv("BATCH_ACCOUNT_KEY")
BATCH_ACCOUNT_URL = os.getenv("BATCH_ACCOUNT_URL")
APPINSIGHTS_CONNECTION_STRING = os.getenv("APPINSIGHTS_CONNECTION_STRING")

MAX_RETRIES = 10
RETRY_DELAY = 5

# Setup logging with Application Insights
logger = logging.getLogger(__name__)
if APPINSIGHTS_CONNECTION_STRING:
    logger.addHandler(AzureLogHandler(connection_string=APPINSIGHTS_CONNECTION_STRING))
    logger.setLevel(logging.INFO)

# Initialize Batch submitter (optional - only if Batch is configured)
batch_submitter = None
if BATCH_ACCOUNT_NAME and BATCH_ACCOUNT_KEY and BATCH_ACCOUNT_URL:
    try:
        batch_submitter = BatchJobSubmitter(
            BATCH_ACCOUNT_NAME, 
            BATCH_ACCOUNT_KEY, 
            BATCH_ACCOUNT_URL,
            appinsights_connection_string=APPINSIGHTS_CONNECTION_STRING
        )
        print("[SCHEDULER] Azure Batch integration enabled", flush=True)
    except Exception as e:
        print(f"[SCHEDULER] Azure Batch not available: {e}", flush=True)

def connect_with_retry():
    """Connect to Service Bus with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[SCHEDULER] Attempting to connect to Service Bus (attempt {attempt + 1}/{MAX_RETRIES})...", flush=True)
            client = ServiceBusClient.from_connection_string(SERVICEBUS_CONNECTION_STRING)
            print("[SCHEDULER] Successfully connected to Service Bus", flush=True)
            return client
        except Exception as e:
            print(f"[SCHEDULER] Connection failed: {e}", flush=True)
            if attempt < MAX_RETRIES - 1:
                print(f"[SCHEDULER] Retrying in {RETRY_DELAY} seconds...", flush=True)
                time.sleep(RETRY_DELAY)
            else:
                print("[SCHEDULER] Max retries reached. Exiting.", flush=True)
                sys.exit(1)

def estimate_cost(job: dict):
    p = job["payload"]

    cpu_cost = p.get("rows", 1000) / 1_000_000
    time_cost = p.get("estimated_runtime_sec", 10) / 60

    priority_weight = 2 if p.get("priority") == "high" else 1

    total_score = (cpu_cost + time_cost) * priority_weight
    return total_score

def classify(job: dict) -> tuple:
    
    score = estimate_cost(job)
    p = job["payload"]

    # Latency-sensitive jobs always go to AKS for fast response
    if p.get("latency_sensitive") == True:
        return ("aks", "actor-jobs")

    # Heavy compute jobs go to Azure Batch if available
    if batch_submitter and score > 10:
        return ("batch", "spark")
    elif batch_submitter and score > 4:
        return ("batch", "ml")
    
    # Fallback to AKS queues if Batch not configured
    if score > 10:
        return ("aks", "spark-jobs")
    elif score > 4:
        return ("aks", "ml-jobs")
    else:
        return ("aks", "actor-jobs")

def route_job(client, job: dict, platform: str, target: str):
    job_id = job.get('job_id', 'unknown')
    
    if platform == "batch":
        # Submit to Azure Batch
        try:
            result = batch_submitter.submit_job(job_id, job["payload"], target)
            print(f"[SCHEDULER] Routed job to Azure Batch ({target}): {job_id}", flush=True)
            
            if logger:
                logger.info(f"Job routed to Batch: {job_id}", extra={
                    'custom_dimensions': {
                        'job_id': job_id,
                        'platform': 'batch',
                        'job_type': target,
                        'batch_job_id': result.get('batch_job_id')
                    }
                })
        except Exception as e:
            print(f"[SCHEDULER] Batch submission failed, falling back to AKS: {e}", flush=True)
            # Fallback to AKS if Batch fails
            fallback_queue = f"{target}-jobs"
            sender = client.get_queue_sender(queue_name=fallback_queue)
            with sender:
                message = ServiceBusMessage(json.dumps(job))
                sender.send_messages(message)
            print(f"[SCHEDULER] Fallback: Routed job to AKS {fallback_queue}: {job_id}", flush=True)
    else:
        # Submit to AKS via Service Bus queue
        sender = client.get_queue_sender(queue_name=target)
        with sender:
            message = ServiceBusMessage(json.dumps(job))
            sender.send_messages(message)
        print(f"[SCHEDULER] Routed job to AKS {target}: {job_id}", flush=True)
        
        if logger:
            logger.info(f"Job routed to AKS: {job_id}", extra={
                'custom_dimensions': {
                    'job_id': job_id,
                    'platform': 'aks',
                    'queue': target
                }
            })

def process_message(client, msg):
    start_time = time.time()
    job = json.loads(str(msg))
    job_id = job.get('job_id', 'unknown')
    print(f"[SCHEDULER] Scheduling job: {job_id}", flush=True)
    
    # Classify and route the job
    platform, target = classify(job)
    cost = estimate_cost(job)
    print(f"[SCHEDULER] Classification: {platform}/{target} (score: {cost:.2f})", flush=True)
    
    route_job(client, job, platform, target)
    
    duration = time.time() - start_time
    if logger:
        logger.info(f"Job scheduled: {job_id}", extra={
            'custom_dimensions': {
                'job_id': job_id,
                'platform': platform,
                'target': target,
                'cost_score': cost,
                'duration_ms': duration * 1000
            }
        })

def main():
    print("[SCHEDULER] Starting scheduler...", flush=True)
    print(f"[SCHEDULER] Service Bus connection configured", flush=True)
    
    if batch_submitter:
        print("[SCHEDULER] Azure Batch integration: ENABLED", flush=True)
        print("[SCHEDULER] Heavy jobs (spark/ml) will be sent to Azure Batch", flush=True)
    else:
        print("[SCHEDULER] Azure Batch integration: DISABLED", flush=True)
        print("[SCHEDULER] All jobs will be sent to AKS queues", flush=True)
    
    client = connect_with_retry()
    
    receiver = client.get_queue_receiver(queue_name="jobqueue", max_wait_time=5)
    
    print("[SCHEDULER] Listening for jobs...", flush=True)
    try:
        with receiver:
            while True:
                received_msgs = receiver.receive_messages(max_message_count=1, max_wait_time=5)
                for msg in received_msgs:
                    try:
                        process_message(client, msg)
                        receiver.complete_message(msg)
                    except Exception as e:
                        print(f"[SCHEDULER] Error processing message: {e}", flush=True)
                        if logger:
                            logger.error(f"Scheduling error: {str(e)}")
                        receiver.abandon_message(msg)
    except KeyboardInterrupt:
        print("[SCHEDULER] Shutting down gracefully...", flush=True)
        client.close()

if __name__ == "__main__":
    main()

