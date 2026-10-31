"""Substrato da rodada de geração da doc de usuário do ``comum``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

Reusa por completo o substrato dos e2e do módulo (``comum/tests/e2e/conftest.py``) — o seed
por factories (``e2e_seed``), ``PAPEIS``/``logado_comum``, campus e as fábricas da família
salas — sem duplicar nada. Os dois star-imports são obrigatórios e nesta ordem:

1. ``djtools.e2e_fixtures`` traz os nomes **privados** (``_django_db_helper``,
   ``_exige_banco_de_e2e``), que ``import *`` do conftest do e2e não reexportaria — é a
   armadilha documentada em ``djtools/e2e_fixtures.py:53-57``;
2. o conftest do e2e traz ``e2e_seed``, ``servidores_comum``, ``logado_comum``, ``campus_e2e``
   e as fixtures da fatia salas. Tem de vir DEPOIS: invertida a ordem, o ``e2e_seed`` padrão do
   djtools (só ``semear_base``) sobrescreveria o do módulo e a doc rodaria sem os campi dele.

**O que esta rodada acrescenta, e por quê.** As fixtures do e2e nomeiam os objetos para o
teste (``E2E Sala 5f3a2b1c``, ``Reunião de equipe (fixture e2e)``); aqui o nome **aparece na
captura que o usuário final vai ler**. Por isso ``predio_e2e``, ``sala_agendavel``,
``solicitacao_pendente`` e ``indisponibilizacao`` são **sobrescritas** logo abaixo, com o
mesmo desenho e o mesmo teardown, trocando só o nome. Sobrescrever (e não criar fixtures
novas) é o que deixa ``reserva_deferida``, vinda do e2e sem alteração, encadear na
solicitação daqui.

A doc do ``comum`` é escrita em 6 fatias, em série; esta é a **fatia 1** (prédios, salas e
reservas de sala). As fatias seguintes acrescentam os seus arquivos ``test_0N_*.py`` e, se
precisarem, as suas fixtures ao fim deste arquivo — nunca editando as de outra fatia.

Rodar (a geração inteira, que é o que o CI faz)::

    DATABASE_HOST=localhost DATABASE_PORT=5433 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest -m doc --create-db comum/tests/doc/

A limpeza do destino das capturas é por **sessão** (ver ``capturas`` em
``djtools/e2e_fixtures.py``), então rodar uma fatia sozinha apaga as capturas das outras: é
regeneração parcial, útil para depurar a fatia, não para publicar.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from comum.tests.e2e.conftest import *  # noqa: F403
from djtools.e2e_ui import Tela

DESTINO = Path(settings.BASE_DIR) / 'comum' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Nomes que APARECEM NA CAPTURA. O prédio é de sessão (cadastro estável); a sala nasce e morre
# em cada teste, como no e2e — o banco é reusado e sala que sobra faz as listagens paginarem.
NOME_PREDIO_DOC = 'Bloco Acadêmico I'
NOME_SALA_DOC = 'Sala de Reuniões 101'


def anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões, rótulos e opções de lista da tela para a redação da doc.

    Não é asserção: é o que substitui a leitura de ``views.py``/``models.py`` na hora de
    escrever o passo. Os rótulos importam especialmente aqui: metade dos campos desta família
    tem ``verbose_name`` montado por ``nomenclatura`` (``Campus``, ``Agendamento apenas por
    servidores do campus``), que só o HTML renderizado resolve.
    """
    tela.esperar()
    cabecalhos = [c.strip() for c in tela.pagina.get_by_role('heading').all_inner_texts() if c.strip()]
    despejo = (
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {cabecalhos}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}'
        f'\n  listas: {_opcoes_das_listas(tela)}\n'
    )
    # Arquivo, e não só stderr: quando a rodada fica VERDE o pytest engole o stderr capturado,
    # e é justamente a rodada verde que produz a doc.
    DESTINO.mkdir(parents=True, exist_ok=True)
    with (DESTINO / 'anotacoes.txt').open('a', encoding='utf-8') as arquivo:
        arquivo.write(despejo)
    sys.stderr.write(despejo)


def _opcoes_das_listas(tela: Tela) -> dict[str, list[str]]:
    """``nome do select -> rótulos das opções`` do formulário visível.

    O texto que a doc escreve ("Recorrência: Evento único, Diária, Semanal…") é o rótulo da
    opção, e ele não aparece em ``rotulos_na_tela``. Sem isto, cada valor de lista custa uma
    execução inteira para ser descoberto pela mensagem de erro do ``select_option``.
    """
    opcoes: dict[str, list[str]] = {}
    campos = tela.raiz.locator('//form//select[@name]')
    for indice in range(min(campos.count(), 40)):
        campo = campos.nth(indice)
        nome = campo.get_attribute('name') or ''
        textos = [texto.strip() for texto in campo.locator('option').all_inner_texts() if texto.strip() and texto.strip() != '---------']
        if nome and textos:
            opcoes[nome] = textos[:12]
    return opcoes


# ---------------------------------------------------------------------------------------
# Fatia 1 — prédios, salas e reservas de sala
# ---------------------------------------------------------------------------------------


@pytest.fixture(scope='session')
def predio_e2e(campus_e2e):
    """Sobrescreve a do e2e: mesmo desenho, nome que serve de ilustração."""
    from comum.models import Predio

    return Predio.objects.get_or_create(nome=NOME_PREDIO_DOC, uo=campus_e2e, defaults={'ativo': True})[0]


@pytest.fixture
def sala_agendavel(predio_e2e, servidores_comum):
    """Sobrescreve a do e2e: nome fixo (e não ``uuid``) porque ele aparece na captura.

    Nome fixo exige apagar ANTES e depois: o banco da doc é reusado entre fatias e o
    ``unique`` de fato da sala é o par (nome, prédio) na leitura do usuário.
    """
    from comum.models import Sala

    Sala.objects.filter(nome=NOME_SALA_DOC, predio=predio_e2e).delete()
    sala = Sala.objects.create(
        nome=NOME_SALA_DOC,
        predio=predio_e2e,
        ativa=True,
        agendavel=True,
        capacidade=30,
        informacoes_complementares='Sala com projetor, quadro branco e ar-condicionado.',
    )
    sala.avaliadores_de_agendamentos.add(servidores_comum['avaliador_sala'].get_user())

    yield sala

    Sala.objects.filter(pk=sala.pk).delete()


