#!/bin/bash

echo "System Diagnostics"


echo "=== Pod Status ==="
kubectl get pods -n local-infra -o wide

echo ""
echo "=== Failing Pod Details ==="
for pod in $(kubectl get pods -n local-infra --field-selector=status.phase!=Running -o jsonpath='{.items[*].metadata.name}'); do
    echo ""
    echo "--- Pod: $pod ---"
    kubectl describe pod $pod -n local-infra | tail -20
done

echo ""
echo "=== Recent Pod Logs ==="

echo ""
echo "--- API Logs ---"
kubectl logs -l app=api -n local-infra --tail=50 --all-containers=true || echo "No API logs available"

echo ""
echo "--- Scheduler Logs ---"
kubectl logs -l app=scheduler -n local-infra --tail=50 --all-containers=true || echo "No Scheduler logs available"

echo ""
echo "--- Actor Worker Logs ---"
kubectl logs -l app=actor-worker -n local-infra --tail=50 --all-containers=true || echo "No Actor Worker logs available"

echo ""
echo "--- Spark Worker Logs ---"
kubectl logs -l app=spark-worker -n local-infra --tail=50 --all-containers=true || echo "No Spark Worker logs available"

echo ""
echo "--- RabbitMQ Logs ---"
kubectl logs -l app=rabbitmq -n local-infra --tail=30 || echo "No RabbitMQ logs available"

echo ""
echo "=== Service Endpoints ==="
kubectl get svc -n local-infra

echo ""
echo "=== Events (last 10) ==="
kubectl get events -n local-infra --sort-by='.lastTimestamp' | tail -10
