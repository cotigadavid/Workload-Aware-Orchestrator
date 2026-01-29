resource "azurerm_resource_group" "rg" {
  name     = "orchestrator-rg"
  location = "Germany West Central"
}

resource "azurerm_container_registry" "acr" {
  name                = "orchestratoracr123"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = false
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
    node_count = 1
    vm_size = "Standard_B2ps_v2"
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  principal_id         = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  role_definition_name = "AcrPull"
  scope                = azurerm_container_registry.acr.id
}
