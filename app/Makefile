CURRENT_DIRECTORY := $(shell pwd)

COMMAND?=python manage.py shell

SERVICES?=web cron celery celery-beat celery-flower redis db minio minio-nginx pdfprinter mail
WEB_CONTAINER=web

ifneq ("$(wildcard .env)","")
include .env
export $(shell sed 's/=.*//' .env)
endif
export COMPOSE_PROJECT_NAME=suap
export DATA=$(shell date '+%F+%H-%M-%S')
export COMPOSE_BAKE=true

COMPOSE=docker compose -f docker/docker-compose.dev.yml
CONN_STRING=postgresql://$(DATABASE_USER):$(DATABASE_PASSWORD)@$(DATABASE_HOST):$(DATABASE_PORT)
PSQL=$(COMPOSE) run --rm db psql "$(CONN_STRING)/$(DATABASE_NAME)"
DOCKER_TARGETS=runserver run start-web stop-web stop-runserver start-celery stop-celery start-celery-beat stop-celery-beat start-flower start-cron start-pdf start-ai stop-ai stop-pdf start-minio start-redis stop-redis start-db stop-db stop-cron stop down prune status build-base build-dev build push-image push-image-base pull-image pull-pdf-image pull-ai-image pull-image-base logs execute sync bash shell migrate makemigrations collectstatic begin psql backup restore drop-db redis-cli

help:
	@echo "Ajuda de Comandos (SUAP)"
	@echo "========================"
	@echo ""
	@echo "Aviso: comandos Docker/Compose exigem arquivo .env."
	@echo "Dica: cp .env.dev.sample .env"
	@echo ""
	@echo "=== Docker / Serviços ==="
	@echo "  make runserver|run                           - Sobe web (db + redis + celery + web)"
	@echo "  make stop                                    - Para serviços definidos em SERVICES"
	@echo "  make down                                    - Para e remove containers do projeto"
	@echo "  make logs                                    - Exibe logs dos containers"
	@echo "  make status                                  - Lista status dos serviços"
	@echo "  make start-web|stop-web                      - Inicia/para serviço web"
	@echo "  make start-celery|stop-celery                - Inicia/para workers celery"
	@echo "  make start-celery-beat|stop-celery-beat      - Inicia/para scheduler celery"
	@echo "  make start-cron|stop-cron                    - Inicia/para serviço cron"
	@echo "  make start-db|stop-db                        - Inicia/para PostgreSQL"
	@echo "  make start-redis|stop-redis                  - Inicia/para Redis"
	@echo "  make start-pdf|stop-pdf                      - Inicia/para serviço de impressão PDF"
	@echo "  make start-ai|stop-ai                        - Inicia/para serviço AI"
	@echo "  make start-mail|stop-mail                    - Inicia/para serviço Mailhog"
	@echo ""
	@echo "=== Banco / Gestão ==="
	@echo "  make begin                                   - Cria DB e carga inicial"
	@echo "  make backup                                  - Backup em deploy/backup/"
	@echo "  make restore FILE=<dump>                     - Restaura dump"
	@echo "  make drop-db                                 - Remove banco"
	@echo "  make psql                                    - Abre psql no banco"
	@echo "  make redis-cli                               - Abre redis-cli"
	@echo ""
	@echo "=== Comandos no Container Web ==="
	@echo "  make sync                                    - Executa python manage.py sync"
	@echo "  make bash                                    - Abre bash no container web"
	@echo "  make shell                                   - Abre shell do Django"
	@echo "  make migrate                                 - Executa migrações"
	@echo "  make makemigrations                          - Gera novas migrações"
	@echo "  make collectstatic                           - Coleta arquivos estáticos"
	@echo "  COMMAND='ls' make execute                    - Executa comando arbitrário no web"
	@echo ""
	@echo "=== Build / Imagens ==="
	@echo "  make build-base|build-dev|build              - Build das imagens"
	@echo "  make pull-image|pull-image-base|pull-pdf-image|pull-ai-image - Pull de imagens"
	@echo "  make push-image|push-image-base              - Push de imagens"
	@echo ""
	@echo "=== Desenvolvimento Local (uv) ==="
	@echo "  make venv                                    - Cria .venv com uv"
	@echo "  make uv-sync                                 - Sincroniza dependências"
	@echo "  make uv-update                               - Atualiza lock e sincroniza"
	@echo "  make pre-commit-ci                           - Execute checagem de código no mesmo modo do CI"
	@echo ""
	@echo "=== Utilitários ==="
	@echo "  make clean-pyc                               - Remove arquivos .pyc"
	@echo "  make prune                                   - Remove recursos Docker não utilizados"
	@echo ""

