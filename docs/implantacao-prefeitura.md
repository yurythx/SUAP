# Implantação do SUAP na Prefeitura Municipal de Rondonópolis

Relato da instância publicada em 31 de outubro de 2026: topologia, perfil administrativo, cadastro da prefeitura, o que foi republicado e as dificuldades encontradas.

A base é o SUAP IFRN COSINF 4.0.5 (Django 5.2, Python 3.14). O uso nesta prefeitura é a parte administrativa. Ensino, pesquisa, extensão acadêmica e vida estudantil ficam inacessíveis. Os aplicativos acadêmicos continuam instalados, porque o SUAP oficial não sobe se eles saem de `INSTALLED_APPS`.

## Domínios e branches

O nome de homologação é `hmlsuap.rondonopolis.mt.gov.br`. O de produção é `suap.rondonopolis.mt.gov.br`. O acesso que funciona hoje continua sendo `http://192.168.29.110`, porque o vhost desses nomes no proxy reverso `192.168.0.218` entra numa etapa seguinte. O exemplo desse vhost está em `scripts/nginx/proxy-reverso.conf.example`.

As branches `main`, `homologacao` e `producao` nascem do mesmo commit. O trabalho do dia a dia fica em `homologacao`. Quando uma versão é aceita, ela segue `homologacao` → `main` → `producao`. A diferença entre os ambientes é o `.env` do servidor (`scripts/env/homologacao.env.example` e `scripts/env/producao.env.example`), não o código. Não há máquina de produção.

O Nginx do `suap-lb` aceita o hostname de homologação, confia no `X-Forwarded-For` vindo de `192.168.0.218` e repassa `Host` e `X-Forwarded-Proto` para o Gunicorn. Enquanto o proxy falar HTTP, a aplicação trata a requisição como HTTP. Quando o proxy passar a terminar TLS e enviar `X-Forwarded-Proto: https`, o Django reconhece a origem segura.

## O que está no ar

Endereço em uso: `http://192.168.29.110`. O nome público previsto da homologação é `https://hmlsuap.rondonopolis.mt.gov.br`.

O login exibe o selo **PMR**. A hierarquia tem **33 setores** (a raiz Prefeitura Municipal de Rondonópolis e as 32 unidades enviadas). Há **501 servidores** ativos. A sigla da instituição e a raiz da árvore de setores são `PMR`. O estado gravado é MT e o domínio institucional é `rondonopolis.mt.gov.br`.

Depois da republicação de 31/10/2026, o menu autenticado abre nestas raízes:

- Documentos/Processos
- Programa de Gestão
- Gestão de Pessoas
- Administração
- Tec. da Informação
- Balcão Digital
- Des. Institucional
- Central de Serviços
- Internacionalização
- Comunicação Social
- Segurança Institucional
- Gerenciador de Projetos
- Auditoria
- Dados Abertos

Ensino, Pesquisa, Extensão e Atividades Estudantis saíram desse menu. O endereço `http://192.168.29.110/edu/` responde **página não encontrada**. O mesmo vale para `/pesquisa/`, `/extensao/`, `/ae/` e `/admin/edu/aluno/`. O login e a página inicial continuam no ar.

A página anônima ainda mostra o atalho **Demandas da Comunidade**, classificado pelo próprio SUAP na categoria Extensão. Esse atalho aponta para `/demandas_externas/periodos_demanda/`, que é demanda da comunidade, e permanece de propósito.

## Containers

No Proxmox, cada máquina desta implantação é um **container LXC** Debian 13, definido em `terraform/locals.tf` e criado por `terraform/main.tf`. Docker não está instalado em nenhuma delas. Recriar esses LXC apagaria o disco de cada um, inclusive o PostgreSQL com os 501 servidores. Por isso a republicação de 31/10/2026 atualizou o código dentro do `suap-app` e reiniciou só o processo da aplicação.

| LXC | IP interno | Função em execução | Versão conferida |
| --- | --- | --- | --- |
| ansible-ctl | 192.168.110.5 | Nó de controle | — |
| suap-lb | 192.168.110.10 | Nginx | 1.26.3 |
| suap-app | 192.168.110.20 | Gunicorn | 23.0.0, Python 3.14.10 |
| suap-db | 192.168.110.30 | PostgreSQL | 17.11 (Debian 13) |
| suap-redis | 192.168.110.40 | Redis | 8.0.2 |

A rede interna é `192.168.110.0/24`, na ponte `vmbr1`. O Proxmox faz NAT dessa rede para a ponte externa (`scripts/pve-vmbr1-nat.sh`). O endereço que os navegadores usam é `192.168.29.110`, no balanceador.

O Nginx do `suap-lb` escuta a porta 80 e encaminha para `http://192.168.110.20:8000`, preservando o cabeçalho `Host`. Arquivos em `/static/` são servidos de `/var/www/suap-static/` no balanceador.

