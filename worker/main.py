import time
import pika
import json

RABBITMQ_URL = "amqp://guest:guest@rabbitmq:5672/"

def callback(ch, method, properties, body):
    job = json.loads(body)
    print("Executing job:", job)
    time.sleep(3)
    print("Job done")

conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
ch = conn.channel()
ch.queue_declare(queue="jobqueue")
ch.basic_consume(queue="jobqueue", on_message_callback=callback, auto_ack=True)

print("Worker ready...")
ch.start_consuming()
