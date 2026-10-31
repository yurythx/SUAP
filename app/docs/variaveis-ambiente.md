# Variáveis de ambiente

Referência de **todas** as variáveis de ambiente lidas pelo SUAP. O template de
desenvolvimento é o [`.env.dev.sample`](../.env.dev.sample):

```bash
cp .env.dev.sample .env
make run
```

O `.env` é lido por `docker/docker-compose.dev.yml` (todos os serviços via
`env_file`) e pelo `Makefile` (que o exporta). Os valores são consumidos em
`suap/settings_base.py` e `suap/settings_sample.py` via `os.environ.get(...)`.

Quase toda variável tem um **default** no `settings_base.py`; o `.env` só
precisa declarar o que difere do default ou o que ativa um serviço do stack.
A coluna **Obrigatória** indica as que, se ausentes, deixam um serviço do
`docker-compose.dev.yml` ocioso/sem efeito (todas as demais são opcionais).

> **Mecanismo `SUAP_<NOME>`** (`settings_base.py:883`): qualquer variável de
> ambiente com prefixo `SUAP_` sobrescreve a configuração global de mesmo nome
> (sem o prefixo), com o valor parseado como JSON (e, na falha, como string).
> Ex.: `SUAP_DEBUG=true` define `DEBUG`. Use para ajustar pontualmente qualquer
> setting sem editar o `settings.py`.

---

## Toggles de funcionalidade

Ligam/desligam subsistemas inteiros. Padrão `False`, exceto onde indicado.

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `USE_REDIS` | **sim** | `False` | Usa Redis para cache e sessão. Sem ela, `REDIS_LOCATION`/`SESSION_LOCATION` são ignoradas (cache em memória local, sessão em arquivo). |
| `USE_CELERY` | **sim** | `False` | Liga o Celery. Sem ela, os containers `celery`/`celery-beat` não despacham tarefas. |
| `USE_SENTRY` | não | `False` | Inicializa o Sentry (monitoramento de erros). Requer `SENTRY_URL`. |
| `USE_ELASTICSEARCH` | não | `False` | Ativa a integração de busca via Elasticsearch/OpenSearch. |
| `USE_HISTORY` | não | `False` | Ativa o registro de histórico de alterações. |
| `USE_EDU_LOG` | não | `True` | Liga o log do módulo `edu`. Desligado nos testes. |
| `USE_PWA` | não | `False` | Habilita os recursos de Progressive Web App. |

## Aplicação / site

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `SUAP_ENVIRONMENT` | não | `production` | Ambiente lógico (`dev\|production\|homolog\|test`). No sample é `dev`. |
| `DEBUG` | não | `True` (sample) | Modo debug do Django (logging, cookies não-seguros, pipeline de assets desligado). Mantenha `True` em dev. |
| `SECRET_KEY` | não | chave fixa do repo | Chave de assinatura de sessões/CSRF. O default serve para dev; **troque** fora de dev. |
| `SITE_URL` | não | `http://localhost:8000` | URL base do site (compõe, p.ex., a `LOGOUT_URL` do Gov.br). |
| `SERVER_ALIAS` | não | `suap` | Alias do servidor (usado em tags do Sentry). |
| `ALLOWED_HOSTS` | não | `*` | Hosts permitidos, separados por vírgula. |
| `SECURE_PROXY_SSL_HEADER` | não | `HTTP_X_FORWARDED_PROTO,https` | Header (e valor) que indica requisição HTTPS atrás de proxy. |
| `CLIENT_IP_HEADERS` | não | `HTTP_X_REAL_IP,HTTP_X_FORWARDED_FOR,REMOTE_ADDR` | Ordem dos headers consultados para descobrir o IP do cliente. |
| `PUBLIC_INDEX_URL` | não | `/` | URL da página pública inicial. |
| `TIPO_ARVORE_SETORES` | não | `SUAP` | Origem da árvore de setores (`SUAP\|SIAPE`). |
| `LANGUAGES` | não | `pt-br:Português,en:English,es:Español` | Idiomas disponíveis (`código:Rótulo`, separados por vírgula). |
| `LPS` | não | vazio | Linha de Produto de Software: ativa overrides de urls/templates por instituição. |
| `ADMINS` | não | `Admin,admin@suap.net` | Destinatários de e-mails de erro (`Nome,email`, vários separados por `:`). |
| `TIME_ZONE` | não | `America/Recife` | Timezone do Django. |
| `TZ` | não | — | Timezone do container Docker. No sample: `America/Fortaleza`. |

## Aplicações instaladas

Permitem rodar o SUAP com um subconjunto de apps (ex.: só `comum,rh`).

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `PRE_INSTALLED_APPS_SUAP` | não | lista do `settings_base` | Apps carregados antes dos apps do SUAP (separados por vírgula). |
| `INSTALLED_APPS_SUAP` | não | todos os apps (`APPS_SUAP`) | Apps de domínio do SUAP a carregar. |
| `POS_INSTALLED_APPS_SUAP` | não | lista do `settings_base` | Apps de terceiros carregados depois (separados por vírgula). |

## Banco de dados (Postgres)

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `DATABASE_NAME` | não | `suap_dev` | Nome do banco. |
| `DATABASE_USER` | não | `postgres` | Usuário (também vira `POSTGRES_USER` do container `db`). |
| `DATABASE_PASSWORD` | não | vazio | Senha (também vira `POSTGRES_PASSWORD` do container `db`). |
| `DATABASE_HOST` | não | `127.0.0.1` | Host. No stack Docker é o serviço `db`. |
| `DATABASE_PORT` | não | `5432` | Porta. |
| `DISABLE_SERVER_SIDE_CURSORS` | não | `False` | Desativa cursores server-side (necessário atrás de pgbouncer em modo transaction). |
| `DATABASE_ROUTERS` | não | vazio | Routers de banco (ex.: `ldap_backend.router.SuapRouter`). |
| `DEFAULT_DATABASE_TEST` | não | `test_suap_dev` | Nome do banco de testes. |
| `AUTHENTICATION_BACKENDS` | não | `ModelBackendPlus,LdapBackend` | Backends de autenticação (separados por vírgula). |

## Cache / sessão (Redis)

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `USE_REDIS` | **sim** | `False` | Ver toggles. Liga o uso do Redis. |
| `REDIS_LOCATION` | não | `redis://127.0.0.1:6379/1` | URL do cache padrão. No stack: `redis://redis:6379/1`. |
| `REDIS_PASSWORD` | não | vazio | Senha do cache padrão. |
| `SESSION_LOCATION` | não | `redis://127.0.0.1:6379/2` | URL do cache de sessão. No stack: `redis://redis:6379/2`. |
| `SESSION_PASSWORD` | não | vazio | Senha do cache de sessão. |

## Tarefas assíncronas (Celery)

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `USE_CELERY` | **sim** | `False` | Ver toggles. Liga o Celery. |
| `CELERY_BROKER_URL` | não | `redis://localhost:6379/3` | Broker das tarefas. No stack: `redis://redis:6379/3`. |
| `CELERY_RESULT_BACKEND` | não | `redis://localhost:6379/4` | Backend de resultados. No stack: `redis://redis:6379/4`. |
| `CELERY_QUEUE` | não | `geral` | Fila consumida pelos workers (`bin/celery.sh`). |
| `CELERY_TASK_QUEUES` | não | vazio | Mapa extra de filas no formato `chave,valor:chave,valor`. |
| `FLOWER_BASIC_AUTH` | não | `usu4r10:s3nh4` | Basic auth do painel Flower (serviço opcional `celery-flower`, em `localhost:5555`). Formato `usuario:senha`. |

## E-mail

Em modo `DEBUG`, se `EMAIL_HOST` estiver vazio o SUAP usa o backend de debug
(grava em arquivo). O stack dev sobe o **Mailhog** (`mail:1025`, UI em
`http://localhost:8025`); apontar `EMAIL_HOST=mail` faz os e-mails caírem nele.

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `EMAIL_HOST` | não | vazio | Host SMTP. No stack: `mail`. |
| `EMAIL_PORT` | não | vazio | Porta SMTP. Mailhog: `1025`. |
| `EMAIL_HOST_USER` | não | vazio | Usuário SMTP. |
| `EMAIL_HOST_PASSWORD` | não | vazio | Senha SMTP. |
| `EMAIL_USE_TLS` | não | `False` | Usa TLS na conexão SMTP. |
| `EMAIL_BACKEND` | não | `djtools.core.mail.backends.smtp.EmailBackend` | Backend de envio de e-mail. |
| `EMAIL_LOGGING` | não | `db` | Destino(s) do log de e-mails (`db`, `file`...), separados por vírgula. |
| `DEFAULT_FROM_EMAIL` | não | `suap@naoresponder.ifrn.edu.br` | Remetente padrão. |
| `DEBUG_SMTP_CONNECTION` | não | `False` | Loga a conversa SMTP para depuração. |

## Armazenamento de arquivos (MinIO / S3)

Opt-in: o storage padrão em dev é o **filesystem**
(`djtools.storages.storage.FileSystemStoragePlus`). As credenciais abaixo só
entram em jogo se o storage S3 for ativado e também inicializam o MinIO
(`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`) no compose.

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `DEFAULT_FILE_STORAGE` | não | `FileSystemStoragePlus` | Backend de storage de mídia. Troque para o de S3 para usar MinIO. |
| `STATICFILES_STORAGE` | não | `CacheControlPipelineStorage` | Backend de arquivos estáticos. |
| `AWS_ACCESS_KEY_ID` | não | `admin` | Access key do S3/MinIO. |
| `AWS_SECRET_ACCESS_KEY` | não | `miniopassword` | Secret key do S3/MinIO. |
| `AWS_S3_ENDPOINT_URL` | não | `http://localhost:9000` | Endpoint do S3/MinIO. |
| `AWS_S3_REGION_NAME` | não | `us-east-2` | Região. |
| `AWS_S3_SIGNATURE_VERSION` | não | `s3v4` | Versão da assinatura. |
| `AWS_S3_CUSTOM_DOMAIN` | não | vazio | Domínio customizado para as URLs dos objetos. |
| `AWS_MEDIA_BUCKET_NAME` | não | `media` | Bucket de mídia pública. |
| `AWS_PRIVATE_MEDIA_BUCKET_NAME` | não | `media` | Bucket de mídia privada. |
| `AWS_STATIC_BUCKET_NAME` | não | `static` | Bucket de estáticos. |
| `AWS_TEMP_BUCKET_NAME` | não | `temp` | Bucket de arquivos temporários. |
| `AWS_QUERYSTRING_EXPIRE` | não | `86400` | Validade (s) das URLs assinadas. Padrão 24h. |

## Monitoramento (Sentry)

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `USE_SENTRY` | não | `False` | Ver toggles. Inicializa o SDK do Sentry. |
| `SENTRY_URL` | não | `http://token@sentry.ifrn.local/3` | DSN do Sentry. |
| `SENTRY_ENVIRONMENT` | não | `production` | Ambiente reportado ao Sentry. |
| `SENTRY_SAMPLE_RATE` | não | `0.0` | Taxa de amostragem de traces (0–1). |
| `SENTRY_PROFILE_RATE` | não | `0.0` | Taxa de amostragem de profiling (0–1). |
| `SENTRY_JS` | não | URL do loader IFRN | Script do Sentry para o front-end. |

## Segurança / cookies / CSRF

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `CSRF_TRUSTED_ORIGINS` | não | vazio | Origens confiáveis para CSRF (separadas por vírgula). |
| `CSRF_COOKIE_HTTPONLY` | não | `True` | Marca o cookie CSRF como HttpOnly. |
| `CSRF_COOKIE_SECURE` | não | `True` | Envia o cookie CSRF só por HTTPS. Em dev costuma ser `False`. |
| `CSRF_COOKIE_NAME` | não | `__Host-csrftoken` | Nome do cookie CSRF. O prefixo `__Host-` exige HTTPS; em dev use `csrftoken`. |
| `SESSION_COOKIE_NAME` | não | `__Host-sessionid` | Nome do cookie de sessão. Em dev use `sessionid`. |
| `SESSION_COOKIE_SECURE` | não | `True` | Envia o cookie de sessão só por HTTPS. |
| `SUAP_CONTROL_COOKIE_NAME` | não | `__Host-suap-control` | Nome do cookie de controle do SUAP. |
| `SESSION_LOCK` | não | `False` | Ativa o bloqueio/serialização de sessão (middleware `SessionLock`). |
| `RECAPTCHA_PUBLIC_KEY` | não | vazio | Chave pública do reCAPTCHA. |
| `RECAPTCHA_PRIVATE_KEY` | não | vazio | Chave privada do reCAPTCHA. |

## API / OAuth2

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `OAUTH2_PROVIDER_APPLICATION_MODEL` | não | `api.AplicacaoOAuth2` | Model de aplicação OAuth2. |
| `OAUTH2_PROVIDER_SCOPES_BACKEND_CLASS` | não | `api.backends.SuapScopes` | Classe que define os escopos. |
| `OAUTH2_PROVIDER_APPLICATION_ADMIN_CLASS` | não | `api.admin.AplicacaoOAuth2Admin` | Admin da aplicação OAuth2. |
| `OAUTH2_PROVIDER_ACCESS_TOKEN_ADMIN_CLASS` | não | `api.admin.AccessTokenAdmin` | Admin dos access tokens. |

## Login Gov.br

Integração opcional. Sem `GOVBR_CLIENT_ID`/`GOVBR_SECRET_KEY` o login Gov.br
fica inativo; as demais variáveis apontam para o ambiente de *staging*.

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `GOVBR_CLIENT_ID` | não | — (sem default) | Client ID da aplicação Gov.br. |
| `GOVBR_SECRET_KEY` | não | — (sem default) | Secret da aplicação Gov.br. |
| `GOVBR_API_URL` | não | `https://api.staging.acesso.gov.br` | API do Gov.br. |
| `GOVBR_JWK_URL` | não | `.../jwk` (staging) | URL das chaves JWK. |
| `GOVBR_REDIRECT_URI` | não | `/accounts/login/` | URI de retorno após login. |
| `GOVBR_AUTHORIZATION_URL` | não | `.../authorize` (staging) | Endpoint de autorização. |
| `GOVBR_ACCESS_TOKEN_URL` | não | `.../token` (staging) | Endpoint de token. |
| `GOVBR_USER_DATA_URL` | não | `.../userinfo` (staging) | Endpoint de dados do usuário. |
| `GOVBR_SCOPES` | não | `openid,profile,phone,email,govbr_confiabilidades` | Escopos solicitados. |
| `GOVBR_LOGOUT_URL` | não | `.../logout?...` (staging) | URL de logout (recebe `SITE_URL`). |
| `GOVBR_PRIMARY_LOGIN` | não | `False` | Torna o Gov.br o método de login primário. |
| `GOVBR_USER_AUTO_UPDATE` | não | `False` | Atualiza dados do usuário a cada login. |
| `GOVBR_USER_AUTO_CREATE` | não | `False` | Cria o usuário no primeiro login Gov.br. |

## Uploads de arquivo (limites)

Valores em MB (convertidos internamente para bytes).

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `DEFAULT_FILE_UPLOAD_MAX_SIZE` | não | `10` | Tamanho máximo padrão de upload. |
| `FILE_UPLOAD_MAX_MEMORY_SIZE` | não | `5` | Acima disso o upload vai para disco em vez da memória. |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | não | `100` | Tamanho máximo do corpo do request (exceto uploads). |
| `PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE` | não | `10` | Limite de upload de documento externo no Processo Eletrônico. |