No `suap-app` o único serviço da aplicação é `suap-gunicorn.service`:

- diretório `/opt/suap/src`
- ambiente `/opt/suap/src/.env`
- `DJANGO_SETTINGS_MODULE=suap.settings`
- `PYTHONPATH=/opt/suap/src`
- escuta `0.0.0.0:8000`
- 2 workers, 2 threads, timeout de 120 segundos
- usuário do serviço: root

Celery worker e Celery beat constam da descrição do LXC no Terraform e do Compose, e não têm unit systemd nesta instância.

O arquivo `compose/docker-compose.prod.yml` descreve outro desenho: um host com Nginx, Gunicorn, Celery, PostgreSQL 18 e Redis 7 em Docker. O Ansible em `ansible/site.yml` instalaria esse Compose. Esse caminho não é o que está publicado. O endereço `192.168.100.50`, usado em exemplos do Compose, não responde a partir da rede de operação.

## Perfil administrativo

A variável `DISABLE_EDU=True` já estava em `/opt/suap/src/.env`. Até 31/10/2026 o código que lê essa variável não estava no servidor, então o menu acadêmico continuava visível.

A flag fica em `app/suap/settings_base.py`. Os apps acadêmicos permanecem em `INSTALLED_APPS`. O que muda, só com a flag ligada:

- o menu, em `app/djtools/menu.py`, passa por `menu_visivel` antes da checagem de permissão (superusuário também deixa de ver esses grupos);
- os quadros da página inicial, em `app/djtools/layout.py`, `app/comum/views.py` e `app/djtools/utils/session.py`;
- as áreas `ensino`, `pesquisa` e `extensao` da API, em `app/suap/api.py`;
- a URL direta, o admin, `json`, `chained_select` e o breadcrumb desses apps, pelo middleware `djtools.middleware.modulos_ocultos.ModulosOcultosMiddleware`, que responde 404.

A lista e a regra estão em `app/djtools/modulos_ocultos.py`. Ficam ocultos, entre outros: `edu`, `pesquisa`, `projetos`, `ae`, `estagios`, `processo_seletivo`, `ppc`, `saude` (saúde do estudante) e a carreira docente (`professor_titular`, `rsc`, `progressao_docente`, `pit_rit` e variações).

Permanecem de propósito:

- `cursos` — cursos e concursos de servidor;
- `remanejamento` — remoção interna;
- `gestao` — indicadores;
- `catalogo_provedor_servico` — Balcão Digital;
- `rh`, `ponto`, patrimônio, protocolo, compras, contratos e processo eletrônico.

Arquivos estáticos em `/static/edu/...` não entram na regra de 404. Um CSS inexistente responde 404 porque o arquivo não está no disco, e a regra não bloqueia esse prefixo.

## Cadastro da prefeitura

As planilhas de unidades e de pessoas foram lidas por `app/rh/importacao_prefeitura.py` e gravadas pelo comando `importar_prefeitura`.

Decisões de organização:

- uma unidade organizacional e um setor raiz `PMR`, nome Prefeitura Municipal de Rondonópolis;
- as três raízes da planilha (`GAB-PREF`, `SEC-GOV` e `SMAGPI`) ficam filhas de `PMR`; o restante da hierarquia segue a coluna de superior da planilha;
- a matrícula do servidor é a coluna de login da planilha (limite de 30 caracteres do SUAP);
- a sigla do setor cabe em 15 caracteres e o nome em 100;
- todo mundo entra no grupo Django `Servidor`;
- o perfil da planilha vira um segundo grupo, sem permissão extra: **Básico** (271 pessoas) e **Colaborador (Básico sem Assinatura)** (230 pessoas);
- o SUAP não tem a trava do SEI que impede assinar; o segundo grupo só registra a origem do perfil;
- situação funcional código `01`, nome ATIVO PERMANENTE, técnico-administrativo, ativo;
- a importação pode ser repetida: setor pela sigla (código SIAPE vazio) e servidor pela matrícula.

Senha inicial, definida na criação do usuário em `comum.models.UserManager.get_or_create_user`: `PMR.` seguido do CPF já formatado. Exemplo com CPF fictício: `PMR.000.000.000-00`. A troca obrigatória no primeiro acesso ficou desligada. O backend do SUAP, com essa troca ligada e sem e-mail de notificação, recusa o login.

O e-mail de boas-vindas foi desligado só durante a importação, porque uma falha de envio abortaria o lote.

Conferência depois da carga: 33 setores, 501 servidores ativos, 501 no grupo Servidor, 271 em Básico, 230 em Colaborador (Básico sem Assinatura), zero conflito de CPF.

A logo da prefeitura não foi enviada. O cabeçalho continua com a marca do IFRN.

## Correção dos erros de login

