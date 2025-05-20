// Dating Agent Azure Infrastructure (App Service + Redis + Static Web App)
param location string = resourceGroup().location
param appServicePlanName string = 'datingAgentPlan'
param webAppName string = 'dating-agent-backend'
param redisName string = 'datingAgentRedis'
param frontendWebAppName string = uniqueString(resourceGroup().id, 'frontend')
param staticWebAppName string = uniqueString(resourceGroup().id, 'frontendstatic')

resource plan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource webapp 'Microsoft.Web/sites@2022-03-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.10'
      appSettings: [
        { name: 'AGENT_LOG_FILE'; value: '/tmp/agent.log' }
        { name: 'PORT'; value: '8000' }
        // Add your API keys and secrets here or via azd env
      ]
    }
    httpsOnly: true
  }
}

resource frontendWebapp 'Microsoft.Web/sites@2022-03-01' = {
  name: frontendWebAppName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: 'NODE|18-lts'
      appSettings: [
        // Add frontend env vars here or via azd env
      ]
    }
    httpsOnly: true
  }
}

resource staticWeb 'Microsoft.Web/staticSites@2022-03-01' = {
  name: staticWebAppName
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    repositoryUrl: '' // Set by GitHub Actions
    branch: ''        // Set by GitHub Actions
    buildProperties: {
      appLocation: 'frontend'
      apiLocation: ''
      outputLocation: 'frontend/.next'
    }
  }
}

resource redis 'Microsoft.Cache/Redis@2023-04-01' = {
  name: redisName
  location: location
  sku: {
    name: 'Basic'
    family: 'C'
    capacity: 1
  }
  properties: {
    enableNonSslPort: false
  }
}

output webAppUrl string = webapp.properties.defaultHostName
output frontendWebAppUrl string = frontendWebapp.properties.defaultHostName
output staticWebAppUrl string = staticWeb.properties.defaultHostname
output redisHost string = redis.properties.hostName
output redisKey string = listKeys(redis.id, '2023-04-01').primaryKey 