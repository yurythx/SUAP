# SUAP na Prefeitura Municipal de Rondonópolis

Artigo da implantação administrativa do SUAP (IFRN COSINF 4.0.5) em containers LXC no Proxmox, do cadastro da prefeitura e da publicação do nome de homologação no proxy reverso. A homologação está no ar. A produção está dimensionada e ainda não tem máquina.

Data de referência da carga e do corte acadêmico: 31 de outubro de 2026. Data de referência da publicação HTTPS: 4 de novembro de 2026.

## Problemática

A Prefeitura Municipal de Rondonópolis precisava de um sistema único para a rotina administrativa: documentos e processos, gestão de pessoas, ponto, patrimônio, compras, contratos e serviços digitais. A base disponível era o SUAP do IFRN, desenhado para uma instituição de ensino. Ensino, pesquisa, extensão e vida estudantil não fazem parte do uso desta prefeitura, mas o código oficial não sobe se esses aplicativos saem da lista de instalação. Módulos administrativos importam modelos acadêmicos.

Havia também um desenho de implantação que não correspondia ao que precisava ir ao ar. O repositório descreve um host único com Docker (Nginx, Gunicorn, Celery, PostgreSQL 18 e Redis 7). A prefeitura opera o Proxmox e já publica outros sistemas por um proxy reverso municipal. Colocar banco, fila, aplicação e ingresso no mesmo container misturaria disco de dados, processo web e borda de rede, e um `terraform apply` destrutivo apagaria o PostgreSQL junto com o código.

O acesso precisava de dois planos. Na rede interna, o balanceador é alcançado pelo NAT do Proxmox. Fora da prefeitura, o nome `hmlsuap.rondonopolis.mt.gov.br` precisava terminar TLS no proxy que já concentra os sites da prefeitura (`192.168.0.218`) e seguir em HTTP até o balanceador, porque o Nginx interno só escuta a porta 80. Enquanto o nome não tinha vhost próprio na porta 443, o pedido HTTPS caía no site padrão do proxy, apresentava o certificado de outro domínio e respondia 502. O HTTP interno, no mesmo caminho, já devolvia o login.

Por fim, a carga inicial tinha de refletir a estrutura real: uma raiz institucional, a hierarquia de unidades enviada em planilha e 501 servidores, com perfil de acesso registrado sem inventar uma trava de assinatura que o SUAP não possui.

## Desenvolvimento

### Base de software e ramos

A aplicação é Django 5.2 em Python 3.14, publicada com Gunicorn 23.0.0. O banco em execução é PostgreSQL 17.11 e o cache é Redis 8.0.2, os pacotes do Debian 13. O template LXC é `debian-13-standard_13.1-2_amd64`. O Terraform anota, em comentários antigos, PostgreSQL 18 e Redis 7; essas versões são as do desenho Docker, que não foi o caminho publicado.

O dia a dia segue a branch `homologacao`. `main` guarda a versão aceita. `producao` recebe o merge quando houver o que publicar. As três nascem do mesmo commit. O que separa os ambientes é o `.env` do servidor (`scripts/env/homologacao.env.example` e `scripts/env/producao.env.example`), mais o conjunto de LXC. O código é o mesmo.

`DISABLE_EDU=True` esconde a parte acadêmica. Os apps acadêmicos permanecem em `INSTALLED_APPS`.

### Topologia no Proxmox

O nó de API usado pelo Terraform é `https://192.168.29.51:8006/`, nó `pve`, armazenamento `local-lvm`. Cada função é um container LXC Debian 13, não privilegiado, com `nesting` ligado e `keyctl` desligado, criado por `terraform/main.tf` a partir de `terraform/variables.tf`. O recurso tem `prevent_destroy`: recriar o container apagaria o disco, inclusive o dos 501 servidores.

Cada LXC tem duas placas. `eth0` na ponte `vmbr1` é a rede de serviço `192.168.110.0/24`, gateway `192.168.110.1`. `eth1` na ponte `vmbr0` é o endereço da LAN `192.168.29.0/24`, sem gateway nessa interface. O Proxmox faz NAT da rede interna para `vmbr0` (`scripts/pve-vmbr1-nat.sh`: `ip_forward` e `MASQUERADE` de `192.168.110.0/24`). O endereço que o navegador interno usa no balanceador é `192.168.29.110`.

