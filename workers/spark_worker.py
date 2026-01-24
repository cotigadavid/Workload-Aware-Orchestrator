import pika
import json
import time
import os
import sys

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
QUEUE_NAME = "spark-jobs"
MAX_RETRIES = 10
RETRY_DELAY = 5

def connect_with_retry():
    """Connect to RabbitMQ with retries"""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[SPARK] Attempting to connect to RabbitMQ (attempt {attempt + 1}/{MAX_RETRIES})...")
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            print("[SPARK] Successfully connected to RabbitMQ")
            return connection
        except Exception as e:
            print(f"[SPARK] Connection failed: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"[SPARK] Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print("[SPARK] Max retries reached. Exiting.")
                sys.exit(1)

def process_job(job: dict):
    """Process spark job - high compute, data-intensive tasks"""
    job_id = job.get("job_id", "unknown")
    payload = job.get("payload", {})
    
    print(f"[SPARK] Processing job {job_id}")
    print(f"[SPARK] Rows: {payload.get('rows', 'N/A')}")
    print(f"[SPARK] Estimated runtime: {payload.get('estimated_runtime_sec', 'N/A')}s")
    
    # Simulate heavy processing
    runtime = payload.get("estimated_runtime_sec", 5)
    time.sleep(min(runtime, 10))  # Cap at 10s for testing
    
    print(f"[SPARK] Completed job {job_id}")

def callback(ch, method, properties, body):
    try:
        job = json.loads(body)
        process_job(job)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"[SPARK] Error: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    print("[SPARK] Starting spark worker...")
    print(f"[SPARK] RabbitMQ URL: {RABBITMQ_URL}")
    
    connection = connect_with_retry()
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    
    print(f"[SPARK] Worker listening on {QUEUE_NAME}...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("[SPARK] Shutting down gracefully...")
        channel.stop_consuming()
        connection.close()

if __name__ == "__main__":
    main()
