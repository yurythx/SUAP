locals {
  containers      = var.containers
  total_memory_mb = sum([for c in local.containers : c.memory])
  ssh_public_key  = trimspace(file(pathexpand(var.ssh_public_key_path)))
}