No log do Gunicorn, o login de quem tem vínculo direto em pessoa física caía em `PessoaFisica.get_vinculo` ao acessar um atributo `user` que a pessoa não tem, e a resposta era 500. A consulta de ocupação de prestador falhava porque faltavam `atualizado_por_id` e `atualizado_em` em `comum_ocupacaoprestador`. Os 501 servidores tinham sido gravados com `eh_servidor` falso: o `save` da pessoa rodava antes de existir a linha do servidor e apagava a marca.

A consulta agora busca o vínculo pela pessoa quando não há servidor, aluno ou prestador. As duas colunas foram criadas. A marca de servidor foi recolocada nas 501 pessoas, e o `save` preserva a marca quando o servidor ainda está sendo criado. A consulta de duplo fator, que respondia 400 para quem não usa o código e enchia o log de “Bad Request”, passou a responder 200 com o texto `ERROR`, que é o que a tela de login já tratava como “não pedir o código”.

Depois do restart, o caminho de gravação do login dos superusuários e de um servidor concluiu, a página de login abre, e a consulta de duplo fator responde 200.

## Esquema e telas

O código desta versão lia 495 colunas que o PostgreSQL ainda não tinha, em 116 tabelas que já existiam, e faltavam 531 tabelas de modelos novos. Qualquer tela que carregasse esses modelos respondia erro. As colunas foram acrescentadas e as tabelas faltantes foram criadas vazias, na ordem das chaves estrangeiras. As consultas de todos os modelos passaram a responder.

O passaporte vazio passou a ser gravado como texto vazio. A coluna no banco não aceita nulo, e um salvamento posterior da pessoa apagava o valor.

Dois administradores existiam só como pessoa física ou prestador, sem matrícula de servidor. As telas de gestão, ponto, compras e patrimônio esperam um servidor e quebravam para essas contas. Cada uma ganhou matrícula de servidor no setor PMR. A estatística de viaturas não quebra mais quando não há viatura, e a lista de palavras-chave de dados abertos deixou de filtrar um vínculo que o modelo não tem.

Com um servidor comum, as 688 entradas do menu abriram sem erro 500. Com o administrador, a página inicial, o admin, o organograma, a frequência, o protocolo, as compras, o almoxarifado e o patrimônio passaram a abrir.

## Republicação de 31/10/2026

O código do corte acadêmico foi comparado com `/opt/suap/src`. A diferença era só o perfil administrativo. Foram copiados para o `suap-app`:

- `djtools/modulos_ocultos.py` (arquivo novo)
- `djtools/middleware/modulos_ocultos.py` (arquivo novo)
- `djtools/menu.py`
- `djtools/layout.py`
- `djtools/utils/session.py`
- `suap/api.py`
- `comum/views.py`
- `suap/settings_base.py`

Em seguida: `systemctl restart suap-gunicorn`. Banco, Redis e Nginx não foram reiniciados. Os dados da prefeitura ficaram no PostgreSQL.

Conferência depois do restart:

- `DISABLE_EDU` lido como verdadeiro pelo Django;
- menu sem Ensino, Pesquisa, Extensão e Atividades Estudantis;
- `http://192.168.29.110/accounts/login/` abre o login com o selo PMR;
- `http://192.168.29.110/edu/` mostra “Página não encontrada”;
- `systemctl is-active suap-gunicorn` permanece `active`.

Para repetir uma alteração pequena de código:

```bash
scp -i ~/.ssh/id_ed25519_sei_homolog arquivo.py root@192.168.110.20:/opt/suap/src/caminho/arquivo.py
ssh -i ~/.ssh/id_ed25519_sei_homolog root@192.168.110.20 systemctl restart suap-gunicorn
```

A chave usada é `id_ed25519_sei_homolog`, com `StrictHostKeyChecking=accept-new`. O comando roda a partir de `/opt/suap/src` com `PYTHONPATH=/opt/suap/src` quando for `manage.py`.

## Dificuldades e técnicas

### O Compose do repositório e a instância publicada são instalações diferentes

O README e o Ansible descrevem uma imagem Docker num host só. A instância que responde foi montada como cinco LXC, com PostgreSQL e Redis em pacote Debian e Gunicorn em systemd (`scripts/bootstrap-lxc.sh`, `scripts/suap-gunicorn.service`, `scripts/fix-lb.sh`, `scripts/fix-db.sh`, `scripts/fix-redis.sh`). Procurar o SUAP em `docker ps` no `suap-app` não encontra nada. O endereço antigo do Compose também não abre a porta 80.

O Terraform anota PostgreSQL 18 e Redis 7. O que está instalado é PostgreSQL 17.11 e Redis 8.0.2, as versões dos pacotes do Debian 13.

### PowerShell e SSH

