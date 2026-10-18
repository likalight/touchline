// Touchline on Azure: `azd up` provisions everything and deploys the container.
targetScope = 'subscription'

@minLength(1)
@maxLength(40)
@description('azd environment name, used to name resources')
param environmentName string

@minLength(1)
@description('Primary region (must offer Azure Container Apps and the chosen model)')
param location string

@description('Azure OpenAI model deployed in Azure AI Foundry for narration and Q&A')
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
param modelCapacity int = 50

@description('Provision Azure Event Hubs for event-driven match ingestion')
param enableEventHubs bool = true

var tags = { 'azd-env-name': environmentName, app: 'touchline' }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'touchline-resources'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    modelName: modelName
    modelVersion: modelVersion
    modelCapacity: modelCapacity
    enableEventHubs: enableEventHubs
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryLoginServer
output SERVICE_WEB_URI string = resources.outputs.webUri
output AZURE_OPENAI_ENDPOINT string = resources.outputs.openAiEndpoint
output AZURE_OPENAI_MODEL string = modelName
output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.foundryProjectEndpoint
output APPLICATIONINSIGHTS_CONNECTION_STRING string = resources.outputs.appInsightsConnectionString
output TOUCHLINE_EVENTHUB_NAMESPACE string = resources.outputs.eventHubNamespace
