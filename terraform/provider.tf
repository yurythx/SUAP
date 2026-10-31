provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  insecure  = var.proxmox_insecure
  api_token = var.proxmox_api_token != "" ? var.proxmox_api_token : null
  username  = var.proxmox_api_token == "" ? var.proxmox_username : null
  password  = var.proxmox_api_token == "" ? var.proxmox_password : null
}