@pytest.fixture
def solicitacao_pendente(sala_agendavel, servidores_comum):
    """Sobrescreve a do e2e: mesma criação por ORM, justificativa que o leitor entende.

    ``reserva_deferida`` vem do conftest do e2e sem alteração e encadeia nesta.
    """
    from comum.models import SolicitacaoReservaSala

    dia = (datetime.now() + timedelta(days=3)).date()
    return SolicitacaoReservaSala.objects.create(
        sala=sala_agendavel,
        solicitante=servidores_comum['solicitante'].get_user(),
        data_solicitacao=datetime.now(),
        data_inicio=dia,
        hora_inicio=time(8, 0),
        data_fim=dia,
        hora_fim=time(10, 0),
        justificativa='Reunião de planejamento do semestre.',
        recorrencia=SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO,
        status=SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO,
        avaliador=None,
        cancelada_por=None,
    )


@pytest.fixture
def indisponibilizacao(sala_agendavel, servidores_comum):
    """Sobrescreve a do e2e: mesmo período futuro (``pode_excluir`` exige), outra justificativa."""
    from comum.models import IndisponibilizacaoSala

    dia = datetime.now() + timedelta(days=10)
    return IndisponibilizacaoSala.objects.create(
        sala=sala_agendavel,
        data_inicio=dia.replace(hour=8, minute=0, second=0, microsecond=0),
        data_fim=dia.replace(hour=18, minute=0, second=0, microsecond=0),
        usuario=servidores_comum['avaliador_sala'].get_user(),
        data=datetime.now(),
        justificativa='Manutenção elétrica programada.',
        cancelada_por=None,
    )


# ---------------------------------------------------------------------------------------
# Fatia 2 — autenticação e conta pessoal
# ---------------------------------------------------------------------------------------
#
# Fatia destrutiva por natureza: os fluxos trocam a senha, habilitam o 2FA e derrubam a sessão
# do usuário. Tudo roda sobre as contas descartáveis `conta_pessoal`/`conta_dois_fatores` de
# `PAPEIS`, abertas por `logado_efemero` (login próprio a cada teste) — o caminho de
# `logado_comum` passa por `storage_states`, que cacheia UM login por matrícula para a sessão
# inteira do pytest, e derrubá-lo deslogaria as fatias seguintes do mesmo papel.

# Nomes que APARECEM NAS CAPTURAS desta fatia.
NOME_DISPOSITIVO_DOC = 'Notebook de casa'
NOME_CELULAR_DOC = 'Celular'
SENHA_VAZADA_DOC = 'senha123'


@pytest.fixture
def duplo_fator_habilitado():
    """Liga ``comum.permite_autenticacao_duplo_fator`` — sem ela a ``Minha conta`` esconde o 2FA.

    O bloco "Verificação em duas etapas" e o botão que leva ao QR Code são condicionados a esta
    ``Configuracao`` (``comum/templates/minha_conta.html:194``). A tela do QR Code em si abre sem
    ela, mas aí a doc estaria descrevendo uma porta que o usuário não vê.

    O estado é reposto por ``update_or_create(valor='')`` e **não** por ``delete()``: só o
    ``save`` limpa ``_CONFIGURACAO_CACHED`` (``comum/models.py:1552``), de modo que apagar a
    linha deixaria o cache do processo respondendo "ligado" para o resto da sessão — e toda
    ``Minha conta`` das fatias seguintes cresceria um bloco a mais. Valor vazio é falsy, que é
    como ``get_valor_por_chave`` devolve "desligado".

    Com a chave ligada, ``AuthenticationFormPlus.clean_auth_code`` passa a exigir o código TOTP
    no login de **quem tem 2FA ativo**: nenhum teste desta fatia pode relogar depois de habilitar.
    """
    from comum.models import Configuracao

    chave = {'app': 'comum', 'chave': 'permite_autenticacao_duplo_fator'}
    descricao = 'Permite autenticação em duas etapas (fixture da doc)'
    Configuracao.objects.update_or_create(**chave, defaults={'valor': 'True', 'descricao': descricao})

    yield

    Configuracao.objects.update_or_create(**chave, defaults={'valor': '', 'descricao': descricao})


@pytest.fixture
def acessos_pessoais(conta_pessoal, servidores_comum):
    """Dois dispositivos do dono (cada um com uma sessão aberta) e um de outra pessoa.

    Faz mais do que a ``dispositivo_e2e`` do e2e — e por isso é fixture nova, e não sobrescrita:

    * **limpa os dispositivos sintéticos e as sessões** que sobraram de execuções anteriores. O
      banco da doc é reusado e cada rodada deixaria uma linha a mais na listagem que o usuário lê;
    * **nomeia** os dispositivos (``Notebook de casa``, ``Celular``), porque o nome vai à captura;
    * cria um dispositivo de **outra pessoa**, que é o contraexemplo: a listagem de quem não é da
      segurança da informação tem de mostrar só os próprios acessos. Sem ele, esse recorte seria
      afirmação lida de ``DeviceAdmin.get_queryset`` em vez de fato observado na tela.

    **São dois dispositivos, e não um, por causa de ``deactivate_device``**: ela expira TODAS as
    sessões do dispositivo (``comum/views.py:3931``). Com um só, desativá-lo mataria a sessão de
    que o passo seguinte — o "Deslogar" da tela de sessões — precisa, e a doc afirmaria uma ação
    sobre uma linha que já não a oferece (o admin esconde o botão de sessão expirada).

    O ``user_agent`` é único por construção: o ``Device`` real nasce no sinal ``user_logged_in``
    com ``get_or_create(user, user_agent)`` e todo contexto do Playwright manda o mesmo agente —
    sem o ``uuid``, desativar "o dispositivo do teste" expiraria a sessão em uso.
    """
    from types import SimpleNamespace

    from comum.models import Device, SessionInfo

    dono = conta_pessoal.get_user()
    outra_pessoa = servidores_comum['solicitante'].get_user()
    Device.objects.filter(user__in=[dono, outra_pessoa], user_agent__startswith='DOC ').delete()
    # As sessões do dono vindas de execuções anteriores: o login desta execução (`logado_efemero`,
    # chamado depois desta fixture) grava a sua, e é dela que a captura precisa — as velhas só
    # fariam a listagem crescer a cada rodada.
    SessionInfo.objects.filter(device__user=dono).delete()

    def _dispositivo(user, nome: str, ip: str):
        aparelho = Device.objects.create(user=user, user_agent=f'DOC {uuid.uuid4().hex}', friendly_name=nome)
        sessao = SessionInfo.objects.create(session_id=uuid.uuid4().hex, device=aparelho, ip_address=ip)
        return aparelho, sessao

    notebook, sessao_notebook = _dispositivo(dono, NOME_DISPOSITIVO_DOC, '10.0.0.20')
    celular, sessao_celular = _dispositivo(dono, NOME_CELULAR_DOC, '10.0.0.21')
    alheio, _sessao_alheia = _dispositivo(outra_pessoa, 'Dispositivo de outra pessoa', '10.0.0.99')

    yield SimpleNamespace(
        notebook=notebook,
        sessao_notebook=sessao_notebook,
        celular=celular,
        sessao_celular=sessao_celular,
        alheio=alheio,
    )

    # Em cascata: leva as `SessionInfo` junto.
    Device.objects.filter(pk__in=[notebook.pk, celular.pk, alheio.pk]).delete()


