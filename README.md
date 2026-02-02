# Cloud Job Orchestrator

A hybrid job-orchestration platform that classifies workloads and routes them to the most cost‑effective execution environment. Latency‑sensitive and medium workloads run on AKS with KEDA autoscaling, while heavy Spark/ML and batch workloads are offloaded to Azure Batch for elastic, serverless compute. The system provides a single API for submission, end‑to‑end routing, and observability across both paths.

### Job Modeling
Rather than using real-world jobs, this project employs an **abstracted model**. Each job is represented by a JSON object consisting of the following key attributes:

* **`nr_of_rows`**: Mimics the job size (data volume).
* **`estimated_runtime`**: Represents the predicted duration of the task.
* **`priority`**: Defines the execution urgency of the job.
* **`latency_sensitivity`**: Indicates the timing criticality of the process.

## Architecture

- **API**: FastAPI service for job submission
- **Scheduler**: Job classifier that routes jobs to appropriate queues based on workload characteristics
- **Workers (AKS)**:
  - **Actor Worker**: Handles latency-sensitive, lightweight jobs
  - **Spark Worker**: Handles data-intensive, high-compute jobs
- **Azure Batch**: Serverless execution for heavy Spark/ML and batch workloads
- **Batch Submitter**: Bridges `batch-jobs`/`ml-jobs` queues to Azure Batch
- **Message Queue**: Azure Service Bus (production) or RabbitMQ (local)
- **Autoscaling**: KEDA ScaledObjects monitoring queue depth
- **Storage**: Azure Blob Storage (production) or MinIO (local)

## Features

- **Intelligent Job Classification**: Routes jobs based on:
  - Latency sensitivity
  - Data volume (number of rows)
  - Estimated runtime
  - Priority level
- **Hybrid Execution**: AKS for low/medium latency jobs, Azure Batch for large jobs
- **Dynamic Autoscaling**: Workers scale 1-10 replicas based on queue depth
- **Azure-Native**: Uses Azure Service Bus, AKS, ACR, Azure Batch, and Blob Storage

## Repository Layout

- **Dockerfiles**: Stored in `dockerfiles/`
- **Automation scripts**: Stored in `scripts/`

## Prerequisites

### For Local Development
- Docker
- Minikube
- kubectl
- Python 3.11+

### For Azure Deployment
- Azure subscription
- Azure CLI (`az`)
- Docker with buildx support
- kubectl
- Terraform (optional, for infrastructure provisioning)

## Quick Start (Azure Batch Hybrid)

For a full end‑to‑end deployment (AKS + Azure Batch + Service Bus + Storage), run:

```bash
./scripts/deploy_batch.sh
```

This script provisions infrastructure via Terraform, builds and pushes images, creates secrets, and deploys workloads.

## Setup Instructions

### 1. Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` and fill in your Azure resource values:
- `AZURE_SUBSCRIPTION_ID`: Your Azure subscription ID
- `ACR_NAME`: Your Azure Container Registry name (e.g., `myacr123`)
- `ACR_LOGIN_SERVER`: Your ACR login server (e.g., `myacr123.azurecr.io`)
- `AKS_CLUSTER_NAME`: Your AKS cluster name
- `AKS_RESOURCE_GROUP`: Resource group containing the AKS cluster
- `SERVICEBUS_NAMESPACE`: Azure Service Bus namespace name
- `SERVICEBUS_CONNECTION_STRING`: Service Bus connection string (from Azure Portal)
- `AZURE_STORAGE_CONNECTION_STRING`: Azure Storage connection string

### 2. Azure Infrastructure Setup

#### Option A: Using Terraform (Recommended)

```bash
cd infra
terraform init
terraform plan
terraform apply
```

This creates:
- Resource group
- AKS cluster
- Azure Container Registry
- Azure Service Bus namespace
- Azure Storage account
- Azure Batch account (for hybrid execution)

#### Option B: Manual Setup

```bash
# Set variables
RESOURCE_GROUP="orchestrator-rg"
LOCATION="germanywestcentral"
AKS_NAME="orchestrator-aks"
ACR_NAME="<your-unique-acr-name>"
SERVICEBUS_NS="<your-unique-sb-namespace>"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create ACR
az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic

# Create AKS cluster (ARM64 nodes for cost efficiency)
az aks create \
  --resource-group $RESOURCE_GROUP \
  --name $AKS_NAME \
  --node-count 2 \
  --node-vm-size Standard_B2ps_v2 \
  --generate-ssh-keys

# Attach ACR to AKS
az aks update --name $AKS_NAME --resource-group $RESOURCE_GROUP --attach-acr $ACR_NAME

# Create Service Bus namespace
az servicebus namespace create \
  --resource-group $RESOURCE_GROUP \
  --name $SERVICEBUS_NS \
  --location $LOCATION \
  --sku Standard

# Create queues
for queue in jobqueue actor-jobs spark-jobs ml-jobs batch-jobs; do
  az servicebus queue create \
    --resource-group $RESOURCE_GROUP \
    --namespace-name $SERVICEBUS_NS \
    --name $queue
done

# Get connection string
az servicebus namespace authorization-rule keys list \
  --resource-group $RESOURCE_GROUP \
  --namespace-name $SERVICEBUS_NS \
  --name RootManageSharedAccessKey \
  --query primaryConnectionString -o tsv
```

