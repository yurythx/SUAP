locals {
  # Orçamento ampliado no i3-7100 (~11.9 GB). Soma ≤ memory_budget_mb.
  # Prioridade: suap-app (migrate Django) e suap-db.
  containers = {
    "ansible-ctl" = {
      ip          = "192.168.110.5"
      description = "Nó de controle Ansible (SUAP)"
      template    = var.template_debian13
      cores       = 1
      memory      = 512
      swap        = 512
      disk        = 8
      keyctl      = false
      order       = 6
    }
    "suap-lb" = {
      ip          = "192.168.110.10"
      description = "Nginx TLS — ingresso HTTP/S"
      template    = var.template_debian13
      cores       = 1
      memory      = 512
      swap        = 256
      disk        = 8
      keyctl      = false
      order       = 5
    }
    "suap-app" = {
      ip          = "192.168.110.20"
      description = "SUAP app — Gunicorn + Celery + Beat"
      template    = var.template_debian13
      cores       = 2
      memory      = 5632
      swap        = 2048
      disk        = 40
      keyctl      = false
      order       = 4
    }
    "suap-db" = {
      ip          = "192.168.110.30"
      description = "PostgreSQL 18"
      template    = var.template_debian13
      cores       = 1
      memory      = 2560
      swap        = 1024
      disk        = 80
      keyctl      = false
      order       = 1
    }
    "suap-redis" = {
      ip          = "192.168.110.40"
      description = "Redis 7 — broker/cache"
      template    = var.template_debian13
      cores       = 1
      memory      = 1024
      swap        = 512
      disk        = 8
      keyctl      = false
      order       = 2
    }
  }

  total_memory_mb = sum([for c in local.containers : c.memory])
  ssh_public_key  = trimspace(file(pathexpand(var.ssh_public_key_path)))
}
