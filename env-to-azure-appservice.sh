#!/bin/bash
# Usage: ./env-to-azure-appservice.sh <app-name> <resource-group>
# Loads all variables from .env into Azure App Service app settings
# Logs all steps and results to azure-deploy.log
set -e
LOG_FILE="azure-deploy.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "==== env-to-azure-appservice.sh Started: $(date) ===="
if [ $# -ne 2 ]; then
  echo "Usage: $0 <app-name> <resource-group>"
  exit 1
fi
if [ ! -f ".env" ]; then
  echo ".env file not found."
  exit 1
fi
while IFS='=' read -r key value; do
  [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
  az webapp config appsettings set --name "$1" --resource-group "$2" --settings "$key=$value"
done < .env
echo "All variables from .env have been set in Azure App Service app settings."
echo "==== env-to-azure-appservice.sh Finished: $(date) ====" 