@pytest.fixture
def senhas_expostas(conta_pessoal, servidores_comum):
    """``(registro do dono, registro de outra pessoa)`` para a tela ``Senhas Expostas``.

    A tela é uma listagem: sem registro nenhum ela não ilustra nada. O segundo registro é o
    contraexemplo do recorte por dono (``SenhaExpostaAdmin.get_queryset``), pelo mesmo motivo da
    ``acessos_pessoais``.

    A senha gravada é deliberadamente uma senha-lixo de dicionário, e **não** a
    ``SENHA_E2E`` das contas: o campo é exibido em claro na listagem, e a captura vai para a
    documentação.
    """
    from comum.models import SenhaExposta

    dono = conta_pessoal.get_user()
    outra_pessoa = servidores_comum['solicitante'].get_user()
    SenhaExposta.objects.filter(usuario__in=[dono, outra_pessoa]).delete()

    email_do_dono = conta_pessoal.get_vinculo().email_pessoal
    do_dono = SenhaExposta.objects.create(usuario=dono, email=email_do_dono, senha=SENHA_VAZADA_DOC, formato_senha='Texto puro')
    alheia = SenhaExposta.objects.create(usuario=outra_pessoa, email='outra.pessoa@exemplo.com', senha='outra123', formato_senha='Texto puro')

    yield do_dono, alheia

    SenhaExposta.objects.filter(pk__in=[do_dono.pk, alheia.pk]).delete()


# ---------------------------------------------------------------------------------------
# Fatia 3 — grupos, notificações e configuração do sistema
# ---------------------------------------------------------------------------------------
#
# A regra desta fatia vem do conftest do e2e e vale igual aqui: **grupo é o que dá permissão**,
# e as fatias 1, 2 e 4 a 6 dependem dos grupos de `PAPEIS`. Nenhum fluxo daqui muta papel
# compartilhado: quem entra e sai de grupo é o servidor descartável `alvo_grupo` (que nunca
# loga) ou a conta descartável `conta_pessoal`, e os grupos usados são os dois inertes do
# `permissions.yaml` do `comum`, que nascem vazios (`GRUPO_GERENCIADO`/`GRUPO_AUTOMATIZADO`).

# Nomes que APARECEM NAS CAPTURAS desta fatia.
CATEGORIA_NOTIFICACAO_DOC = 'Solicitação de reserva de sala avaliada'
SISTEMA_EM_MANUTENCAO_DOC = 'Portal do Aluno'
MOTIVO_NO_GRUPO_DOC = 'Passou a responder pelo atendimento do setor.'
MOTIVO_DA_MANUTENCAO_DOC = 'Atualização de versão do banco de dados.'


@pytest.fixture
def preferencia_notificacao(servidores_comum):
    """Sobrescreve a do e2e: mesmo desenho, assunto que o leitor da doc entende.

    A do e2e sufixa o assunto com ``uuid`` para a listagem paginada não misturar execuções;
    aqui o assunto **aparece na captura**, então ele é fixo e a limpeza vai para o SETUP — o
    banco da doc é reusado entre as seis fatias e entre execuções.

    ``forcar_habilitacao=False`` é o que mantém a categoria governável pelo usuário: é esse o
    filtro das seis views de preferência, e com ele ligado os botões da tela não fazem nada.
    """
    from comum.models import CategoriaNotificacao, PreferenciaNotificacao

    CategoriaNotificacao.objects.filter(assunto=CATEGORIA_NOTIFICACAO_DOC).delete()
    categoria = CategoriaNotificacao.objects.create(assunto=CATEGORIA_NOTIFICACAO_DOC, ativa=True, forcar_habilitacao=False)
    preferencia = PreferenciaNotificacao.objects.create(
        categoria=categoria,
        vinculo=servidores_comum['solicitante'].get_vinculo(),
        via_suap=True,
        via_email=True,
    )

    yield categoria, preferencia

    PreferenciaNotificacao.objects.filter(pk=preferencia.pk).delete()
    CategoriaNotificacao.objects.filter(pk=categoria.pk).delete()


@pytest.fixture
def manutencao_limpa():
    """Apaga — antes e depois — a parada programada que a tarefa cadastra PELA TELA.

    Os dois lados importam, e o de entrada mais que o de saída: ``proximas_atualizacoes``
    devolve a manutenção para **todo mundo** quando ``vinculos_publico`` está vazio, que é o
    caso do cadastro sem público específico. Uma linha esquecida no banco reusado poria o aviso
    *Fique atento!* na página inicial de todos os papéis das outras fatias — e a captura da
    fatia 5 sairia com um alerta que o teste dela não criou.
    """
    from comum.models import ManutencaoProgramada

    ManutencaoProgramada.objects.filter(sistema_ou_servico=SISTEMA_EM_MANUTENCAO_DOC).delete()

    yield

    ManutencaoProgramada.objects.filter(sistema_ou_servico=SISTEMA_EM_MANUTENCAO_DOC).delete()


@pytest.fixture
def conta_administravel(servidores_comum):
    """``alvo_grupo`` com a conta reposta no SETUP — o alvo das ações em massa de usuário.

    Reposição na entrada pelo mesmo motivo de ``_repor_conta``: ``is_active=False`` esquecido no
    banco reusado quebraria a tarefa dos grupos sem deixar pista — ``gerenciamento_grupo`` filtra
    ``user_set.filter(is_active=True)`` e o cartão simplesmente apareceria vazio.

    ``update`` e não ``save()``: ``User.save`` do SUAP re-sincroniza grupos e vínculo, e o que se
    quer aqui é só devolver as três colunas que os fluxos mexem.
    """
    from comum.models import User

    servidor = servidores_comum['alvo_grupo']
    User.objects.filter(pk=servidor.get_user().pk).update(is_active=True, forcar_troca_senha=False, data_solicitacao_forcar_troca_senha=None)
    return servidor