## Ferramentas externas (PDF)

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `WKHTMLTOPDF_CMD` | não | `/usr/bin/wkhtmltopdf` | Caminho do wkhtmltopdf (geração de PDFs). |
| `GHOSTSCRIPT_CMD` | não | `/usr/bin/gs` | Caminho do Ghostscript. |
| `QPDF_CMD` | não | `/usr/bin/qpdf` | Caminho do qpdf. |

## Requisições HTTP (saída)

Política de retry para chamadas a serviços externos (`requests`).

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `REQUESTS_MAX_RETRIES` | não | `5` | Número máximo de tentativas. |
| `REQUESTS_BACKOFF_FACTOR` | não | `1` | Fator de backoff entre tentativas. |
| `REQUESTS_STATUS_FORCELIST` | não | `104,429,500,502,503,504` | Status HTTP que disparam retry. |
| `REQUESTS_TIMEOUT` | não | `60` | Timeout (s) das requisições. |

## Testes (Behave)

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `BEHAVE_CHROME_HEADLESS` | não | `True` | Roda o Chrome em modo headless (`False` para ver o navegador). |
| `BEHAVE_AUTO_DOC` | não | `False` | Gera documentação automática a partir dos cenários. |
| `BEHAVE_AUTO_DOC_PATH` | não | `deploy/media/documentacao` | Diretório da documentação gerada. |
| `BEHAVE_AUTO_MOCK` | não | `False` | Gera mocks (SQL) automaticamente. |
| `BEHAVE_AUTO_MOCK_PATH` | não | `deploy/media/sql` | Diretório dos mocks gerados. |
| `BEHAVE_DEBUG_ON_ERROR` | não | `False` | Entra em modo debug ao falhar um cenário. |

## Regras de negócio acadêmicas (edu)

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `NOTA_DECIMAL` | não | `False` | Permite notas decimais. |
| `CASA_DECIMAL` | não | `0` | Casas decimais das notas (1 ou 2). |
| `COMPONENTE_CH_DECIMAL` | não | `False` | Permite carga horária decimal nos componentes. |
| `PERIODO_LETIVO_CHOICES` | não | `1:1,2:2` | Opções de período letivo (`valor:rótulo`). |
| `TIPO_HORA_AULA_CHOICES` | não | `45:45 min,60:60 min` | Opções de duração da hora-aula. |
| `IMPEDIR_CHOQUE_HORARIOS_PROFESSOR` | não | `False` | Bloqueia choque de horários do professor. |
| `PERCENTUAL_CH_PREPARACAO_AULAS_PIT` | não | `100` | Percentual de CH de preparação de aulas no PIT. |
| `PERMITE_ALTERACAO_CH_PREPARACAO_AULAS_PIT` | não | `True` | Permite alterar a CH de preparação no PIT. |

## Outras configurações

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `ADMIN_QUICK_ACCESS` | não | `documents,webmail,groups,...` | Atalhos rápidos exibidos no admin. |
| `ADMIN_FILTER_REQUIRED_MODELS` | não | vazio | Models cujo admin exige filtro antes de listar. |
| `DISABLED_DEBUG_LOGGING_APPS` | não | vazio | Loggers extras a silenciar (somados aos padrões). |
| `SERVICE_PROVIDER_FACTORY` | não | factory padrão | Factory de provedores de serviço do catálogo. |
| `NUM_PROCESSO_DIVISOR_SUFIXO` | não | `.` | Separador do sufixo no número de processo. |

## Imagens / Docker

Usadas na interpolação do `docker-compose.dev.yml` (não chegam ao Django).

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `CONTAINERS` | não | — | Marca execução em containers (scripts de bootstrap). |
| `SUAP_IMAGE` | sim (compose) | — | Imagem base do SUAP (`web`, `celery`, `cron`...). |
| `SUAP_PDF_IMAGE` | sim (compose) | — | Imagem do serviço `pdfprinter`. |
| `SUAP_PDF_VOLUME_PATH` | sim (compose) | — | Caminho do volume montado no `pdfprinter`. |
| `SUAP_AI_IMAGE` | sim (compose) | — | Imagem do serviço `ai`. |
| `NGINX_SERVER_NAME` | não | — | `server_name` do Nginx (deploy com proxy). |
