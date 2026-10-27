param environmentName string
param location string
param tags object
param modelName string
param modelVersion string
param modelCapacity int
param enableEventHubs bool
param principalId string = ''
@description('Entra ID app (client) ID for Microsoft sign-in on producer tools; empty keeps the open demo')
param authClientId string = ''
@secure()
param authClientSecret string = ''
@secure()
@description('Optional Microsoft Teams Workflows webhook: the full-time card is posted there')
param teamsWebhookUrl string = ''

var token = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  openAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  azureAiUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  eventHubsReceiver: 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
  eventHubsSender: '2b629674-e913-4c01-ae53-ef4638d8f975'
  speechUser: 'f2dc8367-1007-4938-bd23-fe263f013447'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908' // Azure AI Content Safety data plane
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
}

// Flex Consumption regions; elsewhere the function app runs in East US 2 (it only talks to Event Hubs and the web app)
var flexRegions = [
  'australiaeast'
  'brazilsouth'
  'canadacentral'
  'centralindia'
  'centralus'
  'eastasia'
  'eastus'
  'eastus2'
  'francecentral'
  'germanywestcentral'
  'italynorth'
  'japaneast'
  'koreacentral'
  'northcentralus'
  'northeurope'
  'norwayeast'
  'southafricanorth'
  'southcentralus'
  'southeastasia'
  'southindia'
  'spaincentral'
  'swedencentral'
  'uaenorth'
  'uksouth'
  'ukwest'
  'westcentralus'
  'westeurope'
  'westus'
  'westus2'
  'westus3'
]
var fnLocation = contains(flexRegions, location) ? location : 'eastus2'

// ---------------------------------------------------------------- identity & observability
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-touchline-${token}'
  location: location
  tags: tags
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-touchline-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-touchline-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ---------------------------------------------------------------- registry
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crtouchline${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

// ---------------------------------------------------------------- Azure AI Foundry (account + project + model)
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'ai-touchline-${token}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'ai-touchline-${token}'
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
    disableLocalAuth: true // Entra ID only: the app authenticates with its managed identity
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'touchline'
  location: location
  // Model and project creation both update the parent account; Azure rejects concurrent writes.
  dependsOn: [model]
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Touchline match intelligence'
    description: 'Agents, evaluations and traces for the Touchline insights engine'
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, identity.id, roles.openAiUser)
  scope: foundry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
  }
}

resource aiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, identity.id, roles.azureAiUser)
  scope: foundry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAiUser)
  }
}

// the person running azd can publish agents and run Foundry evaluations
resource deployerAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundry.id, principalId, roles.azureAiUser)
  scope: foundry
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAiUser)
  }
}

// Foundry tracing: connect the project to Application Insights so agent runs appear in the Foundry portal
resource tracing 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'appinsights-touchline'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: false
    credentials: { key: appInsights.properties.ConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: appInsights.id }
  }
}

resource speechUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, identity.id, roles.speechUser)
  scope: foundry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.speechUser)
  }
}

resource safetyUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, identity.id, roles.cognitiveServicesUser)
  scope: foundry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
  }
}

// ---------------------------------------------------------------- Event Hubs (event-driven ingestion)
resource hubs 'Microsoft.EventHub/namespaces@2024-01-01' = if (enableEventHubs) {
  name: 'evh-touchline-${token}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
  properties: { disableLocalAuth: true }
}

resource hub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = if (enableEventHubs) {
  parent: hubs
  name: 'match-events'
  properties: {
    partitionCount: 2
    messageRetentionInDays: 1
  }
}

// outbound: every verified insight and full time, for downstream consumers (the packages function, a CMS, social tools)
resource insightsHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = if (enableEventHubs) {
  parent: hubs
  name: 'touchline-insights'
  properties: {
    partitionCount: 2
    messageRetentionInDays: 1
  }
}

resource packagesGroup 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2024-01-01' = if (enableEventHubs) {
  parent: insightsHub
  name: 'packages'
}

resource hubReceiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableEventHubs) {
  name: guid(resourceGroup().id, identity.id, roles.eventHubsReceiver)
  scope: hubs
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsReceiver)
  }
}

resource hubSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableEventHubs) {
  name: guid(resourceGroup().id, identity.id, roles.eventHubsSender)
  scope: hubs
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsSender)
  }
}

// ---------------------------------------------------------------- Azure Functions: the event-driven back office
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = if (enableEventHubs) {
  name: take('sttouchline${token}', 24)
  location: fnLocation
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowSharedKeyAccess: false // identity only
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = if (enableEventHubs) {
  parent: storage
  name: 'default'
}

resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (enableEventHubs) {
  parent: blobService
  name: 'deployments'
}

resource packagesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (enableEventHubs) {
  parent: blobService
  name: 'packages'
}

resource journalContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (enableEventHubs) {
  parent: blobService
  name: 'input-journal'
}

resource blobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableEventHubs) {
  name: guid(resourceGroup().id, identity.id, roles.storageBlobDataOwner)
  scope: storage
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
  }
}

resource fnPlan 'Microsoft.Web/serverfarms@2024-04-01' = if (enableEventHubs) {
  name: 'plan-touchline-${token}'
  location: fnLocation
  tags: tags
  kind: 'functionapp'
  sku: { tier: 'FlexConsumption', name: 'FC1' }
  properties: { reserved: true }
}

