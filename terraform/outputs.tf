output "containers" {
  value = {
    for name, c in proxmox_virtual_environment_container.suap : name => {
      vmid      = c.vm_id
      ip        = local.containers[name].ip
      memory_mb = local.containers[name].memory
      cores     = local.containers[name].cores
    }
  }
}

output "total_memory_mb" {
  value = local.total_memory_mb
}

output "memory_budget_mb" {
  value = var.memory_budget_mb
}

output "bridge" {
  value = var.bridge
}

output "ansible_hosts" {
  value = join("\n", [
    for name, c in local.containers :
    "${name} ansible_host=${c.ip} ansible_user=root"
  ])
}
