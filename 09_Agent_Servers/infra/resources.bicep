// All resources for the LangGraph agent server, at resource-group scope.
//
// "All in Docker" topology: a SINGLE Azure Container App runs the same three
// containers that `langgraph up` starts locally, sharing one network namespace
// so they reach each other over localhost:
//   - agent-api : your LangGraph server image (built + pushed by azd), port 8000, external ingress
//   - postgres  : pgvector/pgvector:pg16  (localhost:5432)  -- run/thread/checkpoint state
//   - redis     : redis:6                 (localhost:6379)  -- task queue + pub/sub
//
// No separate managed PostgreSQL or Redis services are provisioned.
//
// IMPORTANT TRADEOFFS (by design, for a simple single-unit deploy):
//   - Postgres/Redis state is EPHEMERAL: it resets on every restart/redeploy.
//     Fine for a demo. For durable state, use Azure Database for PostgreSQL
//     Flexible Server instead of the postgres sidecar (see git history for that
//     variant). Postgres on Azure Files (SMB) is not reliable, so we don't mount one.
//   - The app is pinned to a SINGLE replica (min=max=1). The LangGraph queue
//     worker and the co-located Postgres/Redis assume one instance; scaling out
//     would give each replica its own DB/queue. Horizontal scale requires
//     external managed Postgres + Redis.
//
// Security choices:
//   - ACR admin user disabled; the api image is pulled via managed identity + AcrPull.
//   - App keys (OpenAI/Tavily/LangSmith) are Container App secrets, not hardcoded.
//   - Postgres/Redis are never exposed via ingress; only the api container is.

@description('Azure region for all resources.')
param location string

@minLength(3)
@description('Unique, stable suffix for resource names.')
param resourceToken string

@description('Tags applied to every resource (must include azd-env-name).')
param tags object

@secure()
param openAiApiKey string
@secure()
param tavilyApiKey string
@secure()
param langsmithApiKey string

param openAiChatModel string
param openAiEmbeddingModel string

@description('Placeholder image used only at first provision; azd replaces it with the built image on deploy.')
param agentApiImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

// Local, container-to-container connection strings (localhost within the app).
// Postgres uses the stock superuser/db and no TLS since traffic never leaves the pod.
var postgresUri = 'postgres://postgres:postgres@localhost:5432/postgres?sslmode=disable'
var redisUri = 'redis://localhost:6379'

// ---------------------------------------------------------------------------
// Observability: Log Analytics backs the Container Apps environment logs.
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------------------
// Container Registry (image target for azd) + identity that can pull from it.
// ---------------------------------------------------------------------------
resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: 'acr${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' } // Basic is sufficient for pushing a single app image
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${resourceToken}'
  location: location
  tags: tags
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleId
  }
}

// ---------------------------------------------------------------------------
// Container Apps environment + the single multi-container app.
// ---------------------------------------------------------------------------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource agentApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-agent-${resourceToken}'
  location: location
  // azd matches this tag to the `agent-api` service in azure.yaml.
  tags: union(tags, { 'azd-service-name': 'agent-api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000 // only the agent-api container is exposed
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: [
        { name: 'openai-api-key', value: openAiApiKey }
        { name: 'tavily-api-key', value: tavilyApiKey }
        { name: 'langsmith-api-key', value: langsmithApiKey }
      ]
    }
    template: {
      // Three containers share one network namespace -> reachable on localhost.
      containers: [
        {
          name: 'agent-api'
          image: agentApiImage
          resources: {
            cpu: json('0.75')
            memory: '1.5Gi'
          }
          env: [
            { name: 'OPENAI_API_KEY', secretRef: 'openai-api-key' }
            { name: 'TAVILY_API_KEY', secretRef: 'tavily-api-key' }
            { name: 'LANGSMITH_API_KEY', secretRef: 'langsmith-api-key' }
            { name: 'LANGSMITH_TRACING', value: 'true' }
            { name: 'POSTGRES_URI', value: postgresUri }
            { name: 'DATABASE_URI', value: postgresUri }
            { name: 'REDIS_URI', value: redisUri }
            { name: 'OPENAI_CHAT_MODEL', value: openAiChatModel }
            { name: 'OPENAI_EMBEDDING_MODEL', value: openAiEmbeddingModel }
            { name: 'RAG_DATA_DIR', value: 'data' }
          ]
        }
        {
          name: 'postgres'
          image: 'pgvector/pgvector:pg16' // matches what `langgraph up` uses (needs the vector extension)
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'POSTGRES_USER', value: 'postgres' }
            { name: 'POSTGRES_PASSWORD', value: 'postgres' }
            { name: 'POSTGRES_DB', value: 'postgres' }
            // Keep the data dir on the container's own ephemeral filesystem.
            { name: 'PGDATA', value: '/var/lib/postgresql/data/pgdata' }
          ]
        }
        {
          name: 'redis'
          image: 'redis:6'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        // Single replica: co-located stateful sidecars + the LangGraph queue
        // worker must not be duplicated.
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPull
  ]
}

output registryLoginServer string = registry.properties.loginServer
output agentApiUri string = 'https://${agentApi.properties.configuration.ingress.fqdn}'
