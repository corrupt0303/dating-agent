#!/bin/bash
set -e

# Azure deployment script for Dating Agent (multi-service, static hosting, env selection)
# Usage:
#   ./deploy-azure.sh --backend [--env <file>]         # Deploy only backend
#   ./deploy-azure.sh --frontend [--env <file>]        # Deploy only frontend (App Service)
#   ./deploy-azure.sh --frontend-static [--env <file>] # Deploy only frontend (Static Web App)
#   ./deploy-azure.sh                                  # Deploy all
# Logs all steps and results to azure-deploy.log

ENV_NAME="datingagent-dev"
LOG_FILE="azure-deploy.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "==== Azure Deploy Script Started: $(date) ===="

if ! command -v azd &> /dev/null; then
  echo "azd (Azure Developer CLI) not found. Please install it first."
  exit 1
fi

if [ ! -f "azure.yaml" ]; then
  echo "Initializing azd project..."
  azd init --template empty --environment $ENV_NAME --infra infra/
fi

# Parse args
ACTION="all"
ENV_FILE=""
for arg in "$@"; do
  case $arg in
    --backend|--frontend|--frontend-static)
      ACTION=${arg#--}
      ;;
    --env)
      shift
      ENV_FILE="$1"
      ;;
  esac
  shift
done

prompt_env_vars() {
  echo "Prompting for environment variables (leave blank to skip)"
  while true; do
    read -p "Enter variable name (or press Enter to finish): " key
    [ -z "$key" ] && break
    read -p "Enter value for $key: " value
    azd env set "$key" "$value"
  done
}

load_env_file() {
  local env_file="$1"
  if [ ! -f "$env_file" ]; then
    echo "$env_file not found. Skipping env sync."
    return
  fi
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
    if [ -z "$value" ]; then
      read -p "Enter value for $key: " value
    fi
    azd env set "$key" "$value"
  done < "$env_file"
}

# Deploy logic
if [ "$ACTION" = "backend" ] || [ "$ACTION" = "all" ]; then
  echo "Provisioning Azure infra for backend with azd..."
  azd provision
  echo "Deploying backend (agent) service with azd..."
  azd deploy --service backend
  if [ -n "$ENV_FILE" ]; then
    echo "Syncing $ENV_FILE variables to azd environment for backend..."
    load_env_file "$ENV_FILE"
  else
    prompt_env_vars
  fi
fi

if [ "$ACTION" = "frontend" ] || [ "$ACTION" = "all" ]; then
  echo "Provisioning Azure infra for frontend with azd..."
  azd provision
  echo "Deploying frontend service with azd..."
  azd deploy --service frontend
  if [ -n "$ENV_FILE" ]; then
    echo "Syncing $ENV_FILE variables to azd environment for frontend..."
    load_env_file "$ENV_FILE"
  else
    prompt_env_vars
  fi
fi

if [ "$ACTION" = "frontend-static" ] || [ "$ACTION" = "all" ]; then
  echo "Provisioning Azure infra for frontend static web app with azd..."
  azd provision
  echo "Deploying frontend-static service with azd..."
  azd deploy --service frontend-static
  if [ -n "$ENV_FILE" ]; then
    echo "Syncing $ENV_FILE variables to azd environment for frontend-static..."
    load_env_file "$ENV_FILE"
  else
    prompt_env_vars
  fi
fi

echo "\nDeployment complete. Outputs:"
azd env get-values

WEB_URL=$(azd env get-values | grep dating-agent-backend | awk '{print $2}')
FRONTEND_URL=$(azd env get-values | grep frontend | awk '{print $2}')
STATIC_URL=$(azd env get-values | grep staticWebAppUrl | awk '{print $2}')
REDIS_HOST=$(azd env get-values | grep datingAgentRedis | awk '{print $2}')
REDIS_KEY=$(azd env get-values | grep redisKey | awk '{print $2}')
if [ -n "$WEB_URL" ]; then
  echo "Backend Web App URL: https://$WEB_URL"
fi
if [ -n "$FRONTEND_URL" ]; then
  echo "Frontend Web App URL: https://$FRONTEND_URL"
fi
if [ -n "$STATIC_URL" ]; then
  echo "Frontend Static Web App URL: https://$STATIC_URL"
fi
if [ -n "$REDIS_HOST" ] && [ -n "$REDIS_KEY" ]; then
  echo "Redis connection string: rediss://:$REDIS_KEY@$REDIS_HOST:6380/0"
fi

echo "==== Azure Deploy Script Finished: $(date) ====" 