check-env:
	@if [ ! -f .env ]; then \
		echo "Erro: arquivo .env não encontrado. Este comando usa Docker e requer .env."; \
		echo "Dica: copie .env.dev.sample para .env e ajuste as variáveis necessárias."; \
		exit 1; \
	fi

$(DOCKER_TARGETS): check-env

runserver:
	$(COMPOSE) up -d db
	$(COMPOSE) up -d redis
	$(COMPOSE) up celery web

run: runserver

start-web:
	$(COMPOSE) up -d web

stop-web:
	$(COMPOSE) stop web

stop-runserver: stop-web

start-celery:
	$(COMPOSE) up -d celery

stop-celery:
	$(COMPOSE) stop celery

start-celery-beat:
	$(COMPOSE) up -d celery-beat

stop-celery-beat:
	$(COMPOSE) stop celery-beat

start-flower:
	$(COMPOSE) up -d celery-flower

start-cron:
	$(COMPOSE) up -d cron

start-pdf:
	$(COMPOSE) up -d pdfprinter

start-ai:
	$(COMPOSE) up -d ai

stop-ai:
	$(COMPOSE) stop ai
	$(COMPOSE) rm -f ai

stop-pdf:
	$(COMPOSE) stop pdfprinter
	$(COMPOSE) rm -f pdfprinter

start-minio:
	$(COMPOSE) up -d minio minio-nginx

start-redis:
	$(COMPOSE) up -d redis

stop-redis:
	$(COMPOSE) stop redis
	$(COMPOSE) rm -f redis

start-db:
	$(COMPOSE) up -d db

stop-db:
	$(COMPOSE) stop db
	$(COMPOSE) rm -f db

stop-cron:
	$(COMPOSE) stop cron
	$(COMPOSE) rm -f cron

start-mail:
	$(COMPOSE) up -d mail

stop-mail:
	$(COMPOSE) stop mail
	$(COMPOSE) rm -f mail

stop:
	$(COMPOSE) stop $(SERVICES)

down: stop
	$(COMPOSE) rm -f $(SERVICES)
	docker-compose -f docker/docker-compose.cleanup.yml down -v

prune: down
	docker system prune -f

status:
	$(COMPOSE) ps

build-base:
	$(COMPOSE) build base

build-dev:
	$(COMPOSE) build web

build:
	$(COMPOSE) build prod

push-image:
	docker tag $(SUAP_IMAGE):latest $(SUAP_IMAGE):$(NEXT_TAG)
	docker push $(SUAP_IMAGE):$(NEXT_TAG)
	docker push $(SUAP_IMAGE):latest
	docker rmi $(SUAP_IMAGE):$(NEXT_TAG)

push-image-base:
	docker push $(SUAP_IMAGE):base

pull-image:
	docker pull $(SUAP_IMAGE)

pull-pdf-image:
	docker pull $(SUAP_PDF_IMAGE)

pull-ai-image:
	docker pull $(SUAP_AI_IMAGE)

pull-image-base:
	docker pull $(SUAP_IMAGE):base

logs:
	$(COMPOSE) logs -f $(SERVICES)

clean-pyc:
	./bin/clean_pyc.sh

execute:
	$(COMPOSE) run --user 0:0 $(PORT) --rm $(WEB_CONTAINER) $(COMMAND)

sync: COMMAND=python manage.py sync
sync: execute

bash: PORT=-p 8000:8000
bash: COMMAND=/bin/bash
bash: execute

shell: COMMAND=python manage.py shell
shell: execute

migrate: COMMAND=python manage.py migrate
migrate: execute

makemigrations: COMMAND=python manage.py makemigrations
makemigrations: execute

collectstatic: COMMAND=python manage.py collectstatic -c --no-input -v 0
collectstatic: execute

begin:
	$(COMPOSE) run --rm web python manage.py create_db
	$(COMPOSE) run --rm web python manage.py carga_inicial

psql:
	$(PSQL)

backup:
	mkdir -p deploy/backup
	$(COMPOSE) run --rm db pg_dump "$(CONN_STRING)/$(DATABASE_NAME)" > deploy/backup/dump_$(DATA).sql

restore:
	$(COMPOSE) run --rm db psql "$(CONN_STRING)/" -c "create database $(DATABASE_NAME)"
	$(COMPOSE) run --rm -T db psql "$(CONN_STRING)/$(DATABASE_NAME)" < $(FILE)

drop-db:
	$(COMPOSE) run --rm db psql "$(CONN_STRING)/" -c "drop database $(DATABASE_NAME)"

redis-cli:
	$(COMPOSE) run --rm redis redis-cli -u $(REDIS_LOCATION)

venv:
	uv venv .venv

uv-sync:
	uv sync --all-groups

uv-update:
	uv lock --upgrade
	uv sync --all-groups

pre-commit-ci:
	uv run pre-commit run --from-ref origin/master --to-ref HEAD

.PHONY: down help
