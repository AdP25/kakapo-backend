#!/usr/bin/env bash
# deploy.sh — Build, push, and deploy Kakapo to AWS ECS
# Usage: ./deploy.sh <aws-region> <aws-account-id>
# Prerequisites: aws cli, docker, terraform installed and authenticated

set -euo pipefail

REGION="${1:-us-east-1}"
ACCOUNT_ID="${2:?Please pass your AWS account ID as second argument}"
ENV="${3:-dev}"
APP="kakapo-${ENV}"
IMAGE_TAG="latest"
ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${APP}-api"

echo "==> Logging into ECR..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Building Docker image..."
docker build -t "${APP}-api" .

echo "==> Tagging and pushing to ECR..."
docker tag "${APP}-api:latest" "${ECR_URL}:${IMAGE_TAG}"
docker push "${ECR_URL}:${IMAGE_TAG}"

echo "==> Forcing ECS service update..."
aws ecs update-service \
  --cluster "${APP}-cluster" \
  --service "${APP}-api" \
  --force-new-deployment \
  --region "$REGION" \
  --output text --query 'service.serviceArn'

echo ""
echo "==> Done. New deployment rolling out."
echo "    Monitor: https://console.aws.amazon.com/ecs/home?region=${REGION}#/clusters/${APP}-cluster/services"
