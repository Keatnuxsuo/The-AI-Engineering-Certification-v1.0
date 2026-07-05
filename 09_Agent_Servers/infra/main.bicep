// Subscription-scoped entry point for `azd up`.
// It creates one resource group and delegates all resource creation to
// resources.bicep (resource-group scope). This split is the standard azd
// layout and keeps role assignments / resource names easy to reason about.
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment. Used to derive resource names and the azd-env-name tag.')
param environmentName string

@minLength(1)
@description('Primary Azure region for all resources (e.g. eastus, westeurope).')
param location string

@description('OpenAI API key used by the agent (chat + embeddings).')
@secure()
param openAiApiKey string

@description('Tavily API key used by the web-search tool.')
@secure()
param tavilyApiKey string

@description('LangSmith API key. Required for the LangGraph self-hosted server in lite mode and for tracing.')
@secure()
param langsmithApiKey string

@description('Chat model name passed to the app as OPENAI_CHAT_MODEL.')
param openAiChatModel string = 'gpt-5.4-mini'

@description('Embedding model name passed to the app as OPENAI_EMBEDDING_MODEL.')
param openAiEmbeddingModel string = 'text-embedding-3-small'

// Deterministic, subscription-unique suffix so resource names stay stable
// across redeploys of the same environment but never collide globally.
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// azd requires the azd-env-name tag on the resource group to track the environment.
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    openAiApiKey: openAiApiKey
    tavilyApiKey: tavilyApiKey
    langsmithApiKey: langsmithApiKey
    openAiChatModel: openAiChatModel
    openAiEmbeddingModel: openAiEmbeddingModel
  }
}

// Consumed by azd (registry endpoint drives image push) and handy for the user.
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryLoginServer
output SERVICE_AGENT_API_URI string = resources.outputs.agentApiUri
