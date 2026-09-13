#!/usr/bin/env bash
# ==============================================================================
# NovaPay - AWS Cloud Node Automated Deployment Script
# Deploys the NovaPay Banking Node to AWS App Runner / ECR
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Color formatting
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}==============================================================${NC}"
echo -e "${CYAN} NovaPay AWS Cloud Node Deployment Setup                     ${NC}"
echo -e "${CYAN}==============================================================${NC}"

# 1. Check prerequisites
if ! command -v aws &> /dev/null; then
    echo -e "${RED}[ERROR] 'aws' CLI is not installed. Install it with: brew install awscli${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR] 'docker' is not installed or running.${NC}"
    exit 1
fi

# 2. Check AWS credentials
echo -e "\nChecking AWS caller identity..."
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo -e "${YELLOW}[WARNING] AWS credentials not configured or session expired.${NC}"
    echo -e "Please configure credentials with:"
    echo -e "  aws configure"
    echo -e "Or export AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION."
    echo -e "\nWould you like to run 'aws configure' now? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        aws configure
    else
        echo -e "${RED}Aborting. Configure AWS credentials and rerun this script.${NC}"
        exit 1
    fi
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="${AWS_REGION:-eu-west-1}"
ECR_REPO_NAME="${ECR_REPO_NAME:-novapay-app}"
SERVICE_NAME="${SERVICE_NAME:-novapay-aws-node}"
IMAGE_TAG="aws-$(date +%Y%m%d%H%M%S)"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO_NAME}:${IMAGE_TAG}"

echo -e "${GREEN}[OK] AWS Account:${NC} ${AWS_ACCOUNT_ID} (Region: ${AWS_REGION})"

# 3. Read environment variables from .env
if [ -f "$ROOT_DIR/.env" ]; then
    echo -e "Loading configuration secrets from .env..."
    DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    SUPABASE_URL=$(grep -E '^SUPABASE_URL=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    SUPABASE_KEY=$(grep -E '^SUPABASE_KEY=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    SECRET_KEY=$(grep -E '^SECRET_KEY=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    ENCRYPTION_KEY=$(grep -E '^ENCRYPTION_KEY=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
else
    echo -e "${RED}[ERROR] .env file not found in ${ROOT_DIR}.${NC}"
    exit 1
fi

# 4. Create ECR Repository if it doesn't exist
echo -e "\nEnsuring Amazon ECR repository exists..."
if ! aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" > /dev/null 2>&1; then
    echo -e "Creating ECR repository '$ECR_REPO_NAME'..."
    aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$AWS_REGION"
fi

# 5. Authenticate Docker with ECR
echo -e "\nAuthenticating Docker to Amazon ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# 6. Build and push Docker image
echo -e "\nBuilding Docker container image: ${IMAGE_URI}..."
cd "$ROOT_DIR"
docker build -t "$IMAGE_URI" -f Dockerfile .

echo -e "\nPushing container image to ECR..."
docker push "$IMAGE_URI"

# 7. Check or create AWS App Runner Access Role
ROLE_NAME="AppRunnerECRAccessRole"
ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"

if ! aws iam get-role --role-name "$ROLE_NAME" > /dev/null 2>&1; then
    echo -e "Creating App Runner IAM Access Role: ${ROLE_NAME}..."
    TRUST_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document "$TRUST_POLICY" > /dev/null
    aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
    sleep 5
fi

# 8. Check if App Runner Service exists
EXISTING_ARN=$(aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" --output text || true)

if [ -n "$EXISTING_ARN" ] && [ "$EXISTING_ARN" != "None" ]; then
    echo -e "\nUpdating existing App Runner service: ${SERVICE_NAME} (${EXISTING_ARN})..."
    aws apprunner update-service \
        --service-arn "$EXISTING_ARN" \
        --source-configuration "{
            \"ImageRepository\": {
                \"ImageIdentifier\": \"${IMAGE_URI}\",
                \"ImageConfiguration\": {
                    \"Port\": \"8080\",
                    \"RuntimeEnvironmentVariables\": {
                        \"PRIMARY_CLOUD\": \"aws\",
                        \"FLASK_ENV\": \"production\",
                        \"PORT\": \"8080\",
                        \"DATABASE_URL\": \"${DATABASE_URL}\",
                        \"SUPABASE_URL\": \"${SUPABASE_URL}\",
                        \"SUPABASE_KEY\": \"${SUPABASE_KEY}\",
                        \"SECRET_KEY\": \"${SECRET_KEY}\",
                        \"ENCRYPTION_KEY\": \"${ENCRYPTION_KEY}\",
                        \"BEHIND_PROXY\": \"1\"
                    }
                },
                \"ImageRepositoryType\": \"ECR\"
            }
        }" --region "$AWS_REGION"
    SERVICE_ARN="$EXISTING_ARN"
else
    echo -e "\nCreating new App Runner service: ${SERVICE_NAME}..."
    SERVICE_ARN=$(aws apprunner create-service \
        --service-name "$SERVICE_NAME" \
        --source-configuration "{
            \"AuthenticationConfiguration\": {
                \"AccessRoleArn\": \"${ROLE_ARN}\"
            },
            \"AutoDeploymentsEnabled\": false,
            \"ImageRepository\": {
                \"ImageIdentifier\": \"${IMAGE_URI}\",
                \"ImageConfiguration\": {
                    \"Port\": \"8080\",
                    \"RuntimeEnvironmentVariables\": {
                        \"PRIMARY_CLOUD\": \"aws\",
                        \"FLASK_ENV\": \"production\",
                        \"PORT\": \"8080\",
                        \"DATABASE_URL\": \"${DATABASE_URL}\",
                        \"SUPABASE_URL\": \"${SUPABASE_URL}\",
                        \"SUPABASE_KEY\": \"${SUPABASE_KEY}\",
                        \"SECRET_KEY\": \"${SECRET_KEY}\",
                        \"ENCRYPTION_KEY\": \"${ENCRYPTION_KEY}\",
                        \"BEHIND_PROXY\": \"1\"
                    }
                },
                \"ImageRepositoryType\": \"ECR\"
            }
        }" \
        --health-check-configuration "{
            \"Protocol\": \"HTTP\",
            \"Path\": \"/health\",
            \"Interval\": 10,
            \"Timeout\": 5,
            \"HealthyThreshold\": 1,
            \"UnhealthyThreshold\": 3
        }" \
        --region "$AWS_REGION" \
        --query "Service.ServiceArn" --output text)
fi

echo -e "\nWaiting for AWS App Runner service URL..."
SERVICE_URL=""
for i in {1..30}; do
    SERVICE_URL=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query "Service.ServiceUrl" --output text || true)
    SERVICE_STATUS=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query "Service.Status" --output text || true)
    if [ -n "$SERVICE_URL" ] && [ "$SERVICE_URL" != "None" ]; then
        break
    fi
    echo -e "Status: ${SERVICE_STATUS:-pending}... waiting 10s ($i/30)"
    sleep 10
done

PUBLIC_AWS_URL="https://${SERVICE_URL}"

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN} AWS Node Deployed Successfully!                              ${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "Public Endpoint:  ${CYAN}${PUBLIC_AWS_URL}${NC}"
echo -e "Health Check URL: ${CYAN}${PUBLIC_AWS_URL}/health${NC}"
echo -e "\nTo connect NovaPay to this live host, set in your .env:"
echo -e "${BOLD}AWS_URL=${PUBLIC_AWS_URL}${NC}"
