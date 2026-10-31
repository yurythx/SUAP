# Preâmbulo comum de deploy.sh, undeploy.sh e destroy.sh: carregar com `. suapdev-comum.sh "$@"`.

FULLPATH="$( cd "$(dirname "${BASH_SOURCE[0]}")" ; cd ../.. ; pwd -P )"
cd "$FULLPATH"

. .env

# `--chave valor` vira $chave. Consome os pares: um valor com "--" no meio (ex.: branch a--b) não é tomado por opção.
while [ $# -gt 0 ]; do
  case $1 in
    --*) declare "${1#--}=${2-}"; shift $(( $# > 1 ? 2 : 1 )) ;;
    *) shift ;;
  esac
done

# ponytail: colide se duas branches só diferem nesses caracteres (feat/a x feat-a); hash no sufixo se acontecer.
# A branch vira pasta, container, banco e subdomínio: "/" e qualquer caractere fora de [A-Za-z0-9_.-] viram "-".
slug() { printf '%s' "${1//[^A-Za-z0-9_.-]/-}"; }

# Auditoria na tabela suapdevs. Variáveis do psql (só valem via stdin) escapam aspas do dono (ex.: D'Ávila);
# ON_ERROR_STOP mantém o código de saída != 0 em erro de SQL, como o -c fazia.
registrar_acao() {
  docker exec -i postgres psql -h "$DATABASE_HOST" -U postgres -d suapdevs -tA -v ON_ERROR_STOP=1 \
    -v nome="$CONTAINER_NAME" -v dono="$OWNER" -v acao="$1" \
    <<< "INSERT INTO suapdevs (nome, dono, acao) VALUES (:'nome', :'dono', :'acao')"
}