# ---------------------------------------------------------------------------------------
# Fatia 4 — documentos: assinatura digital, autenticação, solicitações e telefones de setor
# ---------------------------------------------------------------------------------------
#
# Três decisões governam a fatia, e as duas primeiras vêm do conftest do e2e:
#
# 1. **Os artefatos de criptografia são os arquivos já versionados** em
#    `comum/tests/arquivos/assinatura-digital/` — o mesmo `.p12` que `comum.signer.test()` usa.
#    Ele é autoassinado e EXPIROU em 26/11/2024, o que parte a tarefa em duas: o certificado
#    cadastrado pela tela nasce vencido (o formulário lê a validade do próprio arquivo) e
#    `AssinarDocumentoForm` filtra `validade__gte=hoje`. Os dois lados são exercitados — o
#    cadastro pela tela, e a assinatura com o certificado de validade futura desta fixture.
# 2. **O setor que os fluxos mutam nasce e morre no teste.** Os papéis de `PAPEIS` guardam o
#    setor no `Vinculo`, e `User.VINCULOS` é cache de processo: mexer no setor deles não chega
#    ao `live_server`.
# 3. **Nome legível em tudo o que aparece na captura.** As fixtures do e2e sufixam `uuid` para a
#    listagem paginada não misturar execuções; aqui o texto vai para a doc, então o nome é fixo e
#    a limpeza vai para o SETUP — o banco da doc é reusado entre as seis fatias e entre execuções.

# Nomes que APARECEM NAS CAPTURAS desta fatia.
TIPO_DOCUMENTO_EMITIDO_DOC = 'Declaração de Vínculo'
TIPO_SOLICITADO_DOC = 'Crachá'
JUSTIFICATIVA_DOC = 'Crachá danificado; preciso da segunda via para o controle de acesso.'
LOCAL_IMPRESSAO_DOC = 'Natal/RN'
SIGLA_SETOR_DOC = 'COATE'
NOME_SETOR_DOC = 'Coordenação de Atendimento ao Público'
TELEFONE_DO_SETOR_DOC = '(84) 4005-4002'
RAMAL_DO_SETOR_DOC = '4002'
RAMAL_NOVO_DOC = '4711'


@pytest.fixture
def certificados_do_papel(servidores_comum):
    """Zera os certificados digitais do papel da fatia — no SETUP e na saída.

    Existe porque UM dos fluxos cria o certificado **pela tela**, e o que a tela cria nenhuma
    fixture desfaz: sem esta limpeza a listagem que a captura mostra cresceria uma linha por
    execução no banco reusado (armadilha 7 da fatia 2). Apaga também o arquivo no
    ``default_storage``, que o ``delete()`` do model não leva junto.
    """
    from comum.models import CertificadoDigital

    dono = servidores_comum['diretor_geral'].get_user()

    def _limpar():
        for certificado in CertificadoDigital.objects.filter(user=dono):
            certificado.arquivo.delete(save=False)
            certificado.delete()

    _limpar()
    yield dono
    _limpar()


@pytest.fixture
def certificado_digital(certificados_do_papel):
    """Sobrescreve a do e2e: do papel da fatia (e não do superusuário) e com metadados de verdade.

    ``nome``/``organizacao``/``unidade`` são os que ``CertificadoDigitalForm.save`` extrairia do
    próprio ``.p12`` (é o ``subject`` do certificado), porque eles **aparecem na captura**: o
    campo *Certificado* da tela de assinatura é o ``__str__`` do model, ``nome - organização -
    (VÁLIDO ATÉ ...)``. A validade, e só ela, é inventada no futuro — é o único metadado que a
    tela de assinatura consulta, e o arquivo versionado venceu em 26/11/2024.
    """
    from django.core.files.base import ContentFile

    from comum.models import CertificadoDigital

    with open(os.path.join(settings.BASE_DIR, ARQUIVO_P12), 'rb') as arquivo:  # noqa: F405
        conteudo = arquivo.read()

    certificado = CertificadoDigital(
        user=certificados_do_papel,
        nome=ASSINANTE,  # noqa: F405
        organizacao='IFRN',
        unidade='COSINF',
        validade=(datetime.now() + timedelta(days=365)).date(),
        conteudo='',
    )
    certificado.arquivo.save(f'doc-{uuid.uuid4().hex[:8]}.p12', ContentFile(conteudo), save=True)

    yield certificado

    certificado.arquivo.delete(save=False)
    CertificadoDigital.objects.filter(pk=certificado.pk).delete()


@pytest.fixture
def certificado_alheio(servidores_comum):
    """Certificado de OUTRA pessoa — o contraexemplo do recorte por dono.

    Mesmo papel do contraexemplo da fatia 2 (``acessos_pessoais``, ``senhas_expostas``): sem ele,
    "cada pessoa vê apenas os próprios certificados" seria afirmação lida de
    ``CertificadoDigitalAdmin.get_queryset`` em vez de fato observado na listagem.
    """
    from comum.models import CertificadoDigital

    outra_pessoa = servidores_comum['solicitante'].get_user()
    CertificadoDigital.objects.filter(user=outra_pessoa).delete()
    certificado = CertificadoDigital.objects.create(
        user=outra_pessoa,
        nome='Certificado de outra pessoa',
        organizacao='IFRN',
        unidade='COSINF',
        validade=(datetime.now() + timedelta(days=365)).date(),
        conteudo='',
    )

    yield certificado

    CertificadoDigital.objects.filter(pk=certificado.pk).delete()


