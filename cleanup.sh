#!/bin/bash

echo "Cleaning up deployments..."

kubectl delete namespace local-infra --ignore-not-found=true

echo "All resources deleted"
