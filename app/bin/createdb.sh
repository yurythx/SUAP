#!/usr/bin/env bash

# Cores e Formatação
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

# Helpers de Log Minimalistas
log_step() { echo -e "${CYAN}→ $1${NC} ..."; }
log_success() { echo -e "${GREEN}✓ $1${NC} "; }
log_error() { echo -e "${RED}✗ ERRO: $1${NC} "; exit 1; }

# Silenciador de comandos
# Redireciona STDOUT para /dev/null, mantém STDERR no terminal
silent() {
  "$@" > /dev/null
}

# 1. Carregamento de Ambiente
if [ -f .env ]; then
  while IFS='=' read -r key value; do
    if [[ ! $key =~ ^# && -n $key ]]; then
      value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//')
      export "$key=$value"
    fi
  done < .env
fi

BANCO_TESTE="test_suap_dev"

echo -e "${BLUE}=== Iniciando Setup do Banco de Dados ===${NC}\n"

# 2. Criação do Banco Temporário
log_step "1/4 Preparando esquema no banco temporário"
silent python bin/scripts/run_sql.py --host "$DATABASE_HOST" --port "$DATABASE_PORT" --user "$DATABASE_USER" --password "$DATABASE_PASSWORD" --command "drop database if exists $BANCO_TESTE" && python manage.py test --noinput --failfast comum.tests.CreateDatabaseTestCase --keepdb -v 0 || \
log_error "Falha ao criar banco temporário. Verifique as configurações de conexão."
log_success "Esquema preparado."

# 3. Renomear Banco
log_step "2/4 Renomeando $BANCO_TESTE para $DATABASE_NAME"
silent python bin/scripts/run_sql.py --host "$DATABASE_HOST" --port "$DATABASE_PORT" --user "$DATABASE_USER" --password "$DATABASE_PASSWORD" --command "alter database $BANCO_TESTE rename to $DATABASE_NAME" || \
log_error "Não foi possível renomear o banco. Certifique-se de que não há conexões ativas ou que o banco '$DATABASE_NAME' não existe."
log_success "Banco de dados renomeado."

# 4. Sincronização de Migrações
log_step "3/4 Sincronizando migrações"
silent python manage.py migrate --fake || \
log_error "Erro ao aplicar migrações fake."
log_success "Migrações sincronizadas."

# 5. Superusuário
log_step "4/4 Criando conta administrativa"
python manage.py createsuperuser || \
log_error "Falha ao criar superusuário."
log_success "Superusuário criado."



echo -e "\n${GREEN}✨ Setup finalizado com sucesso!${NC}"
