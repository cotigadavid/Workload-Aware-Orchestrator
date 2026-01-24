#!/bin/bash

API_URL="http://$(minikube ip):30080"


while true; do
    clear
    echo "=========================================="
    echo "    Queue Status - $(date '+%H:%M:%S')"
    echo "=========================================="
    
    curl -s "$API_URL/queues/status" | jq -r '
        "Intake Queue:    \(.jobqueue) jobs",
        "Actor Queue:     \(."actor-jobs") jobs",
        "Spark Queue:     \(."spark-jobs") jobs",
        "ML Queue:        \(."ml-jobs") jobs",
        "Batch Queue:     \(."batch-jobs") jobs"
    '
    
    echo ""
    echo "=========================================="
    echo "    Pod Status"
    echo "=========================================="
    kubectl get pods -n local-infra -o wide | grep -v "NAME" | awk '{printf "%-20s %-10s %-8s\n", $1, $3, $4}'
    
    echo ""
    echo "=========================================="
    echo "    Resource Usage"
    echo "=========================================="
    kubectl top pods -n local-infra 2>/dev/null | grep -E "actor-worker|spark-worker" || echo "Metrics not ready yet..."
    
    sleep 2
done
