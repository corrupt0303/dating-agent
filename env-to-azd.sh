#!/bin/bash
# Usage: ./env-to-azd.sh
# Loads all variables from .env into the current azd environment
# Logs all steps and results to azure-deploy.log
set -e
LOG_FILE="azure-deploy.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "==== env-to-azd.sh Started: $(date) ===="
if [ ! -f ".env" ]; then
  echo ".env file not found."
  exit 1
fi
while IFS='=' read -r key value; do
  [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
  azd env set "$key" "$value"
done < .env
echo "All variables from .env have been set in the azd environment."
echo "==== env-to-azd.sh Finished: $(date) ====" 