resource packagesFn 'Microsoft.Web/sites@2024-04-01' = if (enableEventHubs) {
  name: 'func-touchline-${token}'
  location: fnLocation
  tags: union(tags, { 'azd-service-name': 'packages' })
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  dependsOn: [blobOwner, hubReceiver]
  properties: {
    serverFarmId: fnPlan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage!.properties.primaryEndpoints.blob}deployments'
          authentication: { type: 'UserAssignedIdentity', userAssignedIdentityResourceId: identity.id }
        }
      }
      scaleAndConcurrency: { maximumInstanceCount: 40, instanceMemoryMB: 2048 } // scales out on Event Hubs backlog
      runtime: { name: 'python', version: '3.11' }
    }
    siteConfig: {
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId', value: identity.properties.clientId }
        { name: 'EventHubConnection__fullyQualifiedNamespace', value: hubNamespaceFqdn }
        { name: 'EventHubConnection__credential', value: 'managedidentity' }
        { name: 'EventHubConnection__clientId', value: identity.properties.clientId }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
        { name: 'PACKAGES_STORAGE_ACCOUNT', value: storage.name }
        { name: 'TOUCHLINE_WEB_URL', value: 'https://${webName}.${env.properties.defaultDomain}' }
        { name: 'TEAMS_WEBHOOK_URL', value: teamsWebhookUrl }
      ]
    }
  }
}

// ---------------------------------------------------------------- Container Apps
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-touchline-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var webName = 'ca-touchline-${token}'
var hubNamespaceFqdn = enableEventHubs ? '${hubs.name}.servicebus.windows.net' : ''

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: webName
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  dependsOn: [acrPull, openAiUser, aiUser, speechUser, safetyUser, blobOwner, journalContainer]
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: empty(authClientSecret) ? [] : [
        { name: 'microsoft-provider-authentication-secret', value: authClientSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // replaced by `azd deploy`
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'AZURE_OPENAI_ENDPOINT', value: 'https://${foundry.properties.customSubDomainName}.openai.azure.com' }
            { name: 'AZURE_OPENAI_MODEL', value: modelName }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}' }
            { name: 'FOUNDRY_MODEL', value: modelName }
            { name: 'TOUCHLINE_FOUNDRY_AGENTS', value: 'on' } // use the agents published by the postprovision hook
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'TOUCHLINE_PUBLIC_URL', value: 'https://${webName}.${env.properties.defaultDomain}' }
            { name: 'TOUCHLINE_EVENTHUB_NAMESPACE', value: hubNamespaceFqdn }
            { name: 'TOUCHLINE_EVENTHUB_PARTITION', value: '0' }
            { name: 'TOUCHLINE_INPUT_JOURNAL_URL', value: enableEventHubs ? '${storage!.properties.primaryEndpoints.blob}input-journal/partition-0.json' : '' }
            { name: 'TOUCHLINE_OUTBOX_URL', value: enableEventHubs ? '${storage!.properties.primaryEndpoints.blob}input-journal/outbound.json' : '' }
            { name: 'AZURE_SPEECH_REGION', value: location }
            { name: 'AZURE_SPEECH_RESOURCE_ID', value: foundry.id }
            { name: 'AZURE_CONTENT_SAFETY_ENDPOINT', value: 'https://${foundry.properties.customSubDomainName}.cognitiveservices.azure.com' }
            { name: 'TOUCHLINE_AUTH', value: empty(authClientId) ? 'open' : 'entra' }
            { name: 'TOUCHLINE_PROTECT_SHARED', value: 'on' } // anonymous viewers use isolated Judge Mode
            { name: 'TOUCHLINE_PACKAGES_URL', value: enableEventHubs ? 'https://${packagesFn!.properties.defaultHostName}' : '' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000 }
              periodSeconds: 20
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/ready', port: 8000 }
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1 // the demo must stay live for judging
        maxReplicas: 1 // match state is process-local; scale out only after adding shared state
        rules: [
          {
            name: 'http-concurrency'
            http: { metadata: { concurrentRequests: '200' } }
          }
        ]
      }
    }
  }
}

// Microsoft Entra ID sign-in (Container Apps built-in authentication). Fans stay anonymous;
// the app enforces the Touchline.Producer / Touchline.Admin roles on producer tools.
resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (!empty(authClientId)) {
  parent: web
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: { unauthenticatedClientAction: 'AllowAnonymous' }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: authClientId
          clientSecretSettingName: 'microsoft-provider-authentication-secret'
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
        validation: { allowedAudiences: [ 'api://${authClientId}' ] }
      }
    }
  }
}

output registryLoginServer string = registry.properties.loginServer
output webUri string = 'https://${web.properties.configuration.ingress.fqdn}'
output openAiEndpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com'
output foundryProjectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
output foundryRaiPolicyId string = '${foundry.id}/raiPolicies/Microsoft.DefaultV2'
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output eventHubNamespace string = hubNamespaceFqdn
output packagesUri string = enableEventHubs ? 'https://${packagesFn!.properties.defaultHostName}' : ''
