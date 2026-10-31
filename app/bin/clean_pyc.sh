#!/usr/bin/env bash

# Define o caminho base
PARENTSCRIPTPATH="$( cd "$(dirname "$0")" ; cd .. ; pwd -P )"

# Inicializa a variável de verbosidade como falsa
VERBOSE=false

# Verifica se o primeiro argumento é -v ou --verbose
if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

# Conta os arquivos (sempre útil ter o número, mas você pode silenciar se quiser)
COUNT=$(cd "$PARENTSCRIPTPATH" && find . -path ./deploy -prune -o -path ./upload -prune -o -name "*.pyc" | wc -l)
echo "Limpando arquivos .pyc em: $PARENTSCRIPTPATH"
echo "Total de arquivos encontrados: $COUNT"
if [ "$VERBOSE" = true ]; then
    # Executa com -print para mostrar os arquivos removidos
    cd "$PARENTSCRIPTPATH" && find . -path ./deploy -prune -o -path ./upload -prune -o -name "*.pyc" -print -exec rm -f {} +
else
    # Executa silenciosamente (sem o -print)
    cd "$PARENTSCRIPTPATH" && find . -path ./deploy -prune -o -path ./upload -prune -o -name "*.pyc" -exec rm -f {} +
fi
