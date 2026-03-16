#!/usr/bin/env bash

# Usage:
# ./check_blob_retention.sh <resource-group> <storage-account>

RESOURCE_GROUP=$1
STORAGE_ACCOUNT=$2

if [ -z "$RESOURCE_GROUP" ] || [ -z "$STORAGE_ACCOUNT" ]; then
  echo "Usage: $0 <resource-group> <storage-account>"
  exit 1
fi

echo "========================================"
echo "Checking retention settings for:"
echo "Storage Account: $STORAGE_ACCOUNT"
echo "Resource Group : $RESOURCE_GROUP"
echo "========================================"

echo ""
echo "1️⃣ Blob Service Properties"
az storage account blob-service-properties show \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --output table

echo ""
echo "2️⃣ Lifecycle Management Policy"
POLICY=$(az storage account management-policy show \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query policy.rules \
  --output json 2>/dev/null)

if [ -z "$POLICY" ] || [ "$POLICY" == "null" ]; then
  echo "No lifecycle management policy configured."
else
  echo "$POLICY" | jq
fi

echo ""
echo "3️⃣ Container Immutability Policies"

CONTAINERS=$(az storage container list \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  --query "[].name" \
  -o tsv)

for container in $CONTAINERS; do
  echo ""
  echo "Container: $container"

  az storage container immutability-policy show \
    --account-name "$STORAGE_ACCOUNT" \
    --container-name "$container" \
    --auth-mode login \
    --output table 2>/dev/null || echo "No immutability policy"
done

echo ""
echo "========================================"
echo "Retention policy check completed"
echo "========================================"