O VMID é a base do ambiente mais o último octeto do IP interno. Homologação usa base 2100 (VMID 2105, 2110, 2120, 2130, 2140 e 2150). Produção está prevista com base 3100, em outro diretório de state. O Terraform recusa aplicar produção com a base 2100, para não misturar os containers que já estão no ar.

A ordem de boot é banco, Redis, worker, aplicação, balanceador e controle, com 10 segundos de espera entre um e outro. DNS dos containers: `192.168.0.101` e `1.1.1.1`. O domínio interno do template é `suap.rondonopolis.local`.

O orçamento de RAM da homologação cabe num host comentado no Terraform como i3-7100 com cerca de 11,9 GB, deixando cerca de 1,8 GB para o Proxmox. A soma dos seis containers é 10240 MB, que é o teto (`memory_budget_mb`). A produção prevista soma 69632 MB dentro de um teto de 73728 MB (72 GB), com cerca de 4 GB de folga para o hipervisor.

São seis containers. O relato operacional de 31/10 ainda descrevia o Celery no próprio `suap-app`. O Ansible atual desliga `suap-celery` e `suap-celery-beat` na aplicação e sobe os dois no `suap-worker`.

| LXC | VMID | IP interno | IP de LAN | Função |
| --- | --- | --- | --- | --- |
| ansible-ctl | 2105 | 192.168.110.5 | 192.168.29.105 | Nó de controle |
| suap-lb | 2110 | 192.168.110.10 | 192.168.29.110 | Nginx, ingresso |
| suap-app | 2120 | 192.168.110.20 | 192.168.29.120 | Gunicorn |
| suap-db | 2130 | 192.168.110.30 | 192.168.29.130 | PostgreSQL 17 |
| suap-redis | 2140 | 192.168.110.40 | 192.168.29.140 | Redis 8 |
| suap-worker | 2150 | 192.168.110.50 | 192.168.29.150 | Celery worker e beat |

### Medidas usadas e medidas recomendadas

As colunas de homologação são as que o Terraform aplica por padrão e as que o Ansible de homologação configura. As de produção são as de `terraform/producao.tfvars.example` e de `ansible/inventories/producao`. Produção ainda não tem IP: o inventário está com marcadores `PREENCHER`. O proxy de borda, nos dois ambientes, é o mesmo host `192.168.0.218`.

| Recurso | Homologação (em uso) | Produção (recomendada, ainda sem máquina) |
| --- | --- | --- |
| Orçamento de RAM | 10240 MB | 73728 MB |
| ansible-ctl | 1 vCPU, 512 MB, swap 512 MB, disco 8 GB | 2 vCPU, 2048 MB, swap 1024 MB, disco 20 GB |
| suap-lb | 1 vCPU, 512 MB, swap 256 MB, disco 8 GB | 2 vCPU, 2048 MB, swap 1024 MB, disco 20 GB |
| suap-app | 2 vCPU, 4096 MB, swap 2048 MB, disco 40 GB | 8 vCPU, 32768 MB, swap 8192 MB, disco 80 GB |
| suap-db | 1 vCPU, 2560 MB, swap 1024 MB, disco 80 GB | 4 vCPU, 16384 MB, swap 4096 MB, disco 200 GB |
| suap-redis | 1 vCPU, 1024 MB, swap 512 MB, disco 8 GB | 2 vCPU, 8192 MB, swap 2048 MB, disco 20 GB |
| suap-worker | 1 vCPU, 1536 MB, swap 1024 MB, disco 20 GB | 4 vCPU, 8192 MB, swap 2048 MB, disco 40 GB |
| Soma de vCPU / RAM / disco | 7 vCPU, 10240 MB, 164 GB | 22 vCPU, 69632 MB, 380 GB |
| Gunicorn | 2 workers, 2 threads, timeout 120 s, escuta na rede interna porta 8000 | 8 workers, 4 threads |
| Celery | concorrência 1, fila `geral`, no worker | concorrência 4, no worker |
| PostgreSQL `shared_buffers` | 512 MB | 4 GB |
| `effective_cache_size` | 1536 MB | 12 GB |
| `work_mem` | 8 MB | 32 MB |
| `maintenance_work_mem` | 128 MB | 1 GB |
| Redis `maxmemory` | 768 MB | 6 GB |
| Política do Redis | `noeviction` (recusa gravar quando enche) e AOF ligado | a mesma política, no teto de 6 GB |
| Backup | `pg_dump -Fc` às 02:30 no banco, retenção de 7 dias; às 03:10 a aplicação puxa a cópia para o próprio disco | o mesmo desenho, com disco de banco de 200 GB |
| Nome | `hmlsuap.rondonopolis.mt.gov.br` | `suap.rondonopolis.mt.gov.br` |
| Base de VMID | 2100 | 3100, em state separado |

Os buffers do PostgreSQL de homologação foram escolhidos para os 2,5 GB do container: 512 MB de `shared_buffers` e 1536 MB de `effective_cache_size`. O padrão do pacote Debian deixa 128 MB e 4 GB, e 4 GB ultrapassa a RAM do LXC. Em produção, 4 GB de buffers e 12 GB de cache efetivo cabem nos 16 GB do banco.

O Redis de homologação cabe em 1 GB de RAM com teto de 768 MB. Produção separa 8 GB de RAM e usa 6 GB de teto, porque sessão, cache e fila compartilham a mesma instância (bases lógicas diferentes no mesmo processo).

O Gunicorn de homologação usa dois workers porque o container tem dois núcleos. Em produção o número sobe para oito workers e quatro threads, na medida dos oito núcleos do `suap-app`. O worker de homologação fica com um processo de Celery; o de produção, com quatro.

### Rede, portas e quem alcança quem

| Origem | Destino | Porta | Regra |
| --- | --- | --- | --- |
| Navegador interno | 192.168.29.110 (`suap-lb`) | 80 | HTTP direto no balanceador |
| Navegador externo ou interno pelo nome | proxy 192.168.0.218 | 443 | TLS no proxy; o upstream é HTTP |
| Proxy | 192.168.29.110 | 80 | `proxy_pass http://`, nunca a porta 443 do balanceador |
| `suap-lb` | 192.168.110.20 | 8000 | Gunicorn, só a partir da rede `192.168.110.0/24` |
| Aplicação e worker | 192.168.110.30 | 5432 | PostgreSQL, só a rede interna |
| Aplicação e worker | 192.168.110.40 | 6379 | Redis, só a rede interna |
| Operação | cada LXC | 22 | SSH com a chave do projeto |

O balanceador confia em `X-Forwarded-For` somente quando a origem é `192.168.0.218`. Ele repassa `Host` e `X-Forwarded-Proto` ao Gunicorn. Com o proxy terminando TLS e enviando `X-Forwarded-Proto: https`, o Django trata a origem como segura. Estáticos em `/static/` saem de `/var/www/suap-static/` no próprio balanceador.

O firewall previsto no Ansible acompanha essa matriz: 22 em todos; 80 e 443 no balanceador; 8000 no app restrito ao CIDR interno; 5432 no banco e 6379 no Redis com a mesma restrição; o worker só expõe SSH.

### Proxy reverso e o nome público

O proxy municipal é o host `pmrwebservice`, `192.168.0.218`, Ubuntu 24.04, painel aaPanel, servidor Tengine. O DNS público de `hmlsuap.rondonopolis.mt.gov.br` aponta para `170.245.70.68`. O DNS interno (`192.168.0.101`) aponta o mesmo nome para `192.168.0.218`. Os dois caminhos chegam ao mesmo Tengine.

O nome de produção, `suap.rondonopolis.mt.gov.br`, foi visto apontando para `192.168.0.89`, com a porta 443 sem escuta. Esse nome fica desligado até existir o balanceador de produção. Apontá-lo para a homologação publicaria dados de teste no endereço definitivo.

Até 4 de novembro o HTTPS do nome de homologação respondia 502 e apresentava o certificado de outro site do proxy (o pedido caía no vhost padrão, cujo upstream estava indisponível). O HTTP no mesmo proxy já chegava ao SUAP: o log do balanceador registrava 302 para `/accounts/login/?next=/`. A causa era a ausência de vhost TLS dedicado. O balanceador não escuta 443; um `proxy_pass` em HTTPS contra ele também gera 502.

O certificado instalado é o de `hmlsuap.rondonopolis.mt.gov.br`, emitido pela Let's Encrypt (intermediária YR2), válido até 2 de fevereiro de 2027. A terminação TLS fica no proxy. O bloco SSL segue o padrão já usado nos outros vhosts do painel (TLS 1.1, 1.2 e 1.3, sessão compartilhada e HSTS de um ano). O encaminhamento interno permanece `http://192.168.29.110`.

Na gravação, o teste de configuração do Tengine recusou o reload por um vhost alheio ao SUAP: formato de log `site_total` desconhecido em `extension/*.g-hosp.rondonopolis.mt.gov.br/site_total.conf`. Com esse teste falho, o painel não grava site nenhum. Corrigido o formato, o nome passou a responder.

Conferência em 4 de novembro de 2026, pelo IP interno do proxy e pelo IP público:

- HTTP/1.1 302, `Location: /accounts/login/?next=/`;
- certificado com CN `hmlsuap.rondonopolis.mt.gov.br`, emissor `CN=YR2, O=Let's Encrypt, C=US`;
- cabeçalho `Strict-Transport-Security: max-age=31536000`;
- servidor `Tengine`.

### Perfil administrativo

A prefeitura usa a parte administrativa do SUAP. A flag `DISABLE_EDU` está em `/opt/suap/src/.env` e é lida em `app/suap/settings_base.py`. Com ela ligada, o menu (`app/djtools/menu.py`) passa por `menu_visivel` antes da checagem de permissão, inclusive para superusuário. Os quadros da página inicial, as áreas `ensino`, `pesquisa` e `extensao` da API e o acesso direto por URL, admin, `json`, `chained_select` e breadcrumb desses apps passam a responder 404, pelo middleware `ModulosOcultosMiddleware`. A lista está em `app/djtools/modulos_ocultos.py`.

Ficam ocultos, entre outros: `edu`, `pesquisa`, `projetos`, `ae`, `estagios`, `processo_seletivo`, `ppc`, `saude` (saúde do estudante) e a carreira docente (`professor_titular`, `rsc`, `progressao_docente`, `pit_rit` e variações).

Permanecem de propósito: `cursos` (cursos e concursos de servidor), `remanejamento` (remoção interna), `gestao` (indicadores), `catalogo_provedor_servico` (Balcão Digital), `rh`, ponto, patrimônio, protocolo, compras, contratos e processo eletrônico. O atalho anônimo Demandas da Comunidade permanece: ele aponta para demanda da comunidade, e o próprio SUAP o classifica na categoria Extensão.

Depois da republicação de 31/10/2026, o menu autenticado abre nestas raízes: Documentos/Processos, Programa de Gestão, Gestão de Pessoas, Administração, Tec. da Informação, Balcão Digital, Des. Institucional, Central de Serviços, Internacionalização, Comunicação Social, Segurança Institucional, Gerenciador de Projetos, Auditoria e Dados Abertos.

`/edu/`, `/pesquisa/`, `/extensao/`, `/ae/` e `/admin/edu/aluno/` respondem página não encontrada. Login e página inicial continuam. Arquivos em `/static/edu/...` não entram nessa regra de 404.

Tirar `edu`, `gestao` ou `processo_seletivo` de `INSTALLED_APPS` impede a inicialização. A técnica foi esconder menu, quadro, API, URL e admin, e manter a lista de apps. A função `quadro()` em `layout.py` já estava no limite de complexidade do ruff; o filtro dos quadros ficou fora dela.

### Cadastro e estrutura administrativa

As planilhas de unidades e de pessoas foram lidas por `app/rh/importacao_prefeitura.py` e gravadas pelo comando `importar_prefeitura`.

Decisões de organização:

- uma unidade organizacional e um setor raiz `PMR`, nome Prefeitura Municipal de Rondonópolis;
- sigla institucional `PMR`, estado MT, domínio `rondonopolis.mt.gov.br`;
- as três raízes da planilha (`GAB-PREF`, `SEC-GOV` e `SMAGPI`) ficam filhas de `PMR`; o restante segue a coluna de superior;
- 33 setores no total (a raiz e as 32 unidades);
- a matrícula do servidor é a coluna de login da planilha, no limite de 30 caracteres do SUAP;
- a sigla do setor cabe em 15 caracteres e o nome em 100;
- situação funcional código `01`, nome ATIVO PERMANENTE, técnico-administrativo, ativo;
- a importação pode ser repetida: setor pela sigla (código SIAPE vazio) e servidor pela matrícula.

Conferência depois da carga: 33 setores, 501 servidores ativos, zero conflito de CPF.

Grupos Django gravados na importação, para o acesso existir antes do primeiro login (o grupo `Servidor` normalmente só entra no login):

| Grupo | Pessoas | Efeito |
| --- | --- | --- |
| Servidor | 501 | acesso de servidor, inclusive documentos e processos |
| Básico | 271 | segundo grupo, vindo do perfil da planilha, sem permissão extra |
| Colaborador (Básico sem Assinatura) | 230 | segundo grupo, só registra a origem do perfil |

O SUAP não tem a trava do SEI que impede assinar. O grupo de colaborador ainda não bloqueia assinatura; isso permanece pendente. A soma 271 + 230 fecha os 501.

A senha inicial é montada com a sigla da instituição e o CPF já formatado pela pessoa física. A fórmula está descrita em `docs/implantacao-prefeitura.md`. A troca obrigatória no primeiro acesso ficou desligada: com essa troca ligada e sem e-mail de notificação, o backend recusa o login (`UserMustResetPassword`). O e-mail de boas-vindas foi desligado só durante o lote, porque uma falha de envio abortaria a carga. A troca obrigatória volta a ser desejável quando o e-mail institucional e o nome público estiverem estáveis.

Dois administradores existiam só como pessoa física ou prestador, sem matrícula de servidor. Telas de gestão, ponto, compras e patrimônio esperam um servidor e quebravam para essas contas. Cada uma recebeu matrícula de servidor no setor PMR.

Com um servidor comum, as 688 entradas do menu abriram sem erro 500. Com o administrador, abriram a página inicial, o admin, o organograma, a frequência, o protocolo, as compras, o almoxarifado e o patrimônio.

A logo da prefeitura ainda não foi enviada. O cabeçalho continua com a marca do IFRN. O login exibe o selo PMR.

### Acessos de operação

| Acesso | Onde | Quem usa |
| --- | --- | --- |
| SSH root nos LXC | porta 22, chave `id_ed25519_sei_homolog`, `StrictHostKeyChecking=accept-new` | publicação de código e leitura de log a partir da estação de operação |
| API do Proxmox | `https://192.168.29.51:8006/`, usuário de token `terraform-prov@pve` | Terraform; o segredo do token fica fora do Git |
| Painel do proxy | `https://192.168.0.218:22370/`, conta de operação do DTI no host `pmrwebservice` | vhost, certificado e reload do Tengine |
| SUAP, grupo Servidor | aplicação | os 501 servidores |
| SUAP, grupos de perfil | aplicação | Básico e Colaborador, sem permissão adicional |
| SUAP, contas elevadas | aplicação | superusuários e as duas contas administrativas que receberam matrícula no setor PMR |
| Cópia de backup | chave `suap_backup`, do `suap-app` para o `suap-db` | cron das 03:10, sem senha de banco na linha de comando |

O Gunicorn da homologação ainda roda como root. A recomendação, para homologação e sobretudo para produção, é um usuário de serviço próprio, escutando só em `192.168.110.20:8000`. Segredos de banco e Redis ficam no `.env` do servidor. Os scripts de bootstrap leem `DATABASE_PASSWORD` e `REDIS_PASSWORD`; os valores reais não entram no Git.

### Esquema, migrações e correções que travavam o login

O código desta versão lia 495 colunas que o PostgreSQL ainda não tinha, em 116 tabelas que já existiam, e faltavam 531 tabelas de modelos novos. As colunas foram acrescentadas e as tabelas faltantes foram criadas vazias, na ordem das chaves estrangeiras.

Na noite de 31/10 o banco tinha 667 migrações que o Django considerava pendentes, embora tabelas e colunas do código já existissem. Um `migrate` comum tentaria criar de novo o que já estava lá. O ensaio foi uma cópia restaurada, no banco `suap_migrate_prova`. Nela, a consulta de cada modelo gerenciado passou, as 667 migrações foram gravadas com `migrate --fake` (só o histórico, sem SQL) e um `migrate` seguinte não tinha o que aplicar. O mesmo registro foi feito no banco `suap`. A cópia de ensaio foi apagada. A partir daí, `migrate` aplica só migração nova. `--fake` fica reservado a uma cópia, se o histórico voltar a divergir do esquema.

No login, quem tem vínculo direto em pessoa física caía em `PessoaFisica.get_vinculo` ao acessar um atributo `user` que a pessoa não tem, e a resposta era 500. A consulta de ocupação de prestador falhava porque faltavam `atualizado_por_id` e `atualizado_em` em `comum_ocupacaoprestador`. Os 501 servidores tinham sido gravados com `eh_servidor` falso: o `save` da pessoa rodava antes de existir a linha do servidor e apagava a marca. A consulta passou a buscar o vínculo pela pessoa quando não há servidor, aluno ou prestador. As duas colunas foram criadas. A marca de servidor foi recolocada nas 501 pessoas, e o `save` preserva a marca enquanto o servidor está sendo criado. A consulta de duplo fator, que respondia 400 para quem não usa o código, passou a responder 200 com o texto que a tela de login já tratava como “não pedir o código”.

