#!/usr/bin/env sh
# Turn on Microsoft Entra ID sign-in for Touchline's producer tools.
#
#   ./scripts/setup_entra.sh            (after the first `azd up`; needs `az login` and `azd`)
#
# Creates an app registration with two app roles (Touchline.Producer, Touchline.Admin), a client
# secret for Container Apps authentication, gives YOU the Producer role, stores the values in the azd
# environment and re-provisions. Fans stay anonymous; producer actions then require the role.
set -eu

WEB_URI=$(azd env get-value SERVICE_WEB_URI)
NAME="touchline-$(azd env get-value AZURE_ENV_NAME)"
ROLES=$(cat <<'JSON'
[
  {"allowedMemberTypes": ["User"], "description": "Approve or drop graphics, run the shared broadcast and resilience drills",
   "displayName": "Touchline producer", "isEnabled": true, "value": "Touchline.Producer", "id": "6f1e7a52-3a1c-4b8e-9d2a-1c7f0a5e9b11"},
  {"allowedMemberTypes": ["User"], "description": "Everything a producer can do, plus configuration",
   "displayName": "Touchline admin", "isEnabled": true, "value": "Touchline.Admin", "id": "0b9d6c3e-8f4a-4e21-b6c5-7a2d9e1f3c22"}
]
JSON
)

echo "Creating the app registration $NAME"
APP_ID=$(az ad app create --display-name "$NAME" --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "$WEB_URI/.auth/login/aad/callback" --enable-id-token-issuance true \
  --app-roles "$ROLES" --query appId -o tsv)
az ad app update --id "$APP_ID" --identifier-uris "api://$APP_ID"
SP_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv 2>/dev/null || az ad sp show --id "$APP_ID" --query id -o tsv)
SECRET=$(az ad app credential reset --id "$APP_ID" --display-name containerapps-auth --years 1 --query password -o tsv)

echo "Giving you the Touchline.Producer role"
ME=$(az ad signed-in-user show --query id -o tsv)
az rest --method POST --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID/appRoleAssignedTo" \
  --body "{\"principalId\": \"$ME\", \"resourceId\": \"$SP_ID\", \"appRoleId\": \"6f1e7a52-3a1c-4b8e-9d2a-1c7f0a5e9b11\"}" >/dev/null

azd env set AUTH_CLIENT_ID "$APP_ID"
azd env set AUTH_CLIENT_SECRET "$SECRET"
echo "Re-provisioning with sign-in enabled"
azd provision
echo "Done. Producer tools at $WEB_URI now need a Microsoft sign-in with the Touchline.Producer role."
