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


resource "azurerm_resource_group" “rg-compare” {
  name     = "db-performance-comparison"
  location = "West Europe"
}

resource "azurerm_kusto_cluster" "example" {
  name                = "adxcompare"
  location            = azurerm_resource_group.rg-compare.location
  resource_group_name = azurerm_resource_group.rg-compare.name

  sku {
    name     = "Standard_D13_v2"
    capacity = 2
  }

  tags = {
    cost center = "IOT",
    environment = "iot-lab"
  }
}