variable "proxmox_endpoint" {
  type = string
}

variable "proxmox_insecure" {
  type    = bool
  default = true
}

variable "proxmox_api_token" {
  type      = string
  default   = ""
  sensitive = true
}

variable "proxmox_username" {
  type    = string
  default = "root@pam"
}

variable "proxmox_password" {
  type      = string
  default   = ""
  sensitive = true
}

variable "proxmox_node" {
  type    = string
  default = "pve"
}

variable "datastore_id" {
  type    = string
  default = "local-lvm"
}

variable "template_debian13" {
  type    = string
  default = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
}

variable "bridge" {
  type    = string
  default = "vmbr1"
}

variable "network_cidr_prefix" {
  type    = number
  default = 24
}

variable "gateway" {
  type    = string
  default = "192.168.110.1"
}

variable "dns_servers" {
  type    = list(string)
  default = ["192.168.0.101", "1.1.1.1"]
}

variable "dns_domain" {
  type    = string
  default = "suap.rondonopolis.local"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519_sei_homolog.pub"
}

variable "root_password" {
  type      = string
  sensitive = true
}

variable "vmid_base" {
  type    = number
  default = 2100
}

# Host i3-7100 ~11.9 GB — reserva ~1.8 GB ao PVE
variable "memory_budget_mb" {
  type    = number
  default = 10240
}
