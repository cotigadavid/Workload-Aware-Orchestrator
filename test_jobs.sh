#!/bin/bash

API_URL="http://$(minikube ip):30080"

echo "=========================================="
echo "    Testing Job Orchestration System"
echo "=========================================="
echo ""

# Function to submit job and show response
submit_job() {
    local description=$1
    local payload=$2
    
    echo "$description"
    echo "   Payload: $payload"
    
    response=$(curl -s -X POST "$API_URL/submit-job" \
      -H "Content-Type: application/json" \
      -d "$payload")
    
    echo "   Response: $response"
    echo ""
    sleep 1
}

# Test 1: Latency-sensitive job → actor-jobs
submit_job "Latency-Sensitive Job (→ actor-jobs)" \
  '{"latency_sensitive": true, "rows": 100, "estimated_runtime_sec": 1}'

# Test 2: Huge Spark job → spark-jobs
submit_job "Large Spark Job (→ spark-jobs)" \
  '{"rows": 50000000, "estimated_runtime_sec": 300, "priority": "high"}'

# Test 3: Another large job → spark-jobs
submit_job "Another Spark Job (→ spark-jobs)" \
  '{"rows": 20000000, "estimated_runtime_sec": 200, "priority": "high"}'

# Test 4: Medium ML job → ml-jobs
submit_job "Medium ML Job (→ ml-jobs)" \
  '{"rows": 5000000, "estimated_runtime_sec": 100, "priority": "normal"}'

# Test 5: Medium ML job with high priority → ml-jobs
submit_job "High Priority ML Job (→ ml-jobs)" \
  '{"rows": 3000000, "estimated_runtime_sec": 80, "priority": "high"}'

# Test 6: Small batch job → batch-jobs
submit_job "Small Batch Job (→ batch-jobs)" \
  '{"rows": 1000, "estimated_runtime_sec": 5, "priority": "normal"}'

# Test 7: Another small job → batch-jobs
submit_job "Tiny Batch Job (→ batch-jobs)" \
  '{"rows": 500, "estimated_runtime_sec": 2, "priority": "normal"}'

# Test 8: Multiple latency-sensitive jobs
for i in {1..3}; do
    submit_job "Latency Job #$i (→ actor-jobs)" \
      '{"latency_sensitive": true, "rows": 50, "estimated_runtime_sec": 1}'
done

echo ""
echo "=========================================="
echo "    Checking Queue Status"
echo "=========================================="
sleep 2

queue_status=$(curl -s "$API_URL/queues/status")
echo "$queue_status" | jq '.'