O modelo declara `pessoa_fisica.passaporte` como nulo e a coluna no banco é `NOT NULL`. Na importação, o formatador devolve texto vazio quando o documento está vazio. Vários `CharField` do servidor que a planilha não traz (`matricula_crh`, `matricula_sipe` e e-mails) foram preenchidos do mesmo modo. O erro de banco, que incluía o CPF da linha, passou a ser relatado pelo login e pelo tipo do erro.

Duas colunas de `edu_aluno` (`token_responsavel` e `data_prevista_termino_ciclo`) foram criadas vazias e anuláveis porque o `save` de pessoa física consulta `aluno_set` e o SQL lista todas as colunas do modelo, mesmo com o módulo acadêmico oculto.

### Como uma alteração pequena chega ao ar

O código fica em `/opt/suap/src`, com `DJANGO_SETTINGS_MODULE=suap.settings`. Uma correção pontual é copiada para o `suap-app` e o processo é reiniciado com `systemctl restart suap-gunicorn`. Banco, Redis e Nginx não precisam reiniciar por causa de uma mudança de menu. Nesta estação Windows, o PowerShell remove aspas de `python -c` enviado por SSH; o caminho que funcionou foi gravar um `.py` local, enviar com `scp` e executar no LXC. O ambiente virtual em `app/.venv` neste Windows é o venv Linux do projeto, então o teste de verdade do corte foi feito na instância publicada. A checagem de estilo usou `uvx ruff`.

## Solução

A prefeitura ficou com uma homologação administrativa em seis LXC no Proxmox, separando ingresso, aplicação, fila, banco, cache e controle, no teto de 10 GB de RAM do host atual. O corte acadêmico é de visibilidade, não de desinstalação: o SUAP sobe completo e o menu, a API e a URL acadêmica deixam de aparecer. A estrutura cadastrada é a da planilha: raiz PMR, 33 setores e 501 servidores ativos, todos no grupo Servidor, repartidos entre Básico (271) e Colaborador (230) só como registro de origem.

O nome `hmlsuap.rondonopolis.mt.gov.br` termina TLS no proxy municipal e segue em HTTP até `192.168.29.110`. Em 4 de novembro de 2026 o HTTPS deixou de apresentar certificado de outro site e passou a responder 302 para o login, no IP interno do proxy e no IP público, com o certificado Let's Encrypt do próprio nome.

A produção permanece um conjunto maior, já escrito no Terraform e no Ansible (cerca de 68 GB de RAM útil, banco de 16 GB com disco de 200 GB, aplicação de 32 GB e worker dedicado com concorrência 4), em VMID a partir de 3100 e em state separado. Ela não aponta para os LXC de homologação.

## Conclusão

O SUAP administrativo da prefeitura está utilizável em homologação: login com o selo PMR, hierarquia carregada, módulos acadêmicos fora do caminho do usuário e nome público com certificado válido. O que sustentou isso foi tratar Proxmox, proxy e aplicação como três bordas distintas. O LXC guarda o serviço. O proxy guarda o TLS. O Django só reconhece HTTPS porque o balanceador repassa o protocolo que o proxy terminou.

As medidas de homologação são as de um host pequeno e de um ensaio com dados reais (501 pessoas). As de produção estão definidas e são maiores de propósito: mais núcleo e RAM na aplicação, banco com cache efetivo de 12 GB, Redis com teto de 6 GB e fila fora do processo web. Subir produção é criar esse segundo conjunto, preencher os IPs e publicar `suap.rondonopolis.mt.gov.br` no mesmo proxy, com `proxy_pass` HTTP para o balanceador novo.

Permanece em aberto, e deve entrar antes de tratar a homologação como produção:

- logo da prefeitura no lugar da marca do IFRN;
- trava real de assinatura para o grupo Colaborador (Básico sem Assinatura);
- troca obrigatória de senha no primeiro acesso, depois que o e-mail de notificação funcionar;
- Gunicorn com usuário próprio;
- máquinas, DNS e certificado do nome `suap.rondonopolis.mt.gov.br`, sem reutilizar o banco de homologação.
