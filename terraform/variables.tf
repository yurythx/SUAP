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

variable "lan_bridge" {
  type    = string
  default = "vmbr0"
}

variable "lan_cidr_prefix" {
  type    = number
  default = 24
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

variable "environment" {
  type    = string
  default = "homologacao"

  validation {
    condition     = contains(["homologacao", "producao"], var.environment)
    error_message = "environment deve ser homologacao ou producao."
  }
}

variable "containers" {
  type = map(object({
    ip          = string
    lan_ip      = string
    description = string
    template    = string
    cores       = number
    memory      = number
    swap        = number
    disk        = number
    keyctl      = bool
    order       = number
  }))
  default = {
    "ansible-ctl" = {
      ip          = "192.168.110.5"
      lan_ip      = "192.168.29.105"
      description = "Nó de controle Ansible (SUAP)"
      template    = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
      cores       = 1
      memory      = 512
      swap        = 512
      disk        = 8
      keyctl      = false
      order       = 6
    }
    "suap-lb" = {
      ip          = "192.168.110.10"
      lan_ip      = "192.168.29.110"
      description = "Nginx TLS — ingresso HTTP/S"
      template    = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
      cores       = 1
      memory      = 512
      swap        = 256
      disk        = 8
      keyctl      = false
      order       = 5
    }
    "suap-app" = {
      ip          = "192.168.110.20"
      lan_ip      = "192.168.29.120"
      description = "SUAP app — Gunicorn"
      template    = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
      cores       = 2
      memory      = 4096
      swap        = 2048
      disk        = 40
      keyctl      = false
      order       = 4
    }
    "suap-db" = {
      ip          = "192.168.110.30"
      lan_ip      = "192.168.29.130"
      description = "PostgreSQL 17"
      template    = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
      cores       = 1
      memory      = 2560
      swap        = 1024
      disk        = 80
      keyctl      = false
      order       = 1
    }
    "suap-redis" = {
      ip          = "192.168.110.40"
      lan_ip      = "192.168.29.140"
      description = "Redis 8 — sessao, cache e fila"
      template    = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
      cores       = 1
      memory      = 1024
      swap        = 512
      disk        = 8
      keyctl      = false
      order       = 2
    }
    "suap-worker" = {
      ip          = "192.168.110.50"
      lan_ip      = "192.168.29.150"
      description = "SUAP worker — Celery e Beat"
      template    = "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"
      cores       = 1
      memory      = 1536
      swap        = 1024
      disk        = 20
      keyctl      = false
      order       = 3
    }
  }
}
