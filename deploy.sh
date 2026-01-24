#!/bin/bash

set -e

echo "=== Checking Minikube Status ==="
if ! minikube status &> /dev/null; then
    echo "Minikube is not running!"
    echo "Starting minikube..."
    minikube start
fi

echo "Minikube is running"

echo ""
echo "=== Setting up Minikube Docker Environment ==="
eval $(minikube docker-env) 2>/dev/null || {
    echo "Warning: Could not set docker-env, trying to continue..."
    eval $(minikube -p minikube docker-env)
}

echo "Docker environment configured"

echo ""
echo "=== Building Docker Images ==="

# Build API
docker build -t localhost:5000/cloud-api:latest -f Dockerfile.api .
echo "API image built"

# Build Scheduler
docker build -t localhost:5000/cloud-scheduler:latest -f Dockerfile.scheduler .
echo "Scheduler image built"

# Build Actor Worker
docker build -t localhost:5000/cloud-actor-worker:latest \
  --build-arg WORKER_SCRIPT=actor_worker.py \
  -f Dockerfile.worker .
echo "Actor Worker image built"

# Build Spark Worker
docker build -t localhost:5000/cloud-spark-worker:latest \
  --build-arg WORKER_SCRIPT=spark_worker.py \
  -f Dockerfile.worker .
echo "Spark Worker image built"

echo ""
echo "=== Verifying Images ==="
docker images | grep cloud
echo "All images verified"

echo ""
echo "=== Creating Namespace ==="
kubectl create namespace local-infra --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "=== Deploying Infrastructure (RabbitMQ & MinIO) ==="

# Deploy RabbitMQ first
kubectl apply -f k8s/rabbitmq.yaml
echo "RabbitMQ manifest applied"

# Deploy MinIO
kubectl apply -f k8s/minio.yaml
echo "MinIO manifest applied"

echo ""
echo "=== Waiting for RabbitMQ to be ready ==="
sleep 5
kubectl wait --for=condition=ready pod -l app=rabbitmq -n local-infra --timeout=120s

echo ""
echo "=== Checking RabbitMQ connectivity ==="
kubectl run rabbitmq-test --rm -i --restart=Never --image=busybox -n local-infra -- \
  sh -c "wget -q --spider http://rabbitmq:15672 && echo 'RabbitMQ is reachable'" || echo "Warning: RabbitMQ may not be fully ready"

echo ""
echo "=== Deploying Application Services ==="
kubectl apply -f k8s/deployments.yaml
echo "Application deployments applied"

echo ""
echo "=== Forcing Pod Restart to Use New Images ==="
kubectl delete pods --all -n local-infra --grace-period=0 --force 2>/dev/null || true
sleep 5
echo "Pods restarted"

echo ""
echo "=== Waiting for pods to start (this may take a minute) ==="
sleep 15

echo ""
echo "=== Current pod status ==="
kubectl get pods -n local-infra

echo ""
echo "=== Checking pod logs for errors ==="
echo "--- API Logs ---"
kubectl logs -l app=api -n local-infra --tail=20 --prefix=true || echo "API pods not ready yet"

echo ""
echo "--- Scheduler Logs ---"
kubectl logs -l app=scheduler -n local-infra --tail=20 --prefix=true || echo "Scheduler pods not ready yet"

echo ""
echo "=== Deployment Complete! ==="
