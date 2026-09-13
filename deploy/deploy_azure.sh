#!/usr/bin/env bash
# ==============================================================================
# NovaPay - Azure Cloud Node Automated Deployment Script
# Deploys the NovaPay Banking Node to Azure App Service (Linux Container)
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
echo -e "${CYAN} NovaPay Azure Cloud Node Deployment Setup                   ${NC}"
echo -e "${CYAN}==============================================================${NC}"

# 1. Check prerequisites
if ! command -v az &> /dev/null; then
    echo -e "${RED}[ERROR] 'az' CLI is not installed. Install it with: brew install azure-cli${NC}"
    exit 1
fi

# 2. Check Azure credentials
echo -e "\nChecking Azure account authentication..."
if ! az account show > /dev/null 2>&1; then
    echo -e "${YELLOW}[WARNING] Azure CLI not logged in.${NC}"
    echo -e "Please log in to your Azure account by running:"
    echo -e "  az login"
    echo -e "\nWould you like to run 'az login' now? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        az login
    else
        echo -e "${RED}Aborting. Log in to Azure and rerun this script.${NC}"
        exit 1
    fi
fi

SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo -e "${GREEN}[OK] Active Azure Subscription:${NC} ${SUBSCRIPTION_NAME} (${SUBSCRIPTION_ID})"

# Deployment variables
RESOURCE_GROUP="${AZURE_RG:-novapay-rg}"
LOCATION="${AZURE_LOCATION:-uksouth}"
# ACR names must be alphanumeric only
RANDOM_SUFFIX=$(echo "$SUBSCRIPTION_ID" | tr -d '-' | cut -c 1-6)
ACR_NAME="${AZURE_ACR:-novapayacr${RANDOM_SUFFIX}}"
APP_SERVICE_PLAN="${AZURE_PLAN:-novapay-asp}"
APP_NAME="${AZURE_APP_NAME:-novapay-azure-${RANDOM_SUFFIX}}"

echo -e "Target Configuration:"
echo -e "  Resource Group:   ${RESOURCE_GROUP}"
echo -e "  Location:         ${LOCATION}"
echo -e "  Container Registry: ${ACR_NAME}"
echo -e "  App Service Name: ${APP_NAME}"

# 3. Read environment variables from .env
if [ -f "$ROOT_DIR/.env" ]; then
    echo -e "\nLoading configuration secrets from .env..."
    DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    SUPABASE_URL=$(grep -E '^SUPABASE_URL=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    SUPABASE_KEY=$(grep -E '^SUPABASE_KEY=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    SECRET_KEY=$(grep -E '^SECRET_KEY=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
    ENCRYPTION_KEY=$(grep -E '^ENCRYPTION_KEY=' "$ROOT_DIR/.env" | cut -d'=' -f2-)
else
    echo -e "${RED}[ERROR] .env file not found in ${ROOT_DIR}.${NC}"
    exit 1
fi

# 4. Create Resource Group
echo -e "\nCreating Azure Resource Group '$RESOURCE_GROUP' in '$LOCATION'..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o table

# 5. Create Azure Container Registry (ACR)
echo -e "\nChecking / Creating Azure Container Registry '$ACR_NAME'..."
if ! az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true -o table
fi

# 6. Build and push image to ACR using cloud-native build
echo -e "\nBuilding Docker container image in ACR (no local docker daemon required)..."
cd "$ROOT_DIR"
az acr build --registry "$ACR_NAME" --image novapay-app:latest .

# Retrieve ACR credentials
ACR_SERVER="${ACR_NAME}.azurecr.io"
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

# 7. Create App Service Plan (Linux)
echo -e "\nChecking / Creating Linux App Service Plan '$APP_SERVICE_PLAN'..."
if ! az appservice plan show --name "$APP_SERVICE_PLAN" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    az appservice plan create --name "$APP_SERVICE_PLAN" --resource-group "$RESOURCE_GROUP" --is-linux --sku B1 -o table
fi

# 8. Create Web App for Containers
echo -e "\nCreating / Updating Web App '$APP_NAME'..."
IMAGE_FULL="${ACR_SERVER}/novapay-app:latest"

if ! az webapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    az webapp create \
        --resource-group "$RESOURCE_GROUP" \
        --plan "$APP_SERVICE_PLAN" \
        --name "$APP_NAME" \
        --deployment-container-image-name "$IMAGE_FULL" \
        -o table
fi

# 9. Configure Container Credentials and App Settings
echo -e "\nConfiguring Web App settings and environment variables..."
az webapp config container set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --docker-custom-image-name "$IMAGE_FULL" \
    --docker-registry-server-url "https://${ACR_SERVER}" \
    --docker-registry-server-user "$ACR_USERNAME" \
    --docker-registry-server-password "$ACR_PASSWORD" \
    -o table

az webapp config appsettings set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings \
        PRIMARY_CLOUD="azure" \
        FLASK_ENV="production" \
        WEBSITES_PORT="5000" \
        PORT="5000" \
        DATABASE_URL="${DATABASE_URL}" \
        SUPABASE_URL="${SUPABASE_URL}" \
        SUPABASE_KEY="${SUPABASE_KEY}" \
        SECRET_KEY="${SECRET_KEY}" \
        ENCRYPTION_KEY="${ENCRYPTION_KEY}" \
        BEHIND_PROXY="1" \
    -o table

# Configure health check endpoint
echo -e "\nSetting health check path to /health..."
az webapp config set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$APP_NAME" \
    --generic-configurations '{"healthCheckPath": "/health"}' \
    -o table

PUBLIC_AZURE_URL="https://${APP_NAME}.azurewebsites.net"

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN} Azure Node Deployed Successfully!                            ${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "Public Endpoint:  ${CYAN}${PUBLIC_AZURE_URL}${NC}"
echo -e "Health Check URL: ${CYAN}${PUBLIC_AZURE_URL}/health${NC}"
echo -e "\nTo connect NovaPay to this live host, set in your .env:"
echo -e "${BOLD}AZURE_URL=${PUBLIC_AZURE_URL}${NC}"