Nesta estação Windows, o PowerShell remove aspas de `python -c` e de here-strings enviados pelo `ssh`. O comando que chega no servidor fica com a sintaxe quebrada. O caminho que funcionou foi gravar um `.py` local, enviar com `scp` e executar no LXC.

A primeira tentativa de SSH no `suap-app` sem a chave do projeto falhou na verificação do host em modo batch. Com `id_ed25519_sei_homolog` e `accept-new`, o host foi aceito. Os LXC do balanceador, do banco e do Redis precisaram do mesmo aceite na primeira conexão.

### O SUAP não sobe sem os apps acadêmicos

Tirar `edu`, `gestao` ou `processo_seletivo` de `INSTALLED_APPS` quebra a inicialização: modelos administrativos importam modelos acadêmicos. A técnica foi esconder acesso (menu, quadro, API, URL e admin) e deixar a lista de apps intacta. A função `quadro()` em `layout.py` já estava no limite de complexidade do ruff (C901, máximo 10). Um `if` a mais dentro dela estourava a regra. O registro do app do quadro ficou numa atribuição, e o filtro ficou em `chaves_de_quadros_visiveis` e `get_quadro_by_name`.

O ambiente virtual em `app/.venv` neste Windows é o venv Linux do projeto. `uv run` e o pytest local não sobem aqui. A checagem de estilo usou `uvx ruff`. O teste de verdade do corte foi feito na instância publicada.

### Banco à frente do registro e atrás do código

O comando de migração enxerga centenas de migrações pendentes em apps acadêmicos e administrativos. Ao mesmo tempo, as migrações do `edu` constam como aplicadas, e a tabela `edu_aluno` não tinha as colunas `token_responsavel` e `data_prevista_termino_ciclo`. Aplicar as centenas de migrações pendentes em cima de um banco que já tem as tabelas arrisca recriar estrutura e dados. A saída usada na carga foi pontual: as duas colunas faltantes de `edu_aluno` foram criadas vazias e anuláveis, porque o `save` de pessoa física consulta `aluno_set` e o SQL lista todas as colunas do modelo.

Há outras centenas de colunas que o código atual espera e o banco não tem, em tabelas que já existem. Um sintoma já visto no log, antes desta republicação, é a página de prestador de serviço: falta `comum_ocupacaoprestador.atualizado_por_id` e a resposta é 500. Isso não foi alterado nesta etapa.

### Passaporte obrigatório no PostgreSQL

O modelo declara `pessoa_fisica.passaporte` como nulo. A coluna no banco é `NOT NULL`. Na hora de salvar, `formatar_passaporte` devolve `None` quando o documento está vazio, e o primeiro servidor da planilha derrubou a transação. Os setores, gravados antes do laço de pessoas, permaneceram. A correção, só durante o comando de importação, faz o formatador devolver texto vazio. Vários `CharField` do servidor (`matricula_crh`, `matricula_sipe` e os e-mails que a planilha não traz) foram preenchidos com texto vazio pelo mesmo motivo.

O erro do banco inclui o CPF da linha. O comando passou a relatar a falha pelo login e pelo tipo do erro, sem o detalhe da linha.

### Senha, e-mail e grupo

A senha é montada com a sigla da instituição. A sigla precisava existir antes do primeiro usuário. O CPF usado na senha é o já mascarado (`000.000.000-00`), porque a pessoa física formata o documento no `save` e o servidor lê esse valor ao criar o usuário.

`forcar_troca_senha` ficou desligado. Com a troca forçada e sem e-mail de notificação, o backend levanta `UserMustResetPassword` e a pessoa não entra.

O grupo `Servidor` normalmente é atribuído no login. Na importação ele é gravado na hora, junto com o grupo do perfil da planilha, para o acesso a documentos e processos existir antes do primeiro login.

### Segredos nos scripts de bootstrap

`scripts/bootstrap-lxc.sh`, `scripts/fix-db.sh` e `scripts/fix-redis.sh` gravam senha inicial de banco e de Redis no próprio arquivo. Esses valores não devem ser copiados para documentação, chat ou commit novo. O passo pendente é tirá-los do repositório, guardá-los só no servidor e trocar as senhas que já circularam.

## O que ficou pendente

- Logo da prefeitura no lugar da marca do IFRN.
- Impedir de fato a assinatura de quem veio como “Colaborador (Básico sem Assinatura)”.
- Celery worker e beat, previstos no LXC da aplicação e ausentes no systemd.
- Alinhar o esquema do PostgreSQL ao código sem rodar às cegas as centenas de migrações pendentes. A página de prestador é um caso já quebrado.
- Retirar senhas iniciais dos scripts de bootstrap.
- O código do corte acadêmico foi copiado para `/opt/suap/src`. Uma sincronização futura que substitua essa árvore por um pacote antigo faz o menu acadêmico voltar, mesmo com `DISABLE_EDU=True` no `.env`.
