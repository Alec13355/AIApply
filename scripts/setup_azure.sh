#!/usr/bin/env bash
# Provisions the Azure AI Foundry resource this project needs: a resource
# group, an AI Foundry (Cognitive Services "AIServices") account, and a
# chat-model deployment. Prints the values to put in .env at the end.
#
# This creates real, billable Azure resources. Review the variables below,
# then run it yourself:
#   ./scripts/setup_azure.sh
#
# Idempotent: safe to re-run, existing resources are left as-is.

set -euo pipefail

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-83fe4d36-e79b-40ed-aad7-6180a77f7e97}"  # MVP Subscription
RESOURCE_GROUP="${RESOURCE_GROUP:-aiapply-rg}"
LOCATION="${LOCATION:-eastus2}"
ACCOUNT_NAME="${ACCOUNT_NAME:-aiapply-foundry}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-gpt-5.4-mini}"
MODEL_NAME="${MODEL_NAME:-gpt-5.4-mini}"
MODEL_VERSION="${MODEL_VERSION:-2026-03-17}"
SKU_CAPACITY="${SKU_CAPACITY:-10}"

echo "== AIApply Azure AI Foundry setup =="
echo "Subscription: $SUBSCRIPTION_ID"
echo "Resource group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Account: $ACCOUNT_NAME"
echo "Deployment: $DEPLOYMENT_NAME ($MODEL_NAME @ $MODEL_VERSION)"
echo

az account set --subscription "$SUBSCRIPTION_ID"

echo "-- Resource group --"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table

echo "-- AI Foundry (Cognitive Services AIServices) account --"
if az cognitiveservices account show \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    &>/dev/null; then
  echo "Account $ACCOUNT_NAME already exists, skipping create."
else
  az cognitiveservices account create \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --kind AIServices \
    --sku S0 \
    --custom-domain "$ACCOUNT_NAME" \
    --yes \
    --output table
fi

echo "-- Model deployment --"
if az cognitiveservices account deployment show \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --deployment-name "$DEPLOYMENT_NAME" \
    &>/dev/null; then
  echo "Deployment $DEPLOYMENT_NAME already exists, skipping create."
else
  az cognitiveservices account deployment create \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --deployment-name "$DEPLOYMENT_NAME" \
    --model-name "$MODEL_NAME" \
    --model-version "$MODEL_VERSION" \
    --model-format OpenAI \
    --sku-capacity "$SKU_CAPACITY" \
    --sku-name GlobalStandard \
    --output table
fi

ENDPOINT=$(az cognitiveservices account show \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.endpoint" -o tsv)

KEY=$(az cognitiveservices account keys list \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "key1" -o tsv)

echo
echo "== Done. Put these in your .env (copy .env.example first if you haven't) =="
echo "AZURE_AI_ENDPOINT=$ENDPOINT"
echo "AZURE_AI_KEY=$KEY"
echo "AZURE_AI_DEPLOYMENT=$DEPLOYMENT_NAME"
echo "AZURE_AI_API_VERSION=2024-10-21"
