from azure.servicebus import ServiceBusClient
from prometheus_client import Counter, Histogram, start_http_server
import json
import time
import os
import sys

# Prometheus metrics
jobs_processed = Counter('jobs_processed_total', 'Total jobs processed', ['worker_type'])
job_processing_duration = Histogram('job_processing_duration_seconds', 'Job processing time', ['worker_type'])
job_errors = Counter('job_errors_total', 'Total job errors', ['worker_type'])

SERVICEBUS_CONNECTION_STRING = os.getenv("SERVICEBUS_CONNECTION_STRING")
QUEUE_NAME = "actor-jobs"
MAX_RETRIES = 10
RETRY_DELAY = 5

def connect_with_retry():
    """Connect to Service Bus with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[ACTOR] Attempting to connect to Service Bus (attempt {attempt + 1}/{MAX_RETRIES})...", flush=True)
            client = ServiceBusClient.from_connection_string(SERVICEBUS_CONNECTION_STRING)
            print("[ACTOR] Successfully connected to Service Bus", flush=True)
            return client
        except Exception as e:
            print(f"[ACTOR] Connection failed: {e}", flush=True)
            if attempt < MAX_RETRIES - 1:
                print(f"[ACTOR] Retrying in {RETRY_DELAY} seconds...", flush=True)
                time.sleep(RETRY_DELAY)
            else:
                print("[ACTOR] Max retries reached. Exiting.", flush=True)
                sys.exit(1)

def process_job(job: dict):
    """Process actor job - low latency, lightweight tasks"""
    start_time = time.time()
    job_id = job.get("job_id", "unknown")
    payload = job.get("payload", {})
    
    print(f"[ACTOR] Processing job {job_id}", flush=True)
    print(f"[ACTOR] Payload: {payload}", flush=True)
    
    # Simulate processing
    time.sleep(1)
    
    duration = time.time() - start_time
    job_processing_duration.labels(worker_type='actor').observe(duration)
    jobs_processed.labels(worker_type='actor').inc()
    
    print(f"[ACTOR] Completed job {job_id} in {duration:.2f}s", flush=True)

def process_message(receiver, msg):
    try:
        job = json.loads(str(msg))
        process_job(job)
        receiver.complete_message(msg)
    except Exception as e:
        print(f"[ACTOR] Error: {e}", flush=True)
        job_errors.labels(worker_type='actor').inc()
        receiver.abandon_message(msg)

def main():
    print("[ACTOR] Starting actor worker...", flush=True)
    print(f"[ACTOR] Service Bus connection configured", flush=True)
    
    # Start Prometheus metrics server
    start_http_server(8002)
    print("[ACTOR] Metrics server started on port 8002", flush=True)
    
    client = connect_with_retry()
    receiver = client.get_queue_receiver(queue_name=QUEUE_NAME, max_wait_time=5)
    
    print(f"[ACTOR] Worker listening on {QUEUE_NAME}...", flush=True)
    try:
        with receiver:
            while True:
                received_msgs = receiver.receive_messages(max_message_count=1, max_wait_time=5)
                for msg in received_msgs:
                    process_message(receiver, msg)
    except KeyboardInterrupt:
        print("[ACTOR] Shutting down gracefully...", flush=True)
        client.close()

if __name__ == "__main__":
    main()
