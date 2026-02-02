# Navigate to project directory
cd /home/david/Desktop/Cloud

# Check AKS cluster status
az aks show \
  --resource-group orchestrator-rg \
  --name orchestrator-aks \
  --query '[provisioningState,powerState.code]' \
  -o table


# Get AKS credentials
az aks get-credentials \
  --resource-group orchestrator-rg \
  --name orchestrator-aks \
  --overwrite-existing

# Check all pods are running
kubectl get pods -n local-infra


# If any pods are not running, restart them:
kubectl rollout restart deployment/api -n local-infra
kubectl rollout restart deployment/scheduler -n local-infra


# Verify Batch pool exists and is at 0 nodes (idle state)
az batch pool show \
  --pool-id spark-pool \
  --account-name orchestratorbatch123 \
  --query '[id,state,currentDedicatedNodes,targetDedicatedNodes,enableAutoScale]' \
  -o table

# Open a new terminal window and run:
kubectl port-forward -n local-infra svc/api 8000:8000

#Terminal 1 (Top Left)**: Scheduler logs
kubectl logs -f -l app=scheduler -n local-infra --tail=20


#Terminal 2 (Top Right)**: Azure Batch pool monitoring
watch -n 5 'az batch pool show \
  --pool-id spark-pool \
  --account-name orchestratorbatch123 \
  --query "{CurrentNodes:currentDedicatedNodes,TargetNodes:targetDedicatedNodes,State:allocationState}" \
  -o table'


#Terminal 3 (Bottom Left)**: KEDA HPA status
watch -n 2 'kubectl get hpa -n local-infra'


#Execute in Terminal 4**:
curl -X POST http://localhost:8000/submit-job \
  -H "Content-Type: application/json" \
  -d '{"rows": 1000, "estimated_runtime_sec": 5, "job_type": "actor"}' \
  | jq


#Execute in Terminal 4**:
curl -X POST http://localhost:8000/submit-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "spark",
    "rows": 50000000,
    "estimated_runtime_sec": 300,
    "priority": "normal"
  }' | jq


#Execute in Terminal 4**:
# Submit 5 large Spark jobs
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/submit-job \
    -H "Content-Type: application/json" \
    -d "{\"job_type\": \"spark\", \"rows\": 80000000, \"estimated_runtime_sec\": 400}" \
    | jq -r '.job_id'
  echo "Job $i submitted"
done

# Submit 5 ML jobs
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/submit-job \
    -H "Content-Type: application/json" \
    -d "{\"job_type\": \"ml\", \"rows\": 5000000, \"estimated_runtime_sec\": 100}" \
    | jq -r '.job_id'
  echo "ML job $i submitted"
done

# Submit 5 Actor jobs
for i in {1..20}; do
  curl -s -X POST http://localhost:8000/submit-job \
    -H "Content-Type: application/json" \
    -d "{\"job_type\": \"actor\", \"rows\": 5000, \"estimated_runtime_sec\": 5}" \
    | jq -r '.job_id'
  echo "Actor job $i submitted"
done