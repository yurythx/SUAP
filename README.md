# SUAP — Implantação Autarquia (Proxmox + Terraform + Ansible + Compose)

Base oficial **IFRN COSINF 4.0.5** (Django 5.2 / Python 3.14). Com `DISABLE_EDU=True` a parte acadêmica fica inacessível (menu, página inicial e URL) e os módulos administrativos seguem no ar. Os apps de ensino permanecem instalados porque o SUAP oficial não sobe sem eles.

A instância publicada da Prefeitura Municipal de Rondonópolis está em cinco LXC no Proxmox (balanceador, aplicação, banco, Redis e controle). Esse conjunto é a homologação (`hmlsuap.rondonopolis.mt.gov.br`). A produção (`suap.rondonopolis.mt.gov.br`) ainda não tem máquina. O relato do deploy, do corte acadêmico e do cadastro está em [docs/implantacao-prefeitura.md](docs/implantacao-prefeitura.md). O Compose desta pasta é um desenho alternativo de host único; a instância no ar usa Gunicorn em systemd.

O dia a dia segue a branch `homologacao`. `main` guarda a versão aceita e `producao` recebe o merge quando houver o que publicar. As três começam no mesmo commit.

## Layout

```text
app/                 # Fonte oficial SUAP (manage.py na raiz)
terraform/           # VM Proxmox (8 vCPU, 16 GB, 160 GB)
ansible/             # hardening + Docker + sync/deploy
compose/             # Compose de produção + Dockerfile (uv) + overlay settings
```

## Pré-requisitos

- Fonte em `./app/manage.py` (já alinhado)
- Ansible via **WSL/Linux** (rsync)
- Terraform + acesso Proxmox

## Deploy

```bash
# 1) Segredos
cp compose/.env.example compose/.env
# editar SECRET_KEY, DATABASE_PASSWORD, REDIS_PASSWORD, hosts

cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# editar Proxmox / IP / VLAN

# 2) VM
cd terraform && terraform init && terraform apply

# 3) Host + stack
cd ../ansible
# atualizar inventory.ini com o IP
ansible-galaxy collection install -r requirements.yml
ansible-playbook site.yml
```

## Stack de runtime

| Serviço | Rede | Notas |
|---------|------|-------|
| nginx | front + back | 80/443 |
| web | back | Gunicorn `suap.wsgi`, UID 33 (`www-data`) |
| celery_worker / celery_beat | back | `celery -A suap` |
| postgres:18 | back | unaccent, pg_trgm, buffers 3 GB |
| redis:7 | back | senha obrigatória |

`DISABLE_EDU=True` (já no `compose/.env`) esconde Ensino, Pesquisa, Extensão e Atividades Estudantis, a carreira docente e as URLs `/edu/`, `/pesquisa/`, `/projetos/`, `/ae/` e o admin desses apps. Gestão de pessoas, ponto, patrimônio, protocolo, compras, contratos e processo eletrônico continuam. Para valer na instância publicada, reconstrua a imagem e suba o `web` de novo.

Bootstrap oficial na 1ª subida do `web`: `python manage.py sync`.
