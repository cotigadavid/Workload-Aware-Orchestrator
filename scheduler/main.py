from azure.servicebus import ServiceBusClient, ServiceBusMessage
import json
import time
import sys
import os

SERVICEBUS_CONNECTION_STRING = os.getenv("SERVICEBUS_CONNECTION_STRING")
MAX_RETRIES = 10
RETRY_DELAY = 5

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

def classify(job: dict) -> str:
    score = estimate_cost(job)
    p = job["payload"]

    if p.get("latency_sensitive") == True:
        return "actor-jobs"

    if score > 10:
        return "spark-jobs"
    elif score > 4:
        return "ml-jobs"
    else:
        return "batch-jobs"

def route_job(client, job: dict, target_queue: str):
    """Route job to the appropriate queue"""
    sender = client.get_queue_sender(queue_name=target_queue)
    with sender:
        message = ServiceBusMessage(json.dumps(job))
        sender.send_messages(message)
    print(f"[SCHEDULER] Routed job to {target_queue}: {job.get('job_id', 'unknown')}", flush=True)

def process_message(client, msg):
    job = json.loads(str(msg))
    print(f"[SCHEDULER] Scheduling job: {job.get('job_id', 'unknown')}", flush=True)
    
    # Classify and route the job
    target_queue = classify(job)
    print(f"[SCHEDULER] Classification: {target_queue} (score: {estimate_cost(job):.2f})", flush=True)
    route_job(client, job, target_queue)

def main():
    print("[SCHEDULER] Starting scheduler...", flush=True)
    print(f"[SCHEDULER] Service Bus connection configured", flush=True)
    
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
                        receiver.abandon_message(msg)
    except KeyboardInterrupt:
        print("[SCHEDULER] Shutting down gracefully...", flush=True)
        client.close()

if __name__ == "__main__":
    main()

