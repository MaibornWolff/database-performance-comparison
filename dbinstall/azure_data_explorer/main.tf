terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0.2"
    }
  }

  required_version = ">= 1.1.0"
}

provider "azurerm" {
  features {}
}


resource "azurerm_resource_group" "rg-compare" {
  name     = "db-performance-comparison"
  location = "West Europe"

  tags = {
    "cost center" = "IOT",
    environment   = "iot-lab"
  }
}

resource "azurerm_kusto_cluster" "adxcompare" {
  name                        = "adxcompare"
  location                    = azurerm_resource_group.rg-compare.location
  resource_group_name         = azurerm_resource_group.rg-compare.name
  streaming_ingestion_enabled = true

  # Change depending on your performance needs
  sku {
    name     = "Dev(No SLA)_Standard_E2a_v4"
    capacity = 1
  }

  tags = {
    "cost center" = "IOT",
    environment   = "iot-lab"
  }
}

resource "azurerm_kusto_database" "sample-db" {
  name                = "SampleDB"
  resource_group_name = azurerm_resource_group.rg-compare.name
  location            = azurerm_resource_group.rg-compare.location
  cluster_name        = azurerm_kusto_cluster.adxcompare.name

  hot_cache_period   = "P1D"
  soft_delete_period = "P1D"
}

data "azurerm_client_config" "current" {
}

# Change to your own service principal
data "azuread_service_principal" "service-principle" {
  display_name = "mw_iot_ADX-DB-Comparison"
}

resource "azurerm_kusto_database_principal_assignment" "ad-permission" {
  name                = "AD-Permission"
  resource_group_name = azurerm_resource_group.rg-compare.name
  cluster_name        = azurerm_kusto_cluster.adxcompare.name
  database_name       = azurerm_kusto_database.sample-db.name

  tenant_id      = data.azurerm_client_config.current.tenant_id
  principal_id   = data.azuread_service_principal.service-principle.id
  principal_type = "App"
  role           = "Admin"
}
