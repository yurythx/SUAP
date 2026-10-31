#!/usr/bin/env bash

GREEN='\033[0;32m' # Green
RED='\033[0;31m' # Red
NC='\033[0m' # No Color

running_branches=$(docker ps --format '{{.Label "BRANCH"}}' | grep -v -e '^$' | sort -u)
folders=$(ls -d /var/suapdevs/*/ 2>/dev/null)

echo ">>>>>>>> $(date)"

# Verificar cada pasta
for folder in $folders; do
  # Extrai o nome do branch a partir do caminho da pasta
  # Ex: de "/var/suapdevs/meu-branch/" para "meu-branch"
  branch_name=$(basename "$folder")
  
  # Verifica se o branch da pasta está na lista de branches ativos
  if echo "${running_branches}" | grep -q -w "${branch_name}"; then
    # Se estiver na lista, o container está ativo. A pasta é preservada.
    echo -e "${GREEN}${folder} preservado (container ativo)${NC}"
  else
    # Se não, a pasta e qualquer container parado associado serão removidos.
    echo -e "${RED}Avaliando a remoção de ${folder}...${NC}"
    
    # Procura por containers PARADOS (status=exited) com o label do branch correspondente.
    stopped_container_id=$(docker ps -a --filter "status=exited" --filter "label=BRANCH=${branch_name}" --format '{{.ID}}')
    
    if [ -n "$stopped_container_id" ]; then
      # Se encontrou um container parado, remove ele primeiro.
      echo -e "${RED} -> Removendo container parado: $(echo $stopped_container_id | tr '\n' ' ')${NC}"
      docker rm $stopped_container_id > /dev/null
    fi
    
    # Agora, remove a pasta que não tem mais um container ativo.
    echo -e "${RED} -> Apagando pasta ${folder}${NC}"
    rm -rf "$folder"
  fi
done

echo "Limpeza concluída com sucesso! ✨"
