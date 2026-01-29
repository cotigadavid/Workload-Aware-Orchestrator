import pika
import json
import time
import os
import sys

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
QUEUE_NAME = "actor-jobs"
MAX_RETRIES = 10
RETRY_DELAY = 5

def connect_with_retry():
    """Connect to RabbitMQ with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[ACTOR] Attempting to connect to RabbitMQ (attempt {attempt + 1}/{MAX_RETRIES})...", flush=True)
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            print("[ACTOR] Successfully connected to RabbitMQ", flush=True)
            return connection
        except Exception as e:
            print(f"[ACTOR] Connection failed: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"[ACTOR] Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print("[ACTOR] Max retries reached. Exiting.")
                sys.exit(1)

def process_job(job: dict):
    """Process actor job - low latency, lightweight tasks"""
    job_id = job.get("job_id", "unknown")
    payload = job.get("payload", {})
    
    print(f"[ACTOR] Processing job {job_id}", flush=True)
    print(f"[ACTOR] Payload: {payload}", flush=True)
    
    # Simulate processing
    time.sleep(1)
    
    print(f"[ACTOR] Completed job {job_id}", flush=True)

def process_message(receiver, msg):
    try:
        job = json.loads(str(msg))
        process_job(job)
        receiver.complete_message(msg)
    except Exception as e:
        print(f"[ACTOR] Error: {e}", flush=True)
        receiver.abandon_message(msg)

def main():
    print("[ACTOR] Starting actor worker...", flush=True)
    print(f"[ACTOR] Service Bus connection configured", flush=True)
    
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
