resource "azurerm_resource_group" "rg" {
  name     = "orchestrator-rg"
  location = "Germany West Central"
}

resource "azurerm_container_registry" "acr" {
  name                = "orchestratoracr123"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = true
}

resource "azurerm_storage_account" "storage" {
  name                     = "orchestratorstore123"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_servicebus_namespace" "sb" {
  name                = "orchestratorsb"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Standard"
}

resource "azurerm_servicebus_queue" "jobs" {
  name         = "jobqueue"
  namespace_id = azurerm_servicebus_namespace.sb.id
}

resource "azurerm_kubernetes_cluster" "aks" {
  name                = "orchestrator-aks"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "orchestrator"

  default_node_pool {
    name       = "system"
    node_count = 2
    vm_size = "Standard_B2ps_v2"
  }

  identity {
    type = "SystemAssigned"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id
  }

  azure_policy_enabled = true
}

resource "azurerm_role_assignment" "acr_pull" {
  principal_id         = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  role_definition_name = "AcrPull"
  scope                = azurerm_container_registry.acr.id
}

# Log Analytics Workspace for Container Insights and Application Insights
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "orchestrator-logs"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# Application Insights for application monitoring
resource "azurerm_application_insights" "appinsights" {
  name                = "orchestrator-appinsights"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  workspace_id        = azurerm_log_analytics_workspace.logs.id
  application_type    = "web"
}

# Enable Container Insights on AKS
resource "azurerm_log_analytics_solution" "container_insights" {
  solution_name         = "ContainerInsights"
  location              = azurerm_resource_group.rg.location
  resource_group_name   = azurerm_resource_group.rg.name
  workspace_resource_id = azurerm_log_analytics_workspace.logs.id
  workspace_name        = azurerm_log_analytics_workspace.logs.name

  plan {
    publisher = "Microsoft"
    product   = "OMSGallery/ContainerInsights"
  }
}

# Azure Batch Account for heavy compute workloads
resource "azurerm_batch_account" "batch" {
  name                              = "orchestratorbatch123"
  resource_group_name               = azurerm_resource_group.rg.name
  location                          = azurerm_resource_group.rg.location
  pool_allocation_mode              = "BatchService"
  storage_account_id                = azurerm_storage_account.storage.id
  storage_account_authentication_mode = "StorageKeys"

  identity {
    type = "SystemAssigned"
  }

  tags = {
    environment = "production"
    purpose     = "heavy-compute-jobs"
  }
}

# Batch Pool for Spark/ML jobs
resource "azurerm_batch_pool" "spark_pool" {
  name                = "spark-pool"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_batch_account.batch.name
  display_name        = "Spark & ML Compute Pool"
  vm_size             = "Standard_D2s_v3"
  node_agent_sku_id   = "batch.node.ubuntu 20.04"

  auto_scale {
    evaluation_interval = "PT5M"
    formula = <<EOF
// Get pending tasks
$PendingTasks = $PendingTasks.GetSample(1);
$TargetDedicated = $PendingTasks > 0 ? min(10, $PendingTasks) : 0;
$TargetLowPriority = 0;
EOF
  }

  storage_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-focal"
    sku       = "20_04-lts"
    version   = "latest"
  }

  container_configuration {
    type = "DockerCompatible"
  }

  start_task {
    command_line         = "/bin/bash -c 'apt-get update && apt-get install -y docker.io'"
    wait_for_success     = true
    user_identity {
      auto_user {
        elevation_level = "Admin"
        scope          = "Pool"
      }
    }
  }

  depends_on = [azurerm_batch_account.batch, azurerm_container_registry.acr]
}
