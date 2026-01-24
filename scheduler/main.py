import pika
import json
import time
import sys
import os

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
MAX_RETRIES = 10
RETRY_DELAY = 5

def connect_with_retry():
    """Connect to RabbitMQ with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[SCHEDULER] Attempting to connect to RabbitMQ (attempt {attempt + 1}/{MAX_RETRIES})...")
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            print("[SCHEDULER] Successfully connected to RabbitMQ")
            return connection
        except Exception as e:
            print(f"[SCHEDULER] Connection failed: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"[SCHEDULER] Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print("[SCHEDULER] Max retries reached. Exiting.")
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

def route_job(ch, job: dict, target_queue: str):
    """Route job to the appropriate queue"""
    ch.queue_declare(queue=target_queue, durable=True)
    ch.basic_publish(
        exchange="",
        routing_key=target_queue,
        body=json.dumps(job),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    print(f"[SCHEDULER] Routed job to {target_queue}: {job.get('job_id', 'unknown')}")

def callback(ch, method, properties, body):
    job = json.loads(body)
    print(f"[SCHEDULER] Scheduling job: {job.get('job_id', 'unknown')}")
    
    # Classify and route the job
    target_queue = classify(job)
    print(f"[SCHEDULER] Classification: {target_queue} (score: {estimate_cost(job):.2f})")
    route_job(ch, job, target_queue)
    
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print("[SCHEDULER] Starting scheduler...")
    print(f"[SCHEDULER] RabbitMQ URL: {RABBITMQ_URL}")
    
    conn = connect_with_retry()
    ch = conn.channel()
    ch.queue_declare(queue="jobqueue", durable=True)
    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue="jobqueue", on_message_callback=callback, auto_ack=False)

    print("[SCHEDULER] Listening for jobs...")
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        print("[SCHEDULER] Shutting down gracefully...")
        ch.stop_consuming()
        conn.close()

if __name__ == "__main__":
    main()