@pytest.fixture
def registro_emissao_documento():
    """Sobrescreve a do e2e: mesmo PDF assinado, **tipo legível** — ele vai à captura.

    A do e2e sufixa o tipo com ``uuid`` porque o formulário público monta a lista de tipos com
    ``values_list('tipo').distinct()`` sobre a tabela inteira; aqui o tipo é o rótulo que o leitor
    da doc lê no campo *Tipo de Documento*, então ele é fixo e a limpeza vai para o SETUP. Um
    registro esquecido de execução anterior não quebraria o formulário — ``get_registros`` casa
    tipo **e** código —, mas duplicaria a opção da lista na imagem.
    """
    from django.core.files.base import ContentFile

    from comum.models import RegistroEmissaoDocumento

    RegistroEmissaoDocumento.objects.filter(tipo=TIPO_DOCUMENTO_EMITIDO_DOC).delete()

    with open(os.path.join(settings.BASE_DIR, ARQUIVO_PDF_ASSINADO), 'rb') as arquivo:  # noqa: F405
        conteudo = arquivo.read()

    registro = RegistroEmissaoDocumento(
        tipo=TIPO_DOCUMENTO_EMITIDO_DOC,
        data_emissao=datetime.now().date(),
        codigo_verificador=uuid.uuid4().hex[:12].upper(),
    )
    registro.documento.save(f'doc-{registro.codigo_verificador}.pdf', ContentFile(conteudo), save=True)

    yield registro

    # `RegistroEmissaoDocumento.delete` apaga o arquivo no storage junto com a linha.
    RegistroEmissaoDocumento.objects.filter(pk=registro.pk).delete()


@pytest.fixture
def solicitacao_documento(servidores_comum, campus_e2e):
    """Sobrescreve a do e2e: ``bulk_create`` igual, texto legível e o campus **configurado**.

    O ``bulk_create`` é obrigatório e não é estilo: ``DocumentoControle.save`` grava o histórico
    com ``request.user.get_vinculo()`` a partir do threadlocal do djtools, que numa fixture está
    vazio — ``objects.create`` levanta ``AttributeError``. O histórico que o ``save`` gravaria
    nasce logo abaixo por ORM, porque é ele que a tela de acompanhamento lista.

    **O que esta fixture acrescenta ao seed, e sem o que a tarefa não existe:** a
    ``ConfiguracaoImpressaoDocumento`` do campus. Medido — sem ela a listagem do admin abre
    vazia mesmo para a Gestão de Pessoas: ``DocumentoControleAdmin.regras_filtro_queryset``
    monta a lista a partir das configurações de impressão do campus de quem olha, e sem nenhuma
    cai no ramo final, que devolve só as solicitações **do próprio usuário**. O seed não
    traz configuração de impressão nenhuma, nem tipo de documento nenhum.

    ``identificador='cracha'`` não é enfeite: é ele que faz ``DocumentoControleAdminFormFactory``
    encontrar o tipo suportado (``.get(identificador=CRACHA)``, que sem nenhum tipo cadastrado
    levanta ``DoesNotExist`` e derruba a tela de cadastro com HTTP 500). Como
    ``DocumentoControleTipo.save`` reescreve a descrição a partir do identificador, o rótulo que
    vai à captura é o oficial, *Crachá*.
    """
    from djtools.choices import SituacaoSolicitacaoDocumento

    from comum.models import ConfiguracaoImpressaoDocumento, DocumentoControle, DocumentoControleHistorico, DocumentoControleTipo
    from rh.models import Situacao

    DocumentoControleTipo.objects.filter(descricao=TIPO_SOLICITADO_DOC).delete()
    tipo = DocumentoControleTipo.objects.create(descricao=TIPO_SOLICITADO_DOC, identificador=DocumentoControleTipo.CRACHA)
    tipo.abrangencia.add(Situacao.objects.get(codigo=Situacao.ATIVO_PERMANENTE))

    # Escopo é a própria linha (campus + local), não o campus inteiro: o CI roda `pytest -m doc`
    # de todos os módulos num processo e num banco só, e varrer por `uo=` apagaria a configuração
    # de impressão que outra suíte de doc tenha criado para o mesmo campus. O model não tem
    # unicidade em `uo`, então conviver com a linha alheia é seguro.
    ConfiguracaoImpressaoDocumento.objects.filter(uo=campus_e2e, local_impressao=LOCAL_IMPRESSAO_DOC).delete()
    configuracao = ConfiguracaoImpressaoDocumento.objects.create(uo=campus_e2e, local_impressao=LOCAL_IMPRESSAO_DOC)
    configuracao.relacao_impressao.add(campus_e2e)
    configuracao.tipos_documento.add(tipo)

    solicitante = servidores_comum['solicitante']
    solicitacao = DocumentoControle.objects.bulk_create(
        [
            DocumentoControle(
                documento_tipo=tipo,
                solicitante_vinculo=solicitante.get_vinculo(),
                justificativa=JUSTIFICATIVA_DOC,
                ativo=True,
                status_solicitacao=SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
            )
        ]
    )[0]
    DocumentoControleHistorico.objects.create(
        solicitacao=solicitacao,
        responsavel_vinculo=solicitante.get_vinculo(),
        situacao_historico=SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
        motivo=solicitacao.justificativa,
    )

    yield tipo, solicitacao

    # Em cascata: o histórico vai com a solicitação, e a solicitação com o tipo.
    ConfiguracaoImpressaoDocumento.objects.filter(pk=configuracao.pk).delete()
    DocumentoControleTipo.objects.filter(pk=tipo.pk).delete()


@pytest.fixture
def setor_descartavel(campus_e2e):
    """Sobrescreve a do e2e: setor descartável com **sigla e nome legíveis**.

    Legíveis porque os dois aparecem em duas capturas (a lista telefônica e a página do setor);
    descartável — e nunca um setor de ``PAPEIS`` — porque os fluxos GRAVAM nele (telefone,
    e-mail) e o ``Vinculo`` dos papéis compartilhados guarda o setor num cache de processo.

    ``instance.delete()`` e não ``queryset.delete()``, nos dois lados: só o ``delete()`` do model
    invalida o ``_SETOR_MAP`` que ``rh.models.Setor`` mantém por processo — pelo caminho do
    queryset o setor apagado continuaria vivo no ``live_server``.
    """
    from rh.models import Setor

    for antigo in Setor.objects.filter(sigla=SIGLA_SETOR_DOC):
        antigo.delete()

    setor = Setor.objects.create(
        sigla=SIGLA_SETOR_DOC,
        nome=NOME_SETOR_DOC,
        codigo=None,
        superior=Setor.objects.get(sigla=SIGLA_CAMPUS, codigo=None),  # noqa: F405
    )
    yield setor
    setor.delete()


@pytest.fixture
def telefone_do_setor(setor_descartavel):
    """Telefone já cadastrado no setor descartável — a linha de partida da lista telefônica."""
    from comum.models import SetorTelefone

    return SetorTelefone.objects.create(
        setor=setor_descartavel,
        numero=TELEFONE_DO_SETOR_DOC,
        ramal=RAMAL_DO_SETOR_DOC,
        observacao='Atendimento ao público',
    )


# ---------------------------------------------------------------------------------------
# Fatia 5 — a página inicial e a aparência do sistema
# ---------------------------------------------------------------------------------------
#
# A fatia é a mais "de todo usuário" de todas — a página inicial é a primeira tela que qualquer
# pessoa vê — e, por isso mesmo, a mais pegajosa: tema, menu retraído, leiaute dos quadros,
# atalho e notificação ficam gravados NO USUÁRIO, e o banco da doc é reusado entre as seis
# fatias. Tudo aqui roda sobre o papel descartável `dono_do_inicio`, por `logado_efemero`, e o
# estado é reposto no SETUP por `usuario_do_inicio` (herdada do e2e, sem alteração): nenhum
# papel de `PAPEIS` sai daqui com tema trocado ou atalho grudado.
#
# As três fixtures abaixo são SOBRESCRITAS da e2e (armadilha 4 da fatia 1): mesmo desenho, mesmo
# teardown, só o nome muda — porque aqui o nome vai para a captura que o usuário final lê
# (`E2E Atalho 3f9a1c`, `SUAP E2E 7b2d41` e `E2E Reserva deferida 9c1e…` seriam o texto do guia).

# Nomes que APARECEM NAS CAPTURAS desta fatia.
NOME_ATALHO_DOC = 'Lista telefônica'
NOME_ATALHO_NOVO_DOC = 'Notificações'
SISTEMA_EM_PARADA_DOC = 'Sistema Acadêmico'
MOTIVO_DA_PARADA_DOC = 'Atualização de versão do sistema acadêmico.'
COMENTARIO_DOC = 'Prédio com obra de acessibilidade prevista para o próximo semestre.'


@pytest.fixture
def atalho_do_inicio(usuario_do_inicio):
    """Sobrescreve a do e2e: atalho já cadastrado, com nome que serve de ilustração.

    O nome é o texto do item no quadro *Atalhos* da página inicial — é ele que a captura mostra.
    Nome fixo exige apagar antes: ``_repor_inicio`` já zera os atalhos do papel no setup, mas a
    limpeza explícita aqui mantém a fixture correta se alguém a usar sem aquela.

    E o nome é ``Lista telefônica``, e não ``Minha conta``, porque a página inicial já traz um
    **quadro** chamado *Minha conta*: com o nome repetido, "o quadro Atalhos sumiu da coluna"
    passaria a ser afirmado por um texto que outro quadro também imprime. Medido — a asserção
    falhou sobre o título do quadro vizinho, não sobre o atalho.
    """
    from comum.models import Atalho

    usuario = usuario_do_inicio.get_user()
    Atalho.objects.filter(usuario=usuario, nome__in=[NOME_ATALHO_DOC, NOME_ATALHO_NOVO_DOC]).delete()
    atalho = Atalho.objects.create(usuario=usuario, nome=NOME_ATALHO_DOC, url='/comum/telefones/')

    yield atalho

    Atalho.objects.filter(pk=atalho.pk).delete()


@pytest.fixture
def manutencao_programada(usuario_do_inicio):
    """Sobrescreve a do e2e: mesma janela de datas, sistema e motivo legíveis.

    A janela é o que faz o aviso existir: ``proximas_atualizacoes`` só devolve a parada depois de
    ``data_hora_inicio_notificacao`` e antes de ``data_hora_atualizacao``. Fora dela o *Fique
    atento!* não renderiza e a captura sairia sem o que a doc descreve.

    O nome do sistema é outro (e não o ``SISTEMA_EM_MANUTENCAO_DOC`` da fatia 3) de propósito: a
    ``manutencao_limpa`` daquela fatia apaga **por nome** na entrada e na saída, e as duas fatias
    dividem o banco.

    ``usuario`` vai explícito porque o campo é ``CurrentUserField``: numa fixture não há request
    no threadlocal do djtools e o default cairia em ``AnonymousUser``/``None``.
    """
    from comum.models import ManutencaoProgramada

    agora = datetime.now()
    ManutencaoProgramada.objects.filter(sistema_ou_servico=SISTEMA_EM_PARADA_DOC).delete()
    manutencao = ManutencaoProgramada.objects.create(
        usuario=usuario_do_inicio.get_user(),
        tipo=ManutencaoProgramada.MANUTENCAO,
        sistema_ou_servico=SISTEMA_EM_PARADA_DOC,
        data_hora_atualizacao=agora + timedelta(days=2),
        previsao_minutos_inatividade=30,
        data_hora_inicio_notificacao=agora - timedelta(days=1),
        motivo=MOTIVO_DA_PARADA_DOC,
    )

    yield manutencao

    ManutencaoProgramada.objects.filter(pk=manutencao.pk).delete()


@pytest.fixture
def notificar_o_inicio(usuario_do_inicio):
    """Sobrescreve a do e2e: ``(assunto, mensagem, quantidade=1, dias_atras=0)`` com assunto FIXO.

    O assunto é o título que a caixa de notificações imprime (``RegistroNotificacao.get_assunto``
    devolve ``notificacao.categoria.assunto``), isto é, exatamente o texto que a captura mostra —
    daí ele não levar o ``uuid`` que a do e2e usa para não misturar execuções na listagem.

    O resto é a do e2e, e cada linha continua valendo:

    * ``send_notification`` (o caminho de produção) e não um ``create`` cru, porque é ele que cria
      a ``PreferenciaNotificacao`` do par (vínculo, categoria) — sem ela ``notificacao_ancora.html``
      chama ``get_preferencia_via_suap`` sobre ``None`` e ``/comum/notificacoes/`` responde 500;
    * ``objeto=None``, para a caixa não agrupar e esconder as notificações do mesmo objeto;
    * ``dias_atras`` por ``queryset.update``, porque as três datas são ``auto_now_add``;
    * a guarda do ``Device``: **logue antes de notificar**. O primeiro login de um dispositivo
      gera o alerta "dispositivo desconhecido", com bloqueio de leitura por três dias; criado
      depois, ele vira a primeira da caixa e nada mais é marcado como lido.

    O que esta versão acrescenta é a limpeza das categorias pelo assunto no SETUP: com nome fixo e
    banco reusado, uma execução interrompida deixaria a categoria para trás e a caixa da captura
    cresceria uma linha a cada rodada.
    """
    from django.conf import settings as configuracoes

    from djtools.utils import send_notification

    from comum.models import CategoriaNotificacao, Device, RegistroNotificacao

    vinculo = usuario_do_inicio.get_vinculo()
    categorias: list[str] = []

    def _notificar(assunto: str, mensagem: str, quantidade: int = 1, dias_atras: int = 0) -> list:
        if not categorias:
            assert Device.objects.filter(user=vinculo.user).exists(), (
                'logue o papel `dono_do_inicio` ANTES de criar notificações: o primeiro login de um dispositivo '
                'gera o alerta "dispositivo desconhecido", que entraria na caixa depois das do teste'
            )
            RegistroNotificacao.objects.filter(vinculo=vinculo).delete()
        CategoriaNotificacao.objects.filter(assunto=assunto).delete()
        categorias.append(assunto)
        for _ in range(quantidade):
            send_notification(assunto, mensagem, configuracoes.DEFAULT_FROM_EMAIL, [vinculo], categoria=assunto, so_notificar=True)
        registros = RegistroNotificacao.objects.filter(vinculo=vinculo, notificacao__categoria__assunto=assunto)
        if dias_atras:
            antiga = datetime.now() - timedelta(days=dias_atras)
            registros.update(data=antiga, data_permite_marcar_lida=antiga, data_permite_excluir=antiga)
        return list(registros.order_by('data'))

    yield _notificar

    RegistroNotificacao.objects.filter(vinculo=vinculo).delete()
    CategoriaNotificacao.objects.filter(assunto__in=categorias).delete()


# ---------------------------------------------------------------------------------------
# Fatia 6 — pessoas, prestadores de serviço e usuários externos
# ---------------------------------------------------------------------------------------
#
# A regra desta fatia é a mais dura do módulo, e vem do conftest do e2e: `PessoaFisica` e
# `Vinculo` são o substrato de TODO o SUAP — as outras cinco fatias, os 90 apps e o próprio
# login dependem deles. Por isso nenhum fluxo que mute pessoa toca um papel de `PAPEIS`: o
# prestador que aparece nas capturas nasce e morre no teste, e as duas telas que gravam num
# papel compartilhado (contatos de emergência e biometria do `solicitante`) são aditivas e
# zeradas no SETUP pelas fixtures herdadas do e2e.
#
# O que esta rodada acrescenta ao e2e é o NOME: `prestador_e2e` chama a pessoa de
# `E2E Prestador 5f3a2b1c`, e é ela o assunto de sete capturas desta fatia — a decisão que a
# fatia 3 (armadilha 9) deixou explicitamente para cá. A fixture é sobrescrita com nome de
# gente, e com matrícula e CPF FIXOS, derivados de uma marca hexadecimal estável; nome fixo em
# banco reusado exige apagar no SETUP, e não só no teardown.

# Nomes que APARECEM NAS CAPTURAS desta fatia.
NOME_PRESTADOR_DOC = 'Marina Alves Pereira'
NOME_NOVO_EXTERNO_DOC = 'Ricardo Nunes Barbosa'
PERFIL_EXTERNO_DOC = 'Prestador de serviço terceirizado'
EMAIL_NOVO_EXTERNO_DOC = 'ricardo.barbosa@exemplo.com.br'
EMAIL_CORRIGIDO_DOC = 'marina.pereira@exemplo.com.br'
CONTATO_EMERGENCIA_DOC = 'Maria Alves Pereira (mãe)'
TELEFONE_EMERGENCIA_DOC = '(84) 3215-1234'
TITULO_REUNIAO_DOC = 'Reunião Ordinária do Conselho Superior'
TITULO_REUNIAO_NOVA_DOC = 'Reunião Extraordinária do Conselho Superior'
LOCAL_REUNIAO_DOC = 'Auditório da Reitoria'
PAUTA_REUNIAO_DOC = 'Aprovação do calendário acadêmico do próximo ano.'

# Marcas hexadecimais das duas pessoas descartáveis. **Hexadecimais** porque
# `_matricula_descartavel` faz `int(marca, 16)`: uma marca com letra fora de a-f estoura com
# `ValueError` dentro da fixture, antes de qualquer tela.
MARCA_PRESTADOR_DOC = 'd0c6a1e5'
MARCA_NOVO_EXTERNO_DOC = 'd0c6b2f4'


def _matricula_e_cpf(marca: str) -> tuple[str, str]:
    """``(matrícula, CPF)`` estáveis de uma pessoa descartável desta fatia.

    Os dois helpers vêm do conftest do e2e **por importação nomeada**: eles começam com
    ``_``, e ``import *`` não traz nome com underscore (é a mesma armadilha que o cabeçalho
    deste arquivo documenta para ``_django_db_helper``). Sem isto a falha seria um
    ``NameError`` no teardown de uma fixture — depois de o teste passar.
    """
    from comum.tests.e2e.conftest import _cpf_para, _matricula_descartavel

    return _matricula_descartavel(marca), _cpf_para(marca)


def _apagar_pessoas_descartaveis(matricula: str, cpf: str) -> None:
    """Apaga prestador, vínculo, usuário, papéis e TODA pessoa física com aquele CPF.

    Mais abrangente que o ``_apagar_prestador`` do e2e de propósito: aqui o CPF é fixo, o banco
    é reusado entre as seis fatias e entre execuções. Uma execução interrompida deixaria a pessoa para trás e o cadastro pela tela passaria a
    responder *"Este CPF já está sendo usado por outro prestador."* — erro de validação, não de
    tela, e sem pista nenhuma do motivo.
    """
    from django.db.models import Q
    from rh.models import PessoaFisica

    from comum.models import PrestadorServico, Vinculo
    from comum.tests.e2e.conftest import _apagar_prestador

    for antigo in PrestadorServico.objects.filter(Q(matricula=matricula) | Q(pessoa_fisica__cpf=cpf)):
        _apagar_prestador(antigo)
    # O que sobrar é pessoa sem prestador — o meio-caminho de uma execução interrompida.
    # `Vinculo.pessoa` aponta para `rh.Pessoa`, de que `PessoaFisica` herda:
    # o pk é o mesmo, então o filtro pela pessoa física alcança o vínculo.
    for pessoa in PessoaFisica.objects.filter(cpf=cpf):
        for vinculo in Vinculo.objects.filter(pessoa_id=pessoa.pk):
            user = vinculo.user
            vinculo.delete()
            if user:
                user.delete()
        pessoa.delete()


@pytest.fixture
def prestador_e2e(campus_e2e):
    """Sobrescreve a do e2e: **nome de gente**, matrícula e CPF fixos, limpeza nos dois lados.

    O desenho é o da fixture do e2e, inclusive a reposição do setor por ``queryset.update``
    (``PrestadorServico.save()`` anula o setor porque a equivalência SIAPE↔SUAP não está
    montada no seed) — o que muda é só o que **aparece na captura**: sete telas desta fatia têm
    esta pessoa como assunto, e ``E2E Prestador 5f3a2b1c`` seria o nome que o leitor do guia
    veria em todas elas.

    Identificadores fixos, e não derivados de ``uuid4`` como no e2e, porque o CPF também vai à
    tela — e porque o cadastro pela tela (tarefa 28) valida CPF duplicado. O preço do nome fixo
    é a limpeza no SETUP: o banco da doc é reusado entre fatias e entre execuções.
    """
    from rh.enums import Nacionalidade
    from rh.models import Setor

    from comum.models import PrestadorServico, Vinculo
    from comum.tests.e2e.conftest import _apagar_prestador
    from comum.tests.factories import PrestadorServicoFactory

    matricula, cpf = _matricula_e_cpf(MARCA_PRESTADOR_DOC)
    _apagar_pessoas_descartaveis(matricula, cpf)

    setor = Setor.objects.get(sigla=SIGLA_CAMPUS, codigo=None)  # noqa: F405
    # `sexo` e `nacionalidade` vão explícitos porque a ficha do usuário externo os IMPRIME: sem
    # eles a captura que o leitor vê traz `Sexo: None` e `Nacionalidade: -`. A `PessoaFisicaFactory`
    # só preenche nome e CPF — ela serve a testes que não olham a tela.
    prestador = PrestadorServicoFactory(
        matricula=matricula,
        setor=setor,
        pessoa_fisica__nome=NOME_PRESTADOR_DOC,
        pessoa_fisica__cpf=cpf,
        pessoa_fisica__sexo='F',
        pessoa_fisica__nacionalidade=Nacionalidade.BRASILEIRO_NATO,
    )
    PrestadorServico.objects.filter(pk=prestador.pk).update(setor=setor)
    Vinculo.objects.filter(pk=prestador.get_vinculo().pk).update(setor=setor)
    prestador.refresh_from_db()

    yield prestador

    _apagar_prestador(prestador)


@pytest.fixture
def perfil_de_usuario_externo():
    """O *Perfil* que o cadastro de usuário externo exige — e que o seed NÃO traz.

    ``PrestadorServicoForm.justificativa_cadastro`` é obrigatório e sua lista é
    ``JustificativaUsuarioExterno.objects.filter(ativo=True)``; sem nenhuma linha o campo
    renderiza vazio e o cadastro pela tela é impossível — tela que não abre por falta de dado é
    tela não documentada. Acrescentar a linha é completar o seed, não inventar regra: é o mesmo
    cadastro que o menu publica em *Cadastros / Usuários Externos / Perfis para Usuários
    Externos*.
    """
    from comum.models import JustificativaUsuarioExterno

    JustificativaUsuarioExterno.objects.filter(justificativa=PERFIL_EXTERNO_DOC).delete()
    perfil = JustificativaUsuarioExterno.objects.create(justificativa=PERFIL_EXTERNO_DOC, ativo=True)

    yield perfil

    JustificativaUsuarioExterno.objects.filter(pk=perfil.pk).delete()


@pytest.fixture
def cadastro_de_externo_limpo():
    """``(nome, CPF, e-mail)`` da pessoa que a TAREFA cria pela tela — livres nos dois lados.

    Quem grava é o formulário do admin, e o que ele grava nenhuma fixture desfaz: sem esta
    limpeza a segunda execução esbarraria no ``clean`` (*"Este CPF já está sendo usado por
    outro prestador."*) e a doc afirmaria um cadastro que não aconteceu.
    """
    matricula, cpf = _matricula_e_cpf(MARCA_NOVO_EXTERNO_DOC)
    _apagar_pessoas_descartaveis(matricula, cpf)

    yield NOME_NOVO_EXTERNO_DOC, cpf, EMAIL_NOVO_EXTERNO_DOC

    _apagar_pessoas_descartaveis(matricula, cpf)


@pytest.fixture
def reuniao_colegiado():
    """Sobrescreve a do e2e: mesma janela de hoje, **título e pauta legíveis**.

    A do e2e sufixa o título com ``uuid`` para as execuções não se misturarem na listagem;
    aqui o título é o texto que a captura do calendário mostra, então ele é fixo e a limpeza
    vai para o SETUP. A janela é o que faz o calendário ter o que desenhar:
    ``ReuniaoOrgaoColegiado.query`` devolve ``none()`` fora do período filtrado.
    """
    from comum.models import ReuniaoOrgaoColegiado

    ReuniaoOrgaoColegiado.objects.filter(titulo__in=[TITULO_REUNIAO_DOC, TITULO_REUNIAO_NOVA_DOC]).delete()
    reuniao = ReuniaoOrgaoColegiado.objects.create(
        titulo=TITULO_REUNIAO_DOC,
        colegiado=ReuniaoOrgaoColegiado.ORGAO_CONSUP,
        descricao=PAUTA_REUNIAO_DOC,
        local=LOCAL_REUNIAO_DOC,
        data_inicio=datetime.now().date(),
        data_fim=datetime.now().date(),
        hora_inicio=time(9, 0),
        hora_fim=time(12, 0),
    )

    yield reuniao

    ReuniaoOrgaoColegiado.objects.filter(pk=reuniao.pk).delete()


@pytest.fixture
def reuniao_cadastrada_pela_tela():
    """Apaga — nos dois lados — a reunião que a TAREFA cadastra pelo admin.

    Mesma razão da ``cadastro_de_externo_limpo``: o que a tela grava nenhuma fixture desfaz, e
    o calendário da tarefa seguinte passaria a mostrar uma reunião por execução acumulada.
    """
    from comum.models import ReuniaoOrgaoColegiado

    ReuniaoOrgaoColegiado.objects.filter(titulo=TITULO_REUNIAO_NOVA_DOC).delete()

    yield

    ReuniaoOrgaoColegiado.objects.filter(titulo=TITULO_REUNIAO_NOVA_DOC).delete()
