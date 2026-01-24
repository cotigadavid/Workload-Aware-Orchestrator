import pika
import time
import os
from kubernetes import client, config

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
NAMESPACE = "local-infra"
CHECK_INTERVAL = 10  # seconds

# Scaling thresholds
ACTOR_THRESHOLD = 5
SPARK_THRESHOLD = 3
MAX_REPLICAS = 10
MIN_REPLICAS = 1

def get_queue_depth(queue_name):
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    queue = channel.queue_declare(queue=queue_name, durable=True, passive=True)
    connection.close()
    return queue.method.message_count

def scale_deployment(deployment_name, replicas):
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config()
    
    apps_v1 = client.AppsV1Api()
    
    deployment = apps_v1.read_namespaced_deployment(deployment_name, NAMESPACE)
    current_replicas = deployment.spec.replicas
    
    if current_replicas != replicas:
        deployment.spec.replicas = replicas
        apps_v1.patch_namespaced_deployment(deployment_name, NAMESPACE, deployment)
        print(f"Scaled {deployment_name} from {current_replicas} to {replicas}")

def calculate_needed_replicas(queue_depth, threshold):
    if queue_depth == 0:
        return MIN_REPLICAS
    needed = (queue_depth // threshold) + 1
    return min(max(needed, MIN_REPLICAS), MAX_REPLICAS)

def main():
    print("Orchestrator started - monitoring queues and scaling workers...")
    
    while True:
        try:
            actor_depth = get_queue_depth("actor-jobs")
            spark_depth = get_queue_depth("spark-jobs")
            
            actor_replicas = calculate_needed_replicas(actor_depth, ACTOR_THRESHOLD)
            spark_replicas = calculate_needed_replicas(spark_depth, SPARK_THRESHOLD)
            
            print(f"Actor queue: {actor_depth}, needed replicas: {actor_replicas}")
            print(f"Spark queue: {spark_depth}, needed replicas: {spark_replicas}")
            
            scale_deployment("actor-worker", actor_replicas)
            scale_deployment("spark-worker", spark_replicas)
            
        except Exception as e:
            print(f"Error in orchestrator: {e}")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