### 3. Build and Push Docker Images

```bash
# Load environment variables
source .env

# Login to ACR
az acr login --name $ACR_NAME

# Build images for ARM64 (if your AKS uses ARM nodes)
docker buildx build --platform linux/arm64 \
  -t ${ACR_LOGIN_SERVER}/cloud-api:latest \
  -f dockerfiles/Dockerfile.api --push .

docker buildx build --platform linux/arm64 \
  -t ${ACR_LOGIN_SERVER}/cloud-scheduler:latest \
  -f dockerfiles/Dockerfile.scheduler --push .

docker buildx build --platform linux/arm64 \
  --build-arg WORKER_SCRIPT=actor_worker.py \
  -t ${ACR_LOGIN_SERVER}/cloud-actor-worker:latest \
  -f dockerfiles/Dockerfile.worker --push .

docker buildx build --platform linux/arm64 \
  --build-arg WORKER_SCRIPT=spark_worker.py \
  -t ${ACR_LOGIN_SERVER}/cloud-spark-worker:latest \
  -f dockerfiles/Dockerfile.worker --push .
```

### 4. Update Kubernetes Manifests

Replace `<ACR_LOGIN_SERVER>` in `k8s/deployments.yaml` with your actual ACR login server:

```bash
sed -i "s|<ACR_LOGIN_SERVER>|${ACR_LOGIN_SERVER}|g" k8s/deployments.yaml
```

Or manually edit the file and replace all occurrences.

### 5. Create Kubernetes Secrets

```bash
# Get AKS credentials
az aks get-credentials --resource-group $AKS_RESOURCE_GROUP --name $AKS_CLUSTER_NAME

# Create namespace
kubectl create namespace local-infra

# Create Service Bus secret
kubectl create secret generic servicebus-conn \
  --from-literal=connection-string="$SERVICEBUS_CONNECTION_STRING" \
  -n local-infra

# Create Storage secret
kubectl create secret generic storage-conn \
  --from-literal=connection-string="$AZURE_STORAGE_CONNECTION_STRING" \
  -n local-infra
```

### 6. Install KEDA (for autoscaling)

```bash
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.18.3/keda-2.18.3.yaml
```

Wait for KEDA pods to be ready:
```bash
kubectl wait --for=condition=ready pod -l app=keda-operator -n keda --timeout=180s
```

### 7. Deploy Application

```bash
# Deploy services
kubectl apply -f k8s/deployments.yaml

# Deploy KEDA scalers
kubectl apply -f k8s/actor-scaler.yaml
kubectl apply -f k8s/spark-scaler.yaml

# Check deployment status
kubectl get pods -n local-infra
kubectl get svc -n local-infra
```

### 8. Get API External IP

```bash
kubectl get svc api-service -n local-infra
```

Wait for `EXTERNAL-IP` to be assigned (may take a few minutes). Once available, you can access the API at `http://<EXTERNAL-IP>:8000`.

## Usage

### Submit Jobs

```bash
API_URL="http://<EXTERNAL-IP>:8000"

# Submit a latency-sensitive job (routed to actor-jobs queue)
curl -X POST "$API_URL/submit-job" \
  -H "Content-Type: application/json" \
  -d '{"latency_sensitive": true, "rows": 100, "estimated_runtime_sec": 1}'

# Submit a large Spark job (routed to spark-jobs queue)
curl -X POST "$API_URL/submit-job" \
  -H "Content-Type: application/json" \
  -d '{"rows": 50000000, "estimated_runtime_sec": 300, "priority": "high"}'

# Submit a medium ML job (routed to ml-jobs queue)
curl -X POST "$API_URL/submit-job" \
  -H "Content-Type: application/json" \
  -d '{"rows": 5000000, "estimated_runtime_sec": 100, "priority": "normal"}'
```

### Check Queue Status

```bash
curl "$API_URL/queues/status" | jq .
```

### Monitor Autoscaling

```bash
# Watch HPA metrics
kubectl get hpa -n local-infra -w

# Watch pod count
kubectl get pods -n local-infra -w -l app=actor-worker
kubectl get pods -n local-infra -w -l app=spark-worker
```

## Job Classification Logic

The scheduler classifies jobs using a cost estimation algorithm:

```
cost = (rows / 1_000_000) + (estimated_runtime_sec / 10)
if priority == "high": cost *= 1.5

if latency_sensitive:
  → actor-jobs queue
elif cost > 10:
  → spark-jobs queue
elif cost > 4:
  → ml-jobs queue
else:
  → batch-jobs queue (Azure Batch)
```

## Autoscaling Behavior

- **Actor Worker**: Scales based on `actor-jobs` queue depth (target: 5 messages per replica)
- **Spark Worker**: Scales based on `spark-jobs` queue depth (target: 3 messages per replica)
- **Range**: 1-10 replicas per worker type
- **Scale-down**: Gradual cooldown to prevent flapping

## Local Development

For local testing with Minikube:

1. Start Minikube:
   ```bash
   minikube start
   ```

2. Deploy RabbitMQ instead of Service Bus:
   ```bash
   kubectl apply -f k8s/rabbitmq.yaml
   kubectl apply -f k8s/minio.yaml
   ```

3. Use the local deployment script:
   ```bash
   ./scripts/deploy.sh
   ```

4. Access API via Minikube:
   ```bash
   minikube service api-service -n local-infra
   ```
