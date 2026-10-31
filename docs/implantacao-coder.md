# Implantação do SUAP no órgão Coder

Esta branch é de outro órgão, separada da Prefeitura Municipal de Rondonópolis. As duas implantações não compartilham banco, Redis, usuários nem árvore de setores. A homologação que está no ar em `http://192.168.29.110` continua sendo a prefeitura e não recebe o código nem os dados desta branch.

O ponto de partida é o mesmo SUAP administrativo da prefeitura: a parte acadêmica fica inacessível e os aplicativos de ensino continuam instalados. Estrutura, regras e pessoas deste órgão ainda não foram cadastradas.

## O que falta receber

- Nome oficial, sigla da raiz (até 15 caracteres), município, UF e domínio de e-mail.
- Nome público do sistema, para o proxy `192.168.0.218`.
- Endereços de um conjunto novo de máquinas. Não reutilizar `192.168.110.0/24` nem o balanceador `192.168.29.110`.
- Planilha de unidades e planilha de usuários, no mesmo formato usado na prefeitura.
- As regras que diferem da prefeitura: módulos, grupos, assinatura e o modo de trabalho. Elas entram nesta branch quando estiverem descritas.
- A logo, se houver.

## O que já está separado

`scripts/env/coder.env.example` é o ambiente deste órgão. `SUAP_ORGAO=coder` marca a instância. O comando `importar_prefeitura` recusa rodar quando essa variável está definida, para não gravar a sigla PMR aqui.

`scripts/nginx/proxy-reverso-coder.conf.example` é o vhost futuro no proxy. Ele não encaminha para a prefeitura.

`terraform/coder.tfvars.example` reserva a faixa de VMID a partir de 2200. Não se aplica no state da prefeitura, que começa em 2100.

## Cadastro, quando as planilhas chegarem

Na aplicação deste órgão, com o `.env` já apontando para o banco novo:

```bash
python manage.py importar_orgao unidades.csv usuarios.csv \
  --sigla SIGLA --nome "Nome do órgão" --uf MT \
  --municipio "Cidade" --dominio exemplo.gov.br
```

A sigla da instituição é gravada antes das pessoas. A senha inicial de quem é criado fica no formato `SIGLA.` mais o CPF mascarado, por exemplo `CODER.000.000.000-00`. Todo servidor entra no grupo Servidor. O outro grupo é o perfil que vier na planilha, sem permissão extra. A planilha não pode repetir a sigla da raiz numa unidade: essa sigla é o topo da árvore, e as unidades sem superior ficam debaixo dela.

O comando recusa a sigla PMR e recusa o banco `192.168.110.30`.

## Branches

O trabalho deste órgão fica em `coder`. A prefeitura segue `homologacao` → `main` → `producao`. Uma correção do SUAP que sirva aos dois órgãos é levada de uma linha para a outra por escolha, não por um merge que misture cadastro ou regra.

Não há máquina deste órgão ainda. Nada aqui foi publicado no proxy.
