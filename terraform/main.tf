resource "proxmox_virtual_environment_container" "suap" {
  for_each = local.containers

  node_name     = var.proxmox_node
  vm_id         = var.vmid_base + tonumber(element(split(".", each.value.ip), 3))
  description   = each.value.description
  tags          = ["suap", "lxc", "terraform"]
  unprivileged  = true
  started       = true
  start_on_boot = true

  features {
    nesting = true
    keyctl  = each.value.keyctl
  }

  operating_system {
    template_file_id = each.value.template
    type             = "debian"
  }

  cpu {
    cores = each.value.cores
  }

  memory {
    dedicated = each.value.memory
    swap      = each.value.swap
  }

  disk {
    datastore_id = var.datastore_id
    size         = each.value.disk
  }

  network_interface {
    name   = "eth0"
    bridge = var.bridge
  }

  network_interface {
    name     = "eth1"
    bridge   = var.lan_bridge
    firewall = false
  }

  initialization {
    hostname = each.key

    ip_config {
      ipv4 {
        address = "${each.value.ip}/${var.network_cidr_prefix}"
        gateway = var.gateway
      }
    }

    ip_config {
      ipv4 {
        address = "${each.value.lan_ip}/${var.lan_cidr_prefix}"
      }
    }

    dns {
      domain  = var.dns_domain
      servers = var.dns_servers
    }

    user_account {
      keys     = [local.ssh_public_key]
      password = var.root_password
    }
  }

  startup {
    order    = each.value.order
    up_delay = 10
  }

  lifecycle {
    ignore_changes  = [initialization[0].user_account]
    prevent_destroy = true

    precondition {
      condition     = local.total_memory_mb <= var.memory_budget_mb
      error_message = "Soma de RAM dos LXC (${local.total_memory_mb} MB) excede o orçamento de ${var.memory_budget_mb} MB."
    }

    precondition {
      condition     = !(var.environment == "producao" && var.vmid_base == 2100)
      error_message = "Produção não usa o VMID 2100 nem o state da homologação. Aplique o tfvars de produção só num diretório com state novo."
    }
  }
}
