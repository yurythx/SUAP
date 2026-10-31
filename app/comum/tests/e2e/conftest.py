"""Substrato dos e2e do ``comum``: servidores com grupo + o mobiliário da família salas.

O arquivo tem camadas deliberadamente separadas porque a suíte do ``comum`` cresce por fatias:

* **substrato reusável** — ``PAPEIS``/``servidores_comum``/``logado_comum``, a senha padrão e o
  prédio do campus. Qualquer fatia futura (grupos, notificações, prestador de serviço)
  acrescenta um papel em ``PAPEIS`` e reusa o resto sem tocar em nada;
* **fixtures da fatia salas** (1ª fatia) — ``predio_e2e``, ``sala_agendavel``,
  ``sala_sem_avaliador``, ``sala_restrita_ao_campus``, ``solicitacao_pendente``,
  ``reserva_deferida``, ``indisponibilizacao``, ``maquina_e2e`` e ``maquina_com_log``;
* **fixtures da fatia autenticação** (2ª fatia: senha, 2FA, dispositivos, sessões e conta) —
  ``pagina_anonima``, ``logado_efemero``, ``conta_pessoal``, ``conta_dois_fatores``,
  ``dispositivo_e2e`` e ``webmail_configurado``. Elas existem porque esta fatia mexe no que as
  outras assumem intacto: a senha, a sessão e o 2FA do usuário;
* **fixtures da fatia grupos** (3ª fatia: usuários em grupo, automatização e configuração) —
  ``grupo_gerenciado``, ``usuario_no_grupo``, ``grupo_automatizado``, ``automatizacao_existente``,
  ``preferencia_notificacao`` e ``predio_descartavel``. Esta fatia mexe no **substrato** de que as
  outras duas dependem (grupo é o que dá permissão), então nada aqui toca os papéis
  compartilhados: os fluxos que mutam usam dois grupos inertes do ``permissions.yaml`` do
  ``comum`` e um servidor descartável que nunca loga;
* **fixtures da fatia documentos** (4ª fatia: assinatura digital, autenticação de documento,
  solicitações de documento e telefones de setor) — ``certificado_digital``,
  ``registro_emissao_documento``, ``solicitacao_documento``, ``publico_e2e``,
  ``chaves_publicas_configuradas``, ``setor_descartavel`` e ``telefone_do_setor``. Duas escolhas
  governam a fatia: os artefatos de criptografia vêm dos arquivos **já versionados** em
  ``comum/tests/arquivos/assinatura-digital/`` (o mesmo ``.p12`` que ``comum.signer.test()`` usa),
  e o setor que os fluxos mutam é criado e apagado pelo teste — mexer num setor de ``PAPEIS``
  deixaria o ``Vinculo`` dos usuários compartilhados com instância velha.
* **fixtures da fatia página inicial** (5ª fatia: notificações, quadros/pendências, tema, menu,
  atalhos e comentários) — ``usuario_do_inicio``, ``notificar_o_inicio``,
  ``manutencao_programada``, ``atalho_do_inicio`` e ``objeto_comentavel``. Tudo o que esta fatia
  muda é **preferência gravada no usuário**, que o banco reusado carrega para a execução
  seguinte e que muda a aparência das telas de todas as outras fatias; por isso ela inteira roda
  sobre um papel descartável aberto por ``logado_efemero``, e repõe o estado no setup.
* **fixtures da fatia pessoas/prestadores** (6ª e última fatia: prestador de serviço, usuário
  externo, contatos de emergência, biometria, macro SIAPE, webservices do terminal de ponto,
  documentação e órgãos colegiados) — ``prestador_e2e``, ``ocupacao_ativa``, ``pensionista_e2e``,
  ``contatos_de_emergencia_limpos``, ``inscricao_fiscal_limpa``, ``solicitacao_biometria``,
  ``ano_corrente``, ``instituicao_configurada``, ``reuniao_colegiado``, ``ods_e2e``,
  ``terminal_sem_cache``, ``fotos_no_terminal`` e ``documentacao_gerada``. A regra
  desta fatia é a mais dura de todas: ``PessoaFisica`` e ``Vinculo`` são o substrato de **todo**
  o SUAP, então nenhum fluxo que mute pessoa toca um papel de ``PAPEIS`` — prestador e pensionista
  nascem e morrem no teste.

Decisões por módulo (receita, seção (c)):

1. **Seed**: por factories (#17486). ``e2e_seed`` (abaixo) chama ``semear_base()`` (catálogos,
   ``sync_permissions``, raiz e ``admin``) e monta a árvore que as telas usam — os campi ``CZN``,
   ``CEN`` e ``C0`` (com os setores folha ``C1``/``C2``), com as siglas do seed legado do behave —
   e os dois cadastros de apoio da ocupação de prestador. Os servidores são os de ``PAPEIS``
   (``servidores_comum``); o que falta para cada tela (prédio, sala, máquina) nasce por ORM.
2. **Papéis**: sim. As telas de reserva são governadas por permissão de model
   (``add_solicitacaoreservasala`` vem do grupo ``Servidor``;
   ``pode_avaliar_solicitacao_reserva_de_sala`` e as de indisponibilização, do grupo
   ``Avaliador de Sala``; ``view_predio``, do ``Coordenador da Sede``) e o seed base não põe
   ninguém nesses dois últimos grupos. A fixture é **eager e de sessão** porque o SUAP resolve
   permissão com cache por processo (armadilha 3 da receita).
3. **Relógio**: NÃO congela. O domínio de reserva é inteiramente relativo ao *agora* —
   ``SolicitacaoReservaSalaForm.clean`` recusa data/hora no passado, e
   ``pode_avaliar``/``pode_cancelar``/``pode_excluir`` comparam com ``datetime.now()``.
   Congelar brigaria com a própria validação que se quer exercitar; os testes deslocam as
   datas a partir de hoje.
4. **Encadeamento**: arquivos independentes, sem prefixo ``NN``. Nenhum teste depende do
   estado que outro produziu — cada um recebe uma **sala nova** (a suíte não dá flush e o CI
   roda com ``--reuse-db``: sala compartilhada acumularia reservas de execuções anteriores e
   ``Sala.tem_conflito_reserva`` passaria a reprovar solicitações válidas).

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5433 \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest comum/tests/e2e --reuse-db

``TEST_DATABASE_NAME`` com sufixo ``_e2e`` é obrigatório: ``settings_test`` usa ``test_suap``
por padrão e o guard ``_exige_banco_de_e2e`` falha alto sem o sufixo.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from pycpfcnpj import calculation

# Traz as fixtures de browser/banco (`logado`, `live_server`, `e2e_banco` e os overrides de
# `_django_db_helper`/`_exige_banco_de_e2e`). Precisa ser star-import em conftest: é a
# precedência de conftest sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import SENHA_E2E, campus, semear_base, servidor_com_login, setor

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import APIResponse, Page

    from rh.models import Servidor

# apelido -> (matrícula, grupo além do "Servidor" que todo servidor ganha no save, sigla do setor).
# O apelido é o que os testes escrevem (`logado_comum('avaliador_sala')`), para o papel — que é
# metade do que o teste afirma — não virar um número mágico.
#
# `admin` não está aqui de propósito: é o superusuário de `semear_base()`, e `logado_comum` o
# abre direto. As telas de `/comum/maquinas/` exigem `is_superuser`, não grupo.
PAPEIS: dict[str, tuple[str, str | None, str]] = {
    'avaliador_sala': ('9010001', 'Avaliador de Sala', 'CZN'),
    'solicitante': ('9010002', None, 'CZN'),
    'gestor_predios': ('9010003', 'Coordenador da Sede', 'CZN'),
    # Mesmo grupo do `avaliador_sala`, OUTRO campus e sem vínculo com a sala dos testes. É o
    # contraexemplo que separa "tem a permissão de model" de "é avaliador DESTA sala" — as duas
    # condições que `Sala.eh_avaliador` conjuga — e o servidor de fora que a restrição
    # `restringir_agendamentos_no_campus` tem de barrar.
    'avaliador_outro_campus': ('9010004', 'Avaliador de Sala', 'CEN'),
    # Contas DESCARTÁVEIS da fatia de autenticação (senha, sessão, 2FA). Os fluxos delas destroem
    # o estado do próprio usuário — trocam a senha, deslogam, habilitam 2FA —, então elas NÃO podem
    # ser abertas por `logado_comum`: aquele caminho passa por `storage_states`, que cacheia UM login
    # por matrícula para a sessão inteira, e derrubar essa sessão deslogaria todos os testes
    # seguintes do mesmo papel. Quem as abre é `logado_efemero`, que faz login próprio a cada teste;
    # o estado é reposto no SETUP (`conta_pessoal`/`conta_dois_fatores`), não no teardown, para a
    # suíte se curar sozinha depois de uma execução interrompida.
    'conta_pessoal': ('9010005', None, 'CZN'),
    'conta_dois_fatores': ('9010006', None, 'CZN'),
    # Contas da fatia de grupos/permissões (3ª fatia).
    #
    # `gestor_grupos` entra em `comum Administrador`, o grupo que `sync_permissions` cria por app
    # (`djtools/management/commands/sync_permissions.py:282-294`) junto de um `GerenciamentoGrupo`
    # com `eh_local=False` sobre TODOS os 20 grupos do `comum`. É de onde saem, sem inventar
    # substrato, as três autorizações que esta fatia exige: `GerenciamentoGrupo.user_can_manage`
    # (a guarda de `gerenciamento_grupo`), `User.eh_gerenciador_do_grupo` (adicionar/remover/
    # automatizar) e o `eh_local=False` que dispensa a checagem de campus em
    # `adicionar_usuario_grupo` e `remover_usuario_grupo`. O grupo não carrega permissão nenhuma —
    # `sync_manager_groups` só o cria —, então pôr alguém nele não muda tela de mais ninguém.
    'gestor_grupos': ('9010007', 'comum Administrador', 'CZN'),
    # O usuário DESCARTÁVEL que entra e sai de grupo. Nunca loga: `logado_comum` não o abre, e é
    # isso que torna seguro mexer nos grupos dele. Um papel compartilhado no lugar deste seria
    # duas armadilhas de uma vez — `atualizar_grupos_usuario` (`comum/models.py:1296`, no sinal de
    # login) poderia removê-lo de um grupo automatizado, e o cache de permissão por processo faria
    # o efeito depender da ordem dos testes.
    'alvo_grupo': ('9010008', None, 'CZN'),
    # Papel da fatia de documentos (4ª fatia). UM grupo cobre as três telas governadas por
    # permissão desta fatia, e é por isso que ele foi escolhido: `Coordenador de Gestão de Pessoas`
    # carrega `rh.pode_gerenciar_setor_telefone` (as três telas de telefone/e-mail de setor —
    # `rh/permissions.yaml:264`), `comum.change_documentocontrole` (atender e rejeitar solicitação
    # de documento) e `comum.change_prestadorservico` (a prévia de público-alvo). Criar três
    # papéis para isso custaria três servidores e nenhuma asserção a mais.
    'gestor_pessoal': ('9010009', 'Coordenador de Gestão de Pessoas', 'CZN'),
    # Papel DESCARTÁVEL da fatia da página inicial (5ª fatia). Sem grupo além de `Servidor`,
    # e de propósito: tudo o que esta fatia muda — tema, menu retraído, leiaute dos quadros,
    # atalho, preferência de envio, notificações — fica gravado NO USUÁRIO e o banco de e2e é
    # reusado, então mexer nisso com um papel compartilhado mudaria a aparência de TODAS as
    # telas das outras fatias (a barra lateral some, o tema troca, um atalho a mais aparece no
    # acesso rápido). Ninguém mais o abre, e `repor_inicio` o devolve ao zero no SETUP.
    'dono_do_inicio': ('9010010', None, 'CZN'),
    # Papel da fatia de pessoas/prestadores (6ª fatia). UM grupo cobre cinco telas, e é por isso
    # que ele foi escolhido em vez de três papéis: `Coordenador de Gestão de Pessoas Sistêmico`
    # carrega `rh.pode_gerenciar_extracao_siape` (as três telas de macro SIAPE —
    # `rh/permissions.yaml:361`), `comum.view_pensionista` (`comum/permissions.yaml:250`) e
    # `comum.change_prestadorservico` (prestador, ocupação, foto e papel de usuário externo).
    'gestor_pessoal_sistemico': ('9010011', 'Coordenador de Gestão de Pessoas Sistêmico', 'CZN'),
    # `ativar_usuario_externo`/`inativar_usuario_externo` são guardadas por `@group_required`, que
    # checa o NOME do grupo e não a permissão — nenhum papel já existente serve, por mais
    # permissões que tenha. O grupo vem de `rh/permissions.yaml:469` e não carrega permissão
    # nenhuma do `comum`, então pôr alguém nele não muda tela de mais ninguém.
    'gestor_ti': ('9010012', 'Coordenador de TI sistêmico', 'CZN'),
    # Assinatura digital (tarefa 20 da doc): `assinar_documento` e `verificar_documento` são
    # `@group_required('Reitor, Diretor Geral')` (f75876d8c8), grupo que nenhum outro papel tem. O
    # grupo só concede, no `comum`, o cadastro de certificado — que todo servidor já tem —, então
    # não muda tela de mais ninguém.
    'diretor_geral': ('9010013', 'Diretor Geral', 'CZN'),
}

# Campus e prédio em que a fatia inteira vive — o campus que a feature `003.comum.predio_salas`
# usava. Os formulários de sala oferecem campus por `UnidadeOrganizacional.objects.uo()`, que
# filtra por `tipo`: é `campus()` que garante o tipo (campus sem ele sumiria do `select` de
# `SalaIndicadoresForm`, `RelatorioSalasDisponiveisForm` e `RegistrarIndisponibilizacaoSalaForm`).
SIGLA_CAMPUS = 'CZN'
NOME_PREDIO = 'E2E Prédio Central'

# Cadastros de apoio da ocupação de prestador, gravados por `e2e_seed` com a chave natural do seed
# legado do behave (as duas suítes podem dividir o banco). Ficam nomeados aqui porque a fixture os
# busca no banco e o teste os digita no autocomplete: os dois precisam citar a MESMA coisa.
OCUPACAO_DO_SEED = 'Teste Ocupação'
EMPRESA_DO_SEED = 'Pessoa Jurídica'
CNPJ_DA_EMPRESA_DO_SEED = '45.006.424/0001-00'


# Rotas desta fatia que não viram teste. Cada motivo é uma condição verificável no código.
ROTAS_DISPENSADAS = {
    '/comum/sala/deferir_reserva_diario/<int:diario_pk>/<str:dh_inicio>/<str:dh_fim>/': (
        'exige um `edu.Diario` com `local_aula` preenchido, isto é, a cadeia acadêmica inteira '
        '(curso → matriz → componente curricular → calendário → horário de campus → turma → diário). '
        'A própria view busca o model por `apps.get_model("edu", "Diario")` justamente para o `comum` não importar o `edu`: '
        'montar esse grafo no seed do `comum` inverteria a dependência entre os apps e duplicaria `edu/tests/e2e/seed.py`. '
        'É tela do `edu` (o link sai do quadro de horários do diário) hospedada na `urls.py` do `comum`.'
    ),
    '/comum/gerar_cvs/<int:id_documentocontroletipo>/': (
        '**não é tela de browser, e não há por onde clicar**: a rota emite um CSV '
        '(`Content-Disposition: attachment`) e não tem entrada de UI — nenhum `comum/templates/**`, '
        '`comum/admin.py` ou `menu.yaml` a referencia. Um teste aqui seria um `goto` sintético numa URL '
        'que a interface não oferece. O CSV é exercitado ponta a ponta (view → ORM → response, com '
        'solicitação ativa de verdade) por `comum/tests/fluxos/test_fluxo_solicitacao_cracha.py`, que é '
        'onde ele pertence. '
        'Histórico: até o MR de fluxos esta rota era **morta** — `comum/views.py` lia '
        '`documentocontrole.vinculo_solicitante` (o campo chama-se `solicitante_vinculo`; '
        '`vinculo_solicitante` é do `almoxarifado`) e o `select_related` incluía '
        '`solicitante_vinculo__id_relacionamento`, que é `PositiveIntegerField`, não relação. '
        'Os dois defeitos foram corrigidos e a rota responde.'
    ),
    '/comum/sala/deferir_reserva_diario_no_periodo/<int:diario_pk>/': (
        'idem: mesmo `edu.Diario`, e o formulário ainda carrega os `edu.HorarioAulaDiario` do diário. '
        'Não vale o smoke com pk inexistente (o padrão de `almoxarifado/tests/e2e/test_rotas.py`): o corpo inteiro da view está '
        'num `try/except Exception` que engole o `Http404` e devolve 302, então o smoke exercitaria ~2 das 12 linhas, '
        'afirmaria o defeito em vez da tela e ainda marcaria a rota como coberta no gate.'
    ),
}


# ---------------------------------------------------------------------------------------
# Substrato reusável por qualquer fatia do `comum`
# ---------------------------------------------------------------------------------------


@pytest.fixture(scope='session')
def e2e_seed(e2e_banco) -> None:
    """Seed por factories (#17486): a base, a árvore do ``comum`` e os cadastros de apoio.

    Os servidores vêm em ``servidores_comum``. Tudo idempotente: a suíte não dá flush e o CI usa
    ``--reuse-db``. A árvore nasce aqui, antes da primeira request, porque ``rh.models.Setor``
    mantém um mapa de setores por processo que o ``live_server`` monta uma vez.
    """
    from comum.models import Ocupacao
    from rh.tests.factories import PessoaJuridicaFactory

    semear_base()
    campus(SIGLA_CAMPUS, 'Campus Zona Norte')
    campus('CEN', 'Campus Central')
    # `C1`/`C2`: setores folha SEM servidor, que a automatização de grupo usa (ver
    # `SIGLA_SETOR_SEM_SERVIDOR`).
    campus_c0 = campus('C0')
    setor(SIGLA_SETOR_SEM_SERVIDOR, campus_c0)
    setor('C2', campus_c0)
    # Mesma chave do seed legado (`codigo=''`): num banco com os dois seeds, o `get_or_create` de
    # lá reencontra esta linha em vez de criar outra "Teste Ocupação" (`.get` por descrição).
    Ocupacao.objects.get_or_create(codigo='', descricao=OCUPACAO_DO_SEED)
    PessoaJuridicaFactory(cnpj=CNPJ_DA_EMPRESA_DO_SEED, nome=EMPRESA_DO_SEED)


@pytest.fixture(scope='session')
def servidores_comum(e2e_seed) -> dict[str, Any]:
    """Cria TODOS os servidores de ``PAPEIS`` de uma vez, antes da primeira request.

    Eager de propósito (armadilha 3 da receita): o SUAP resolve permissão com cache por
    processo, então atribuir grupo no meio da sessão dá resultado dependente de ordem — uma
    tela que já respondeu 403 continua 403 depois de o usuário entrar no grupo.
    """
    return {apelido: _criar_servidor_com_grupo(apelido) for apelido in PAPEIS}


@pytest.fixture
def logado_comum(logado, servidores_comum) -> Callable[[str], Page]:
    """``(papel) -> Page`` autenticada. ``papel`` é um apelido de ``PAPEIS`` ou ``'admin'``."""

    def _logado_comum(papel: str) -> Page:
        if papel == 'admin':  # o superusuário de `semear_base()`
            return logado(papel)
        assert papel in servidores_comum, f'papel desconhecido: {papel!r}; declare em PAPEIS'
        return logado(PAPEIS[papel][0])

    return _logado_comum


def postar(pagina: Page, url: str) -> APIResponse:
    """POST pela sessão do browser, com o CSRF do cookie — para medir as rotas ``require_POST``.

    ``Tela.postar`` só serve a view ``@csrf_exempt``: sem token, a resposta seria a do CSRF e um
    teste de negação passaria sem nunca chegar à guarda da view. Aqui o token vai no header
    ``X-CSRFToken`` (mesmo idioma de ``centralservicos/tests/e2e/conftest.py``), e a asserção
    final garante que quem respondeu foi a view, não o middleware de CSRF (que devolve 403 com
    "CSRF" no corpo, ou o 302 do ``CSRF_FAILURE_VIEW`` do SUAP).
    """
    token = next((cookie['value'] for cookie in pagina.context.cookies() if cookie['name'] == settings.CSRF_COOKIE_NAME), None)
    assert token, 'a sessão do browser não tem cookie de CSRF'
    resposta = pagina.request.post(url, headers={'X-CSRFToken': token}, max_redirects=0)
    assert 'CSRF' not in resposta.text(), f'{url} foi barrada pelo CSRF, não pela view'
    return resposta


@pytest.fixture(scope='session')
def campus_e2e(e2e_seed):
    """A ``UnidadeOrganizacional`` SUAP do campus da fatia (ver ``SIGLA_CAMPUS``)."""
    from rh.models import UnidadeOrganizacional

    return UnidadeOrganizacional.objects.suap().get(sigla=SIGLA_CAMPUS)


# ---------------------------------------------------------------------------------------
# Fatia salas / prédio / agendamento
# ---------------------------------------------------------------------------------------


@pytest.fixture(scope='session')
def predio_e2e(campus_e2e):
    """Prédio do campus da fatia, criado uma vez por sessão.

    De sessão e não por teste porque prédio é cadastro **estável**: nada nos fluxos o consome
    nem o altera. Idempotente pelo ``unique_together ('nome', 'uo')``.
    """
    from comum.models import Predio

    return Predio.objects.get_or_create(nome=NOME_PREDIO, uo=campus_e2e, defaults={'ativo': True})[0]


@pytest.fixture
def sala_agendavel(predio_e2e, servidores_comum):
    """Sala NOVA a cada teste, agendável e avaliada por ``avaliador_sala``.

    Nova, e não compartilhada, por dois motivos que se somam: a suíte não dá flush e o CI roda
    com ``--reuse-db``, então uma sala fixa acumularia as reservas de toda execução anterior e
    ``Sala.tem_conflito_reserva`` passaria a reprovar solicitações perfeitamente válidas; e os
    fluxos desta fatia *consomem* o estado da sala (cancelam reservas, indisponibilizam o
    período), que é o caso clássico de "estado mutável nunca compartilhado" (armadilha 8).

    ``is_agendavel()`` exige as três coisas juntas — ativa, agendável e **ao menos um
    avaliador**; sem qualquer uma delas ``sala_solicitar_reserva`` devolve ``httprr`` de erro
    antes de mostrar o formulário.
    """
    from comum.models import Sala

    sala = Sala.objects.create(
        nome=f'E2E Sala {uuid.uuid4().hex[:8]}',
        predio=predio_e2e,
        ativa=True,
        agendavel=True,
        capacidade=30,
        informacoes_complementares='Sala com projetor e ar-condicionado.',
    )
    sala.avaliadores_de_agendamentos.add(servidores_comum['avaliador_sala'].get_user())

    yield sala

    # Apaga no fim do teste (em cascata: solicitações, reservas e indisponibilizações da sala).
    # Sem isto, cada teste deixa uma sala para trás **para sempre** — o banco de e2e é reusado — e
    # as telas que listam salas do campus (indicadores, salas disponíveis) passam a paginar: em
    # três execuções a sala do teste já caía na segunda página e a asserção falhava por lixo
    # acumulado, não por regressão. Medido.
    Sala.objects.filter(pk=sala.pk).delete()


@pytest.fixture
def sala_sem_avaliador(predio_e2e):
    """Sala agendável **sem avaliador** — o caso que ``Sala.is_agendavel()`` reprova (RN4).

    Existe separada de ``sala_agendavel`` porque a regra é a conjunção das três condições, e só
    dá para observar a terceira isolando-a.
    """
    from comum.models import Sala

    sala = Sala.objects.create(nome=f'E2E Sala sem avaliador {uuid.uuid4().hex[:8]}', predio=predio_e2e, ativa=True, agendavel=True)
    yield sala
    Sala.objects.filter(pk=sala.pk).delete()


@pytest.fixture
def sala_restrita_ao_campus(predio_e2e, servidores_comum):
    """Sala agendável **só por servidores do próprio campus**, avaliada por quem é de fora.

    Duas coisas de uma vez, de propósito: é a sala que exercita
    ``Sala.pode_agendar`` (a restrição de campus) e é o que dá a
    ``avaliador_outro_campus`` alguma sala avaliada — sem isso ele nem passa pela guarda
    ``Sala.eh_avaliador_salas`` do registro de indisponibilização, e a guarda seguinte, a que
    interessa, nunca roda.
    """
    from comum.models import Sala

    sala = Sala.objects.create(
        nome=f'E2E Sala restrita {uuid.uuid4().hex[:8]}',
        predio=predio_e2e,
        ativa=True,
        agendavel=True,
        restringir_agendamentos_no_campus=True,
    )
    sala.avaliadores_de_agendamentos.add(servidores_comum['avaliador_outro_campus'].get_user())
    yield sala
    Sala.objects.filter(pk=sala.pk).delete()


@pytest.fixture
def solicitacao_pendente(sala_agendavel, servidores_comum):
    """Solicitação aguardando avaliação, em data futura, do papel ``solicitante``.

    Criada por ORM (e não pela tela) porque os testes que a consomem exercitam o que vem
    *depois* dela — avaliar, cancelar, excluir. Quem cobre o cadastro pela interface é
    ``test_reserva_sala.test_ciclo_da_reserva_ate_a_ocorrencia``.

    Futura porque ``pode_avaliar``/``pode_cancelar`` exigem ``data_hora_fim >= now()``.
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
        justificativa='Reunião de equipe (fixture e2e).',
        recorrencia=SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO,
        status=SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO,
        avaliador=None,
        cancelada_por=None,
    )


@pytest.fixture
def reserva_deferida(solicitacao_pendente, servidores_comum):
    """``(solicitacao, reserva)`` já deferidas — o ponto de partida de cancelar/informar ocorrência.

    Defere por ORM e chama ``gerar_reservas()``: é o domínio que sabe transformar uma
    solicitação em reservas, e recorrência ``evento único`` produz exatamente uma.
    """
    from comum.models import SolicitacaoReservaSala

    solicitacao_pendente.status = SolicitacaoReservaSala.STATUS_DEFERIDA
    solicitacao_pendente.avaliador = servidores_comum['avaliador_sala'].get_user()
    solicitacao_pendente.data_avaliacao = datetime.now()
    solicitacao_pendente.save()
    solicitacao_pendente.gerar_reservas()
    return solicitacao_pendente, solicitacao_pendente.reservasala_set.get()


@pytest.fixture
def indisponibilizacao(sala_agendavel, servidores_comum):
    """Indisponibilização futura da sala do teste, registrada por ``avaliador_sala``.

    ``pode_excluir`` exige ``data_fim > now()``, então o período é sempre à frente.
    """
    from comum.models import IndisponibilizacaoSala

    dia = datetime.now() + timedelta(days=10)
    return IndisponibilizacaoSala.objects.create(
        sala=sala_agendavel,
        data_inicio=dia.replace(hour=8, minute=0, second=0, microsecond=0),
        data_fim=dia.replace(hour=18, minute=0, second=0, microsecond=0),
        usuario=servidores_comum['avaliador_sala'].get_user(),
        data=datetime.now(),
        justificativa='Manutenção elétrica programada (fixture e2e).',
        cancelada_por=None,
    )


@pytest.fixture
def maquina_com_log(campus_e2e):
    """Máquina que já reportou atividade — o outro quadro de ``/comum/maquinas/``.

    A tela separa as máquinas em "com registro de atividade" e "sem registro" por
    ``ultimo_log__isnull``; sem as duas, metade do relatório nunca é montada.
    """
    from ponto.models import Maquina

    return Maquina.objects.get_or_create(
        ip='127.0.0.2',
        defaults={'descricao': 'E2E Terminal com log', 'ativo': True, 'uo': campus_e2e, 'ultimo_log': datetime.now()},
    )[0]


@pytest.fixture
def maquina_e2e(campus_e2e):
    """Máquina ativa do campus da fatia para as telas de ``/comum/maquinas/``.

    O IP é ``127.0.0.1`` de propósito: ``maquinas_detalhes`` chama ``ping`` pelo shell contra o
    IP do registro, e endereço não roteável faria o teste esperar o timeout do ``ping``.
    Idempotente pelo ``unique`` do IP.
    """
    from ponto.models import Maquina

    return Maquina.objects.get_or_create(
        ip='127.0.0.1',
        defaults={'descricao': 'E2E Terminal CZN', 'ativo': True, 'uo': campus_e2e},
    )[0]


# ---------------------------------------------------------------------------------------
# Fatia autenticação / senha / 2FA / dispositivos e sessões
# ---------------------------------------------------------------------------------------
#
# A regra desta fatia é uma só: **sessão compartilhada não sobrevive a um teste de logout**.
# `logado_comum` entrega uma página autenticada por `storage_states`, que faz UM login real por
# matrícula e reusa o cookie na sessão inteira do pytest; trocar a senha, deslogar ou expirar a
# sessão daquele usuário envenena todos os testes seguintes que o usarem. Por isso os fluxos
# destrutivos usam `logado_efemero` (login próprio, descartado com o contexto) sobre as contas
# `conta_pessoal`/`conta_dois_fatores`, que ninguém mais abre.


# Senha que o fluxo de troca grava. A conta volta a `SENHA_E2E` no setup do próximo teste.
SENHA_TROCADA = 'SenhaValida1!'


@pytest.fixture
def pagina_anonima(new_context) -> Page:
    """Página SEM sessão — para as telas de quem ainda não entrou (a solicitação de troca de senha).

    Não dá para reusar `logado`: ele existe justamente para entregar contexto já autenticado.
    """
    pagina = new_context().new_page()
    pagina.on('dialog', lambda dialogo: dialogo.accept())
    return pagina


@pytest.fixture
def logado_efemero(new_context, login_ui) -> Callable[[str, str], Page]:
    """``(papel, senha) -> Page`` com sessão PRÓPRIA: login de verdade a cada teste.

    Diferença que justifica a fixture (e a razão de ela não envelopar `logado`): aqui **não** se
    passa por `storage_states`. A sessão nasce e morre com o teste, então o teste pode deslogar,
    expirar a sessão ou trocar a senha sem atingir mais ninguém. O preço é um login por teste,
    que o hasher MD5 de `suap/settings_test.py` torna barato.
    """

    def _logado_efemero(papel: str, senha: str = SENHA_E2E) -> Page:
        assert papel in PAPEIS, f'papel desconhecido: {papel!r}; declare em PAPEIS'
        pagina = new_context().new_page()
        pagina.on('dialog', lambda dialogo: dialogo.accept())
        return login_ui(pagina, PAPEIS[papel][0], senha)

    return _logado_efemero


def _repor_conta(servidor):
    """Devolve a conta ao estado inicial — senha, tentativas de login, 2FA e tokens de troca.

    No SETUP e não no teardown de propósito: a suíte não dá flush e o CI roda com ``--reuse-db``,
    então uma execução interrompida no meio de um fluxo destrutivo deixaria a conta com a senha
    trocada (ou com 2FA ativo) para sempre. Repondo na entrada, a suíte se cura sozinha na
    execução seguinte.

    Os `TrocarSenha` também somem aqui: os testes leem o token do banco, e uma execução anterior
    deixaria vários para a mesma matrícula.
    """
    from comum.models import AutenticacaoDoisFatores, TrocarSenha

    user = servidor.get_user()
    user.set_password(SENHA_E2E)
    user.login_attempts = 0
    user.save()
    AutenticacaoDoisFatores.objects.filter(usuario=user).delete()
    TrocarSenha.objects.filter(username=user.username).delete()
    return servidor


@pytest.fixture
def conta_pessoal(servidores_comum):
    """Servidor descartável dos fluxos de senha, logout e seleção de vínculo."""
    return _repor_conta(servidores_comum['conta_pessoal'])


@pytest.fixture
def conta_dois_fatores(servidores_comum):
    """Servidor descartável dos fluxos de autenticação em dois fatores.

    Separado de `conta_pessoal` para o ciclo do 2FA não disputar a mesma conta com a troca de
    senha — e porque um 2FA ativo sobrando mudaria o que o login exige do outro fluxo.
    """
    return _repor_conta(servidores_comum['conta_dois_fatores'])


@pytest.fixture
def dispositivo_e2e(servidores_comum):
    """``(device, session_info)`` SINTÉTICOS do papel ``solicitante``, apagados no fim do teste.

    O ``user_agent`` é único e impossível de colidir por construção: o `Device` real nasce no
    sinal ``user_logged_in`` (``comum/models.py``) com ``get_or_create(user, user_agent)``, e todo
    contexto do Playwright manda o MESMO user agent — sem o `uuid`, desativar "o dispositivo do
    teste" expiraria as `SessionInfo` da sessão que os outros testes reusam, junto com o arquivo
    de sessão no disco.

    A `SessionInfo` também é sintética: é ela que `remote_logout` expira, e o teste afirma o
    registro, nunca a contagem que a mensagem de sucesso traz (essa cresce com o banco reusado).
    """
    from comum.models import Device, SessionInfo

    device = Device.objects.create(
        user=servidores_comum['solicitante'].get_user(),
        user_agent=f'E2E {uuid.uuid4().hex}',
        friendly_name='Notebook do teste e2e',
    )
    sessao = SessionInfo.objects.create(session_id=uuid.uuid4().hex, device=device, ip_address='127.0.0.1')

    yield device, sessao

    # Em cascata: leva a `SessionInfo` junto. Sem isto, cada execução deixa um dispositivo a mais
    # nas listagens de `/admin/comum/device/` e `/admin/comum/sessioninfo/`.
    Device.objects.filter(pk=device.pk).delete()


@pytest.fixture
def webmail_configurado() -> str:
    """URL do webmail institucional na ``Configuracao`` — o destino que ``/comum/webmail/`` devolve.

    O seed não traz a chave, e sem ela a view redireciona para a string ``"None"``
    (``HttpResponseRedirect(None)``): não haveria fato positivo a afirmar. `Configuracao.save`
    já limpa o cache `_CONFIGURACAO_CACHED`, e o backend de cache dos testes é local ao processo —
    o `live_server` roda na mesma memória, então a gravação vale na request seguinte.
    """
    from comum.models import Configuracao

    url = 'https://webmail.ifrn.edu.br/'
    Configuracao.objects.update_or_create(app='comum', chave='url_webmail', defaults={'valor': url, 'descricao': 'URL do Webmail (fixture e2e)'})
    return url


# ---------------------------------------------------------------------------------------
# Fatia grupos / permissões / automatização / configuração
# ---------------------------------------------------------------------------------------
#
# A regra desta fatia: **nenhum fluxo que muta grupo toca papel compartilhado**. Grupo é o que
# dá permissão no SUAP, e as duas fatias anteriores dependem dos grupos de `PAPEIS` — tirar
# alguém de `Avaliador de Sala` no meio da sessão derrubaria a fatia 1 sem deixar rastro no
# teste que causou. Daí a escolha dos dois grupos abaixo: são do `permissions.yaml` do `comum`
# (condição para o filtro por módulo das telas de grupo enxergá-los), estão gerenciados por
# `comum Administrador`, e nascem com ZERO usuários no seed — ninguém depende deles.
#
# Grupo NOVO não serviria: `gerenciamento_grupo` lista o que está no YAML (`APP_GROUP_DICT`,
# `comum/views.py:1705`), que é cache de processo preenchido na primeira request e nunca
# invalidado — um grupo criado depois disso é invisível para o filtro.

# Entra e sai usuário por aqui (`adicionar_usuario_grupo` / `remover_usuario_grupo`).
GRUPO_GERENCIADO = 'Atualizador de Digital'
# Recebe a configuração de automatização em setores. Separado do anterior de propósito: uma
# `ConfiguracaoAutomatizacaoGrupo` ativa torna o campo `Prazo` OBRIGATÓRIO em
# `AdicionarUsuarioGrupoForm` (`comum/forms.py:1433`), e como o banco de e2e é reusado, a
# configuração de uma execução mudaria o formulário da outra.
GRUPO_AUTOMATIZADO = 'Cadastrador de Digital'

# Setor SUAP **sem servidor nenhum** (folha de C0, criada por `e2e_seed`). É o que mantém a
# automatização inócua: `servidores_elegiveis` devolve vazio, então nenhum servidor de verdade
# entra no grupo — nem agora, nem no login seguinte de quem quer que seja
# (`HistoricoUsuarioGrupo.atualizar_grupos_usuario` roda no sinal de login e adiciona ao grupo
# todo servidor do setor configurado).
SIGLA_SETOR_SEM_SERVIDOR = 'C1'


def _grupo_zerado(nome: str):
    """Devolve o grupo do YAML **sem usuários e sem automatização** — reposição no SETUP.

    No setup e não no teardown pelo mesmo motivo de ``_repor_conta``: a suíte não dá flush e o
    CI roda com ``--reuse-db``, então uma execução interrompida no meio de um fluxo deixaria o
    grupo povoado (ou automatizado) para sempre. Repondo na entrada, a suíte se cura sozinha.

    Zerar também é o que impede a listagem de paginar: ``gerenciamento_grupo`` mostra 32 cartões
    por página e o usuário do teste cairia na segunda a partir da 33ª execução.
    """
    from django.contrib.auth.models import Group

    from comum.models import ConfiguracaoAutomatizacaoGrupo, UsuarioGrupoSetor

    grupo = Group.objects.get(name=nome)
    UsuarioGrupoSetor.objects.filter(usuario_grupo__group=grupo).delete()
    grupo.user_set.clear()
    ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo=grupo).delete()
    return grupo


@pytest.fixture
def grupo_gerenciado(servidores_comum):
    """Grupo inerte e vazio para os fluxos de entrada/saída de usuário no grupo."""
    grupo = _grupo_zerado(GRUPO_GERENCIADO)
    yield grupo
    _grupo_zerado(GRUPO_GERENCIADO)


@pytest.fixture
def usuario_no_grupo(grupo_gerenciado, servidores_comum):
    """``UsuarioGrupo`` do papel ``alvo_grupo`` já dentro do grupo, criado por ORM.

    Por ORM e não pela tela para os testes de leitura (grupos do usuário, histórico, vínculo de
    setor) não dependerem da ordem em que o pytest coleta — o efeito colateral de um teste nunca
    é o setup de outro. Quem cobre a entrada pela interface é
    ``test_grupos.test_ciclo_do_usuario_no_grupo``.

    ``user.groups.add`` é o gesto certo (e não um ``UsuarioGrupo.objects.create``): é ele que
    dispara o ``m2m_changed`` de ``comum/utils.py:29``, que grava o ``HistoricoUsuarioGrupo`` e o
    ``LogEntry`` que a tela de histórico lê.
    """
    from comum.models import UsuarioGrupo

    user = servidores_comum['alvo_grupo'].get_user()
    user.groups.add(grupo_gerenciado)
    return UsuarioGrupo.objects.get(user=user, group=grupo_gerenciado)


@pytest.fixture
def grupo_automatizado(servidores_comum):
    """Grupo inerte com UM usuário descartável — o que dá à análise de impacto o que mostrar.

    O usuário dentro do grupo é o que faz a tela de confirmação exibir "será removido": com o
    grupo vazio e um setor sem servidores, as três listas da análise sairiam vazias e o passo de
    confirmação não afirmaria nada. Ele é descartável e nunca loga, então a remoção anunciada não
    alcança sessão nenhuma.
    """
    grupo = _grupo_zerado(GRUPO_AUTOMATIZADO)
    servidores_comum['alvo_grupo'].get_user().groups.add(grupo)
    yield grupo
    _grupo_zerado(GRUPO_AUTOMATIZADO)


@pytest.fixture
def automatizacao_existente(grupo_automatizado, servidores_comum):
    """``ConfiguracaoAutomatizacaoGrupo`` gravada por ORM — ponto de partida da tela de alteração."""
    from rh.models import Setor

    from comum.models import ConfiguracaoAutomatizacaoGrupo

    configuracao = ConfiguracaoAutomatizacaoGrupo.objects.create(
        grupo=grupo_automatizado,
        ativa=True,
        criado_por=servidores_comum['gestor_grupos'].get_user(),
    )
    configuracao.setores.add(Setor.objects.get(sigla=SIGLA_SETOR_SEM_SERVIDOR, codigo=None))
    return configuracao


@pytest.fixture
def preferencia_notificacao(servidores_comum):
    """``(categoria, preferencia)`` de notificação do papel ``solicitante``, apagadas no fim.

    Categoria própria (com ``uuid``) e não uma do seed: as telas de preferência listam o que é do
    **vínculo logado**, e a listagem do admin pagina — uma categoria fixa acumularia uma
    preferência por execução no banco reusado.

    ``forcar_habilitacao=False`` porque é exatamente esse o filtro das seis views de preferência
    (``PreferenciaNotificacao.objects.filter(pk__in=ids, categoria__forcar_habilitacao=False)``):
    com ele ligado, a ação roda e não faz nada.
    """
    from comum.models import CategoriaNotificacao, PreferenciaNotificacao

    categoria = CategoriaNotificacao.objects.create(assunto=f'E2E Notificação {uuid.uuid4().hex[:8]}', ativa=True, forcar_habilitacao=False)
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
def predio_descartavel(campus_e2e):
    """Prédio criado só para ser apagado pela tela de exclusão genérica.

    Separado de ``predio_e2e`` (que é de sessão e sustenta a fatia de salas) porque o teste o
    destrói. Sem sala nem obra: o que se afirma é a exclusão, não a cascata.
    """
    from comum.models import Predio

    predio = Predio.objects.create(nome=f'E2E Prédio Descartável {uuid.uuid4().hex[:8]}', uo=campus_e2e, ativo=True)
    yield predio
    Predio.objects.filter(pk=predio.pk).delete()


# ---------------------------------------------------------------------------------------
# Fatia documentos / assinatura digital / solicitações / telefones de setor
# ---------------------------------------------------------------------------------------
#
# Os três arquivos abaixo já estão versionados desde antes desta suíte: são os que
# `comum.signer.test()` usa para exercitar a assinatura no shell. Reusá-los evita gerar um par
# chave/certificado em tempo de teste — e garante que o PDF assinado foi assinado de verdade,
# por um certificado cuja senha está no próprio `comum/signer.py`.
#
# O certificado é AUTOASSINADO e expirou em 26/11/2024. Nada no caminho exercitado depende
# disso: `signer.sign` não olha a validade, `AssinarDocumentoForm.clean_senha` só abre o `.p12`,
# e `signer.verify` devolve os assinantes com base em hash+assinatura (`certok` é calculado e
# descartado — ver `comum/signer.py`). O campo `validade` do `CertificadoDigital` é metadado
# denormalizado e a fixture o grava no futuro, que é a única coisa que o formulário consulta.
ARQUIVO_P12 = 'comum/tests/arquivos/assinatura-digital/client-identity.p12'
SENHA_DO_CERTIFICADO = 'teste'
ARQUIVO_PDF_ASSINADO = 'comum/tests/arquivos/assinatura-digital/arquivo-assinado.pdf'
ARQUIVO_PDF = 'comum/tests/arquivos/assinatura-digital/arquivo.pdf'
# Nome comum do titular do certificado — é o que as telas de verificação imprimem.
ASSINANTE = 'Hugo Sena'


@pytest.fixture
def certificado_digital(campus_e2e):
    """``CertificadoDigital`` do superusuário, a partir do ``.p12`` versionado dos testes.

    ``campus_e2e`` não é usado no corpo: está aqui só para encadear o ``e2e_seed``, que é quem
    cria o superusuário que a linha abaixo busca. (``registro_emissao_documento``, logo adiante,
    não pede fixture nenhuma justamente porque não tem FK para nada do seed.)

    Do superusuário porque é ele que os testes de assinatura logam; ``AssinarDocumentoForm``
    filtra o campo ``certificado`` por ``user=request.user`` **e** ``validade__gte=hoje``, então
    um certificado de outro usuário simplesmente não aparece na lista e a tela fica sem opção.

    Apagado no fim: o arquivo vai para o ``default_storage`` e o cadastro aparece em
    ``/admin/comum/certificadodigital/`` — sem o teardown, o banco reusado acumularia um por
    execução.
    """
    from django.core.files.base import ContentFile

    from comum.models import CertificadoDigital, User

    with open(os.path.join(settings.BASE_DIR, ARQUIVO_P12), 'rb') as arquivo:
        conteudo = arquivo.read()

    certificado = CertificadoDigital(
        user=User.objects.get(username='admin'),
        nome=f'E2E Certificado {uuid.uuid4().hex[:8]}',
        organizacao='IFRN',
        unidade='COSINF',
        validade=(datetime.now() + timedelta(days=365)).date(),
        conteudo='',
    )
    certificado.arquivo.save(f'e2e-{uuid.uuid4().hex[:8]}.p12', ContentFile(conteudo), save=True)

    yield certificado

    certificado.arquivo.delete(save=False)
    CertificadoDigital.objects.filter(pk=certificado.pk).delete()


@pytest.fixture
def registro_emissao_documento():
    """``RegistroEmissaoDocumento`` com um PDF **assinado** — o alvo da autenticação pública.

    O arquivo é o PDF assinado e não um PDF qualquer porque ``autenticar_documento`` roda
    ``signer.verify`` sobre o documento do registro e só então mostra "assinado digitalmente
    por": com um PDF sem assinatura a tela autentica o registro e o ramo das assinaturas nunca
    executa.

    ``tipo`` e ``codigo_verificador`` levam ``uuid`` porque o formulário público monta a lista de
    tipos com ``values_list('tipo').distinct()`` sobre a tabela inteira, e o banco de e2e é
    reusado: tipo fixo faria a execução seguinte encontrar dois registros e o formulário passaria
    a exigir a "Informação Auxiliar" (``AutenticarDocumentoForm.clean_tipo_objeto``).
    """
    from django.core.files.base import ContentFile

    from comum.models import RegistroEmissaoDocumento

    with open(os.path.join(settings.BASE_DIR, ARQUIVO_PDF_ASSINADO), 'rb') as arquivo:
        conteudo = arquivo.read()

    registro = RegistroEmissaoDocumento(
        tipo=f'E2E Documento {uuid.uuid4().hex[:8]}',
        data_emissao=datetime.now().date(),
        codigo_verificador=uuid.uuid4().hex[:12].upper(),
    )
    registro.documento.save(f'e2e-{registro.codigo_verificador}.pdf', ContentFile(conteudo), save=True)

    yield registro

    # `RegistroEmissaoDocumento.delete` apaga o arquivo no storage junto com a linha.
    registro.delete()


@pytest.fixture
def solicitacao_documento(servidores_comum):
    """``(tipo, solicitação)`` NOVOS a cada teste, aguardando atendimento.

    **Nova a cada teste** porque atender e rejeitar CONSOMEM a solicitação:
    ``DocumentoControle.pode_atender_solicitacao`` exige ``status == NAO_ATENDIDA``, e uma
    solicitação compartilhada faria o segundo teste passar sem fazer nada (armadilha 8).

    **Por ``bulk_create`` e não por ``objects.create``**: ``DocumentoControle.save`` grava o
    histórico com ``self._salva_dados_historico(tl.get_request(), ...)``, e esse método faz
    ``request.user.get_vinculo()`` sem checar ``None``. Numa fixture não há request no
    threadlocal do djtools, então o ``create`` levanta
    ``AttributeError: 'NoneType' object has no attribute 'user'``. O ``bulk_create`` não passa
    pelo ``save()``; o histórico que ele gravaria é criado logo abaixo por ORM, porque é ele que a
    tela de acompanhamento lista.
    """
    from djtools.choices import SituacaoSolicitacaoDocumento

    from comum.models import DocumentoControle, DocumentoControleHistorico, DocumentoControleTipo
    from rh.models import Situacao

    tipo = DocumentoControleTipo.objects.create(descricao=f'E2E Documento {uuid.uuid4().hex[:8]}')
    tipo.abrangencia.add(Situacao.objects.get(codigo=Situacao.ATIVO_PERMANENTE))

    solicitante = servidores_comum['solicitante']
    solicitacao = DocumentoControle.objects.bulk_create(
        [
            DocumentoControle(
                documento_tipo=tipo,
                solicitante_vinculo=solicitante.get_vinculo(),
                justificativa='Primeira via do documento (fixture e2e).',
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

    # Em cascata: o histórico vai junto com a solicitação, e a solicitação com o tipo.
    DocumentoControleTipo.objects.filter(pk=tipo.pk).delete()


@pytest.fixture
def publico_e2e(servidores_comum):
    """``Publico`` que resolve para UM servidor — o alvo da prévia de público-alvo.

    O filtro é por matrícula de propósito. ``visualizar_publico`` pagina de 50 em 50, e um
    público sobre todos os servidores reduziria a asserção ao ``<h1>``: com um único resultado dá
    para afirmar que a consulta do público foi realmente executada (a view chama
    ``publico.get_queryset()`` dentro de um ``try`` que transforma qualquer erro em redirect).
    """
    from comum.models import Publico

    publico = Publico.objects.create(
        nome=f'E2E Público {uuid.uuid4().hex[:8]}',
        modelo_base=Publico.BASE_SERVIDOR,
        manager_base='objects',
        filtro='{{"matricula": "{}"}}'.format(PAPEIS['gestor_pessoal'][0]),
    )
    yield publico
    Publico.objects.filter(pk=publico.pk).delete()


@pytest.fixture
def chaves_publicas_configuradas() -> dict[str, str]:
    """As duas chaves públicas que o SUAP publica sem autenticação, gravadas na ``Configuracao``.

    O seed não traz nenhuma das duas, e sem elas os endpoints respondem 200 com corpo
    vazio (``/comum/get_chave_publica_suap/``) ou com ``{"keys": [{}]}`` (``/comum/jwk/``) — não
    haveria contrato a afirmar. ``Configuracao.save`` limpa o cache ``_CONFIGURACAO_CACHED`` e o
    backend de cache dos testes é local ao processo, que é o mesmo do ``live_server``.
    """
    from comum.models import Configuracao

    valores = {
        'chave_publica': 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC0e2e terminal-de-ponto@e2e',
        'chave_publica_jwk': '{"kty": "RSA", "use": "sig", "kid": "e2e", "alg": "RS256", "n": "e2e-modulo", "e": "AQAB"}',
    }
    for chave, valor in valores.items():
        Configuracao.objects.update_or_create(app='comum', chave=chave, defaults={'valor': valor, 'descricao': f'{chave} (fixture e2e)'})
    return valores


@pytest.fixture
def setor_descartavel(campus_e2e):
    """Setor SUAP criado e apagado pelo teste — o alvo dos fluxos de telefone e e-mail de setor.

    Descartável, e nunca um setor de ``PAPEIS``: os papéis compartilhados guardam o setor no
    ``Vinculo``, e ``User.VINCULOS`` é cache de processo — mexer no setor deles depois de os
    usuários existirem deixa o ``live_server`` com instância velha (achado das fatias anteriores).
    Também não serve um setor do seed: ``setor_editar_email`` GRAVA no setor, e o banco de e2e é
    reusado entre execuções.

    Criado por ``Setor.objects.create`` e apagado por ``instance.delete()`` (e não por
    ``queryset.delete()``): os dois invalidam o ``_SETOR_MAP``, o mapa em memória que
    ``rh.models.Setor`` mantém por processo — o caminho por queryset não passa pelo ``delete()``
    do model e deixaria o setor apagado vivo no cache do ``live_server``.
    """
    from rh.models import Setor

    setor = Setor.objects.create(
        sigla=f'E2E{uuid.uuid4().hex[:6].upper()}',
        nome=f'Setor de Teste E2E {uuid.uuid4().hex[:6]}',
        codigo=None,
        superior=Setor.objects.get(sigla=SIGLA_CAMPUS, codigo=None),
    )
    yield setor
    setor.delete()


@pytest.fixture
def telefone_do_setor(setor_descartavel):
    """Telefone já cadastrado no setor descartável — o ponto de partida da remoção.

    Por ORM e não pela tela para o teste de remoção não depender do de cadastro: o efeito colateral
    de um teste nunca é o setup de outro. Quem cobre o cadastro pela interface é
    ``test_telefones_setor.test_ciclo_do_telefone_do_setor``.
    """
    from comum.models import SetorTelefone

    return SetorTelefone.objects.create(setor=setor_descartavel, numero='(84) 4005-4002', ramal='4002', observacao='Sala dos testes e2e')


# ---------------------------------------------------------------------------------------
# Fatia página inicial / notificações / tema / menu / atalhos / comentários
# ---------------------------------------------------------------------------------------
#
# A regra desta fatia é uma só, e é o espelho da regra da fatia de autenticação:
# **preferência de usuário é estado pegajoso**. Tema, menu retraído, leiaute dos quadros,
# atalho e preferência de envio ficam gravados no usuário (ou na sessão dele) e o banco de e2e
# é reusado entre execuções — mexer nisso com um papel compartilhado trocaria o tema, sumiria
# com a barra lateral e acrescentaria um atalho no acesso rápido de TODAS as telas das outras
# quatro fatias, sem que nenhum teste delas apontasse a causa.
#
# Daí o desenho: um papel descartável (`dono_do_inicio`) que ninguém mais abre, sempre por
# `logado_efemero` — porque `logado_comum` passa por `storage_states`, que cacheia UMA sessão
# por matrícula, e o menu retraído mora justamente na sessão — e a reposição feita no SETUP
# (`usuario_do_inicio`), não no teardown, para a suíte se curar sozinha depois de uma execução
# interrompida.


def _repor_inicio(servidor):
    """Devolve a página inicial do papel ao zero — tema, quadros, atalhos e notificações.

    No SETUP e não no teardown, pelo mesmo motivo de ``_repor_conta`` e ``_grupo_zerado``: a
    suíte não dá flush e o CI roda com ``--reuse-db``, então uma execução interrompida no meio
    de um fluxo destrutivo deixaria o usuário com tema Dunas, menu retraído e um quadro
    escondido para sempre.

    A ``Preferencia`` é **reposta**, não apagada: ``temas.html`` marca como "Selecionado" todo
    tema quando o usuário não tem preferência nenhuma (``preferencia.tema == tema.slug or not
    preferencia``), e aí a asserção de que o tema Padrão é o selecionado passaria sem afirmar
    nada. Com a linha existente e ``tema=PADRAO``, exatamente um box vem marcado. Ela também
    precisa existir para a barra de ações de ``/admin/comum/preferencianotificacao/`` mostrar os
    botões de envio padrão (``PreferenciaNotificacaoAdmin.get_action_bar``).

    O ``Device`` some junto, e essa linha é a mais importante daqui. O SUAP notifica o usuário no
    PRIMEIRO login de cada dispositivo ("Alerta de dispositivo desconhecido", com bloqueio de
    leitura por três dias), e o ``Device`` sobrevive no banco reusado — de modo que esse alerta
    aparece na **primeira** execução depois de o papel nascer e nunca mais. É o pior formato de
    armadilha: verde em todo ``--reuse-db`` local e vermelho no ``--create-db`` do CI, que foi
    exatamente o que se mediu ao escrever esta fatia. Apagando o dispositivo no setup, todo login
    volta a ser o primeiro, o alerta é sempre criado e sempre removido pela limpeza de
    ``notificar_o_inicio`` — e a execução fria fica idêntica à quente. A cascata leva as
    ``SessionInfo`` do papel junto, o que é inócuo: ``logado_efemero`` abre sessão nova a cada
    teste e ninguém mais usa esta conta.
    """
    from comum.models import Atalho, Device, IndexLayout, NotificacaoSistema, Preferencia, RegistroNotificacao

    user = servidor.get_user()
    Preferencia.objects.update_or_create(usuario=user, defaults={'tema': Preferencia.PADRAO, 'via_suap': True, 'via_email': True})
    IndexLayout.objects.filter(usuario=user).delete()
    Atalho.objects.filter(usuario=user).delete()
    RegistroNotificacao.objects.filter(vinculo__user=user).delete()
    Device.objects.filter(user=user).delete()
    # Mensagem sem nenhum destinatário é lixo por construção: `send_notification` cria uma
    # `NotificacaoSistema` por envio e os `RegistroNotificacao` que apontam para ela acabaram de
    # ser apagados. Sem esta linha o alerta de login de cada teste deixaria uma órfã no banco
    # reusado — invisível em tela, mas somada no "Notificações" de `/admin/comum/categorianotificacao/`.
    NotificacaoSistema.objects.filter(registronotificacao__isnull=True).delete()
    return servidor


@pytest.fixture
def usuario_do_inicio(servidores_comum):
    """Servidor descartável dos fluxos que gravam preferência de usuário, reposto no setup."""
    return _repor_inicio(servidores_comum['dono_do_inicio'])


@pytest.fixture
def notificar_o_inicio(usuario_do_inicio):
    """``(assunto, mensagem, quantidade=1, dias_atras=0) -> [RegistroNotificacao]`` do papel.

    Usa ``djtools.utils.send_notification``, o caminho de produção, e **não** um
    ``RegistroNotificacao.objects.create`` cru. A diferença não é estética: é ele que cria a
    ``PreferenciaNotificacao`` do par (vínculo, categoria), e sem ela ``notificacao_ancora.html``
    chama ``RegistroNotificacao.get_preferencia_via_suap`` sobre um ``None`` — a ``AttributeError``
    escapa do template (o Django só engole ``TypeError`` ao chamar método de variável) e
    ``/comum/notificacoes/`` responde 500. Um ``create`` cru deixaria o teste afirmando uma
    caixa de notificações que o SUAP real nunca monta.

    ``objeto=None`` de propósito: com ``objeto_relacionado`` preenchido, a caixa agrupa as
    notificações do mesmo objeto (``outras_notificacoes_nao_lidas_mesmo_objeto``) e a
    deduplicação de ``_notificacoes_nao_lidas_deduplicadas`` mostra só a mais recente — o que
    esconderia as demais dos testes que contam itens.

    ``dias_atras`` é aplicado por ``queryset.update``: as três datas do registro são
    ``auto_now_add``, e o ``save()`` as reescreveria para agora.

    **Chame depois de logar.** O SUAP notifica o próprio usuário no PRIMEIRO login de cada
    dispositivo (``@receiver(user_logged_in)`` em ``comum/models.py``: "Alerta de dispositivo
    desconhecido"), e esse alerta nasce com ``data_permite_marcar_lida`` **três dias à frente**.
    Criado depois das notificações do teste, ele vira a mais recente da caixa — e, como
    ``pode_ler()`` é falso, ``/comum/notificacoes/`` deixava de marcar qualquer uma como lida
    (corrigido no #17388: a caixa pula a travada; o alerta continua sendo um item a mais). Medido: a suíte inteira passou em banco reusado e reprovou na primeira execução depois de o
    papel ser criado, que é exatamente o que o ``--create-db`` reproduz (armadilha 13 da receita).

    Daí as duas linhas de guarda abaixo: a primeira chamada exige que o login já tenha acontecido
    (o ``Device`` do usuário é a prova) e limpa a caixa, de modo que o que o teste criar seja tudo
    o que existe — independentemente de ser a primeira execução num banco novo ou a décima no
    reusado.
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
        categoria = f'E2E {assunto} {uuid.uuid4().hex[:8]}'
        categorias.append(categoria)
        for indice in range(quantidade):
            send_notification(
                categoria,
                f'{mensagem} (#{indice + 1})',
                configuracoes.DEFAULT_FROM_EMAIL,
                [vinculo],
                categoria=categoria,
                so_notificar=True,
            )
        registros = RegistroNotificacao.objects.filter(vinculo=vinculo, notificacao__categoria__assunto=categoria)
        if dias_atras:
            antiga = datetime.now() - timedelta(days=dias_atras)
            registros.update(data=antiga, data_permite_marcar_lida=antiga, data_permite_excluir=antiga)
        return list(registros.order_by('data'))

    yield _notificar

    # Tudo do vínculo, e não só o que o teste criou: é o mesmo raciocínio da reposição no setup —
    # um teste interrompido no meio não pode deixar notificação para a execução seguinte, que
    # contaria itens a mais na caixa e no contador do cabeçalho.
    RegistroNotificacao.objects.filter(vinculo=vinculo).delete()
    CategoriaNotificacao.objects.filter(assunto__in=categorias).delete()


@pytest.fixture
def manutencao_programada(usuario_do_inicio):
    """``ManutencaoProgramada`` em cartaz — o que enche o "Fique atento!" da página inicial.

    É o ÚNICO produtor de alerta que mora no próprio ``comum`` (``index_inscricoes``): sem ela,
    ``/comum/index/meus_alertas/`` responde 200 com corpo vazio e não há fato positivo a afirmar.

    Criada e apagada pelo teste, nunca deixada para trás: ``proximas_atualizacoes`` filtra por
    ``vinculos_publico`` vazio **ou** igual ao do usuário, então uma linha esquecida no banco
    reusado poria o alerta na página inicial de TODOS os papéis das outras fatias.

    ``usuario`` vai explícito porque o campo é ``CurrentUserField``: numa fixture não há request
    no threadlocal do djtools e o default cairia em ``AnonymousUser``/``None``.
    """
    from comum.models import ManutencaoProgramada

    agora = datetime.now()
    manutencao = ManutencaoProgramada.objects.create(
        usuario=usuario_do_inicio.get_user(),
        tipo=ManutencaoProgramada.MANUTENCAO,
        sistema_ou_servico=f'SUAP E2E {uuid.uuid4().hex[:6]}',
        data_hora_atualizacao=agora + timedelta(days=2),
        previsao_minutos_inatividade=30,
        data_hora_inicio_notificacao=agora - timedelta(days=1),
        motivo='Janela de manutenção do teste e2e.',
    )

    yield manutencao

    ManutencaoProgramada.objects.filter(pk=manutencao.pk).delete()


@pytest.fixture
def atalho_do_inicio(usuario_do_inicio):
    """Atalho já cadastrado — o que dá conteúdo ao quadro ``Atalhos`` da página inicial.

    Por ORM e não pela tela para os testes de leitura do quadro não dependerem da ordem de
    coleta: o efeito colateral de um teste nunca é o setup de outro. Quem cobre o cadastro pela
    interface é ``test_tema_menu_atalho.test_cadastra_atalho_pelo_popup``.

    Sem ele o quadro não tem itens e ``meu_quadro.html`` — que é todo um ``{% if quadro.items %}``
    — renderiza vazio: a rota responderia 200 sem nada a afirmar.
    """
    from comum.models import Atalho

    atalho = Atalho.objects.create(usuario=usuario_do_inicio.get_user(), nome=f'E2E Atalho {uuid.uuid4().hex[:6]}', url='/comum/minha_conta/')
    yield atalho
    Atalho.objects.filter(pk=atalho.pk).delete()


@pytest.fixture
def objeto_comentavel(predio_descartavel):
    """Objeto de model do próprio ``comum`` para a caixa de comentários genérica.

    Do ``comum`` de propósito: ``comentario_add`` resolve o par (app, model) por ``ContentType``
    e serve a qualquer model do SUAP — escolher um de outro app inverteria a dependência, como
    já se decidiu para os quadros e as pendências da página inicial.

    A limpeza é explícita porque ``Comentario`` se liga por ``GenericForeignKey``: apagar o
    prédio **não** apaga os comentários (não há cascata sem FK real), e o banco de e2e é
    reusado — a listagem de ``/admin/comum/comentario/`` acumularia um por execução.
    """
    from django.contrib.contenttypes.models import ContentType

    from comum.models import Comentario, Predio

    tipo = ContentType.objects.get_for_model(Predio)

    yield predio_descartavel

    Comentario.objects.filter(content_type=tipo, object_id=predio_descartavel.pk).delete()


# ---------------------------------------------------------------------------------------
# Fatia pessoas / prestadores / usuário externo / documentação / colegiados (6ª e última)
# ---------------------------------------------------------------------------------------
#
# A regra desta fatia: `PessoaFisica` e `Vinculo` são o substrato de TODO o SUAP — as outras
# cinco fatias, os 90 apps e o próprio login dependem deles. Por isso **nenhum** fluxo que mute
# pessoa toca um papel de `PAPEIS`: prestador, pensionista e a pessoa de CPF duplicado nascem e
# morrem dentro do teste, com identificadores derivados de `uuid4` (a suíte não dá flush e o CI
# roda com `--reuse-db`, então matrícula e CPF fixos colidiriam na segunda execução — as
# factories do `comum`/`rh` numeram por `factory.Sequence`, que reinicia a cada processo).


@pytest.fixture
def prestador_e2e(campus_e2e):
    """Prestador de serviço NOVO a cada teste, com vínculo e usuário próprios.

    Novo, e nunca um prestador compartilhado: os fluxos desta fatia **mudam** o
    prestador (ativam, inativam, vinculam ocupação, trocam a foto, criam o papel de usuário
    externo) e cada um deles grava em `PessoaFisica`, `Vinculo` e `rh.Papel`.

    A matrícula e o CPF saem de `uuid4`: `PrestadorServicoFactory` numera por
    `factory.Sequence`, que reinicia em cada processo do pytest — no banco reusado a segunda
    execução reencontraria o registro da primeira (`django_get_or_create` na matrícula) e o
    teste seguinte herdaria o estado que o anterior deixou.
    """
    from rh.models import Setor

    from comum.tests.factories import PrestadorServicoFactory

    from comum.models import PrestadorServico, Vinculo

    marca = uuid.uuid4().hex[:8]
    setor = Setor.objects.get(sigla=SIGLA_CAMPUS, codigo=None)
    prestador = PrestadorServicoFactory(
        matricula=_matricula_descartavel(marca),
        setor=setor,
        pessoa_fisica__nome=f'E2E Prestador {marca}',
        pessoa_fisica__cpf=_cpf_para(marca),
    )
    # `PrestadorServico.save()` ANULA o setor (medido: `setor_id` sai `None` do banco logo após o
    # `create`), pelo mesmo motivo de `Servidor.save()` — a equivalência SIAPE↔SUAP não está
    # montada no seed de e2e. A reposição é por queryset para não re-disparar o `save()`, e
    # alcança também o `Vinculo`: é dele que as telas tiram o campus do prestador.
    PrestadorServico.objects.filter(pk=prestador.pk).update(setor=setor)
    Vinculo.objects.filter(pk=prestador.get_vinculo().pk).update(setor=setor)
    prestador.refresh_from_db()

    yield prestador

    _apagar_prestador(prestador)


@pytest.fixture
def ocupacao_ativa(prestador_e2e):
    """Ocupação VIGENTE do prestador — o estado que ``encerrar_ocupacao_prestador`` consome.

    Vigente de verdade (``data_fim`` no futuro) porque a view recusa duas situações com mensagem
    de erro e redirect: ocupação já encerrada e ocupação que termina **hoje**. Sem isso o teste
    afirmaria o caminho do erro achando que afirmou o encerramento.

    A ocupação e a empresa são buscadas pela **chave natural** que ``e2e_seed`` grava
    (``OCUPACAO_DO_SEED``/``EMPRESA_DO_SEED``), e não por ``.first()``: ``Ocupacao`` não
    tem ``Meta.ordering``, então ``.first()`` é arbitrário — no dia em que o seed ganhar uma
    segunda linha, esta fixture e o autocomplete que o teste preenche podem discordar, e a falha
    pareceria um defeito do widget.

    Vai junto com o prestador no teardown (``on_delete=CASCADE``).
    """
    from rh.models import PessoaJuridica

    from comum.models import Ocupacao, OcupacaoPrestador

    return OcupacaoPrestador.objects.create(
        prestador=prestador_e2e,
        ocupacao=Ocupacao.objects.get(descricao=OCUPACAO_DO_SEED),
        empresa=PessoaJuridica.objects.get(nome=EMPRESA_DO_SEED),
        data_inicio=date.today() - timedelta(days=30),
        data_fim=date.today() + timedelta(days=180),
        setor_suap=prestador_e2e.setor,
    )


@pytest.fixture
def pensionista_e2e(prestador_e2e):
    """Pensionista NOVO a cada teste — ``Pensionista`` é um ``OneToOne`` com o prestador.

    A matrícula tem no máximo 8 caracteres (``comum/models.py:3667``) e é única; derivá-la de
    ``uuid4`` é o que permite a segunda execução no banco reusado.
    """
    from comum.models import Pensionista

    return Pensionista.objects.create(usuario_externo=prestador_e2e, matricula=uuid.uuid4().hex[:8])


@pytest.fixture
def contatos_de_emergencia_limpos(servidores_comum):
    """Zera os contatos de emergência de ``solicitante`` — NO SETUP, e de novo no teardown.

    No setup porque a suíte não dá flush: ``ContatoEmergenciaForm.clean`` recusa um telefone já
    cadastrado para a mesma pessoa, e uma execução interrompida no meio do fluxo deixaria o
    contato gravado para sempre — a execução seguinte falharia na validação, não na tela.
    """
    from comum.models import ContatoEmergencia

    dono = servidores_comum['solicitante']
    ContatoEmergencia.objects.filter(pessoa_fisica=dono.pessoa_fisica).delete()

    yield dono

    ContatoEmergencia.objects.filter(pessoa_fisica=dono.pessoa_fisica).delete()


@pytest.fixture
def inscricao_fiscal_limpa(servidores_comum):
    """Apaga a inscrição de fiscal de concurso do papel — NO SETUP.

    ``fiscal_concurso`` é de mão única: ``if InscricaoFiscal.objects.filter(servidor=servidor)``
    redireciona com "Sua inscrição já foi realizada." antes de mostrar o formulário. Sem esta
    limpeza a primeira execução passa e a **segunda** toma o desvio em silêncio.
    """
    from comum.models import InscricaoFiscal

    servidor = servidores_comum['solicitante']
    InscricaoFiscal.objects.filter(servidor=servidor).delete()

    yield servidor

    InscricaoFiscal.objects.filter(servidor=servidor).delete()


@pytest.fixture
def biometria_do_zero(servidores_comum):
    """Zera as solicitações de biometria do papel e configura a expiração — NO SETUP.

    A ``Configuracao`` é obrigatória e o seed não a traz:
    ``BiometriaSolicitacao.data_expiracao`` faz
    ``int(Configuracao.get_valor_por_chave('comum', 'biometria_expiracao'))``, e sem a chave
    ``expirado`` levanta ``TypeError`` — o reenvio devolveria 500 por falta de configuração, não
    por regressão.

    Zerar no setup é o que permite a segunda execução: ``solicitar_autocadastro`` grava uma
    solicitação nova a cada vez e a suíte não dá flush, então o teste que localiza "a solicitação
    do papel" encontraria as de execuções anteriores.
    """
    from rh.models import BiometriaSolicitacao

    from comum.models import Configuracao

    Configuracao.objects.update_or_create(
        app='comum', chave='biometria_expiracao', defaults={'valor': '7', 'descricao': 'Dias de validade do código de biometria (fixture e2e)'}
    )
    dono = servidores_comum['solicitante']
    BiometriaSolicitacao.objects.filter(pessoa_fisica=dono.pessoa_fisica).delete()

    yield dono

    BiometriaSolicitacao.objects.filter(pessoa_fisica=dono.pessoa_fisica).delete()


@pytest.fixture
def cronograma_da_folha(ano_corrente):
    """Um ``rh.CronogramaFolha`` do ano corrente — o evento que o calendário administrativo desenha.

    Sem ele o calendário renderiza doze meses vazios, e afirmar que a tela abriu não diria nada
    sobre o que ela serve para mostrar. O cronograma da folha é o evento mais barato de montar
    entre os que a view coleta (`comum/views.py:3845-3878`): uma linha, sem grafo atrás. Os
    outros dependem de ``ponto.Liberacao``, ``ferias.Ferias`` ou ``rh.ServidorAfastamento``, que
    exigem substrato de outros apps.

    Do ``rh`` e não do ``comum`` de propósito — é a própria view do ``comum`` que o importa, e a
    fixture só monta o que ela já consulta.
    """
    from rh.models import CronogramaFolha

    hoje = date.today()
    cronograma, _ = CronogramaFolha.objects.get_or_create(
        mes=hoje.month,
        ano=ano_corrente,
        defaults={
            'data_consulta_previa_folha': date(hoje.year, hoje.month, 10),
            'data_fechamento_processamento_folha': date(hoje.year, hoje.month, 15),
            'data_abertura_atualizacao_folha': date(hoje.year, hoje.month, 20),
            'data_abertura_proxima_folha': date(hoje.year, hoje.month, 25),
        },
    )

    yield cronograma

    CronogramaFolha.objects.filter(pk=cronograma.pk).delete()


@pytest.fixture
def ano_corrente():
    """O ``Ano`` do ano corrente, que o seed NÃO traz.

    ``calendario_administrativo`` faz ``Ano.objects.filter(ano=date.today().year).first()`` e
    usa ``ano.ano`` sem guarda — sem a linha, a tela é um 500 de ``AttributeError`` no ``None``.
    Idempotente pelo ``django_get_or_create`` da factory.
    """
    from comum.tests.factories import AnoFactory

    return AnoFactory()


@pytest.fixture
def instituicao_configurada():
    """UF e código da instituição na ``Configuracao`` — o que as macros SIAPE compilam.

    Sem as duas chaves, ``baixar_macro_siape`` devolve **200** com o corpo
    ``'Defina Uf e o código da instituição'``: um teste que só olhasse o status passaria sem
    nunca ter gerado macro nenhuma.
    """
    from comum.models import Configuracao

    valores = {'instituicao_estado': 'RN', 'instituicao_identificador': '26435'}
    for chave, valor in valores.items():
        Configuracao.objects.update_or_create(app='comum', chave=chave, defaults={'valor': valor, 'descricao': f'{chave} (fixture e2e)'})
    return valores


@pytest.fixture
def servidor_com_matricula_sipe(servidores_comum):
    """Dá ao papel da fatia uma ``matricula_sipe`` — o campo que a macro de histórico de PCA escreve.

    Os servidores de ``PAPEIS`` nascem sem ela, e ``MacroHistoricoPCAForm`` filtra por
    ``matricula_sipe__isnull=False``. Sem um valor de verdade, a macro
    gerada sai com a matrícula em branco e a asserção não distinguiria "gerou" de "gerou vazio".

    Por ``queryset.update`` e não por ``save()``: ``Servidor.save`` refaz grupos, vínculo e setor,
    e mexer nisso com um papel compartilhado é a armadilha do cache de ``User.VINCULOS``.
    """
    from rh.models import Servidor

    servidor = servidores_comum['gestor_pessoal_sistemico']
    matricula_sipe = f'9{servidor.matricula}'
    Servidor.objects.filter(pk=servidor.pk).update(matricula_sipe=matricula_sipe)
    servidor.refresh_from_db()
    return servidor, matricula_sipe


@pytest.fixture
def reuniao_colegiado():
    """Reunião de órgão colegiado NA JANELA de hoje, para o calendário ter o que desenhar.

    ``ReuniaoOrgaoColegiado.query`` devolve ``none()`` quando o formulário não traz as duas
    datas, então o calendário do mês corrente só mostra algo se a reunião cair nele — uma reunião
    fora da janela faria o teste afirmar um calendário vazio.
    """
    from comum.models import ReuniaoOrgaoColegiado

    reuniao = ReuniaoOrgaoColegiado.objects.create(
        titulo=f'E2E Reunião Ordinária {uuid.uuid4().hex[:6]}',
        colegiado=ReuniaoOrgaoColegiado.ORGAO_CONSUP,
        descricao='Pauta de teste da suíte e2e.',
        local='Auditório da Reitoria',
        data_inicio=date.today(),
        data_fim=date.today(),
        hora_inicio=time(9, 0),
        hora_fim=time(12, 0),
    )

    yield reuniao

    ReuniaoOrgaoColegiado.objects.filter(pk=reuniao.pk).delete()


@pytest.fixture
def ods_e2e():
    """DOIS objetivos da ONU, com um subobjetivo cada — porque o que se testa é o **filtro**.

    O endpoint filtra por ``objetivo__in``, e com um objetivo só a resposta filtrada e a não
    filtrada seriam idênticas: o teste passaria mesmo se o filtro tivesse sido removido. O
    segundo objetivo é o contraexemplo — o subobjetivo que NÃO pode voltar.

    Devolve ``(escolhido, ignorado)``, cada um um par ``(objetivo, subobjetivo)``.
    """
    from comum.models import ObjetivoDesenvolvimentoSustentavel, SubobjetivoDesenvolvimentoSustentavel

    marca = uuid.uuid4().hex[:6]
    pares = []
    for indice, descricao in enumerate(('E2E Educação de Qualidade', 'E2E Saúde e Bem-Estar'), start=1):
        objetivo = ObjetivoDesenvolvimentoSustentavel.objects.create(descricao=f'{descricao} {marca}')
        subobjetivo = SubobjetivoDesenvolvimentoSustentavel.objects.create(
            descricao=f'{descricao} — meta {indice} {marca}', numero=f'E2E-{marca}-{indice}', objetivo=objetivo
        )
        pares.append((objetivo, subobjetivo))

    yield pares[0], pares[1]

    ObjetivoDesenvolvimentoSustentavel.objects.filter(pk__in=[objetivo.pk for objetivo, _ in pares]).delete()


@pytest.fixture
def terminal_sem_cache():
    """Apaga o dump do terminal de ponto já gerado — força o caminho completo da view.

    ``get_dump_pessoas`` reusa o ``.zip`` de ``settings.TEMP_DIR`` enquanto o ``mtime`` for de
    hoje. Sem esta limpeza, a segunda execução do dia devolveria o arquivo da primeira e o teste
    marcaria a rota como exercitada tendo rodado 4 das ~40 linhas da view — inclusive depois de
    um ``--create-db``, porque o arquivo vive no disco e não no banco.
    """
    import glob

    padrao = os.path.join(settings.TEMP_DIR, 'tabela_terminal_vinculos-*.zip')
    for arquivo in glob.glob(padrao):
        os.remove(arquivo)

    yield

    for arquivo in glob.glob(padrao):
        os.remove(arquivo)


@pytest.fixture
def fotos_no_terminal(maquina_e2e, campus_e2e):
    """Os dois ``.zip`` de fotos que o terminal baixa, no storage temporário, e o refeitório ligado.

    Os arquivos são gerados fora do SUAP pelos comandos ``fotos_funcionarios``/``fotos_alunos``;
    sem eles as duas views levantam ``Http404`` antes de qualquer linha útil. O conteúdo não é
    lido por ninguém — o que as views fazem é servir os bytes —, então um zip mínimo basta e é o
    que mantém o teste honesto sobre o que ele afirma (o contrato da resposta).

    ``cliente_refeitorio`` é ligado aqui e desligado no teardown: ``get_fotos_alunos`` exige a
    flag e o ``ip`` da máquina é ``unique``, então não dá para ter duas. O valor é REPOSTO no
    setup (``update``, não ``get_or_create``) para uma execução interrompida não deixar a flag
    ligada para as telas de ``/comum/maquinas/`` das outras fatias.
    """
    import io
    import zipfile

    from ponto.models import Maquina

    from djtools.storages.utils import get_temp_storage

    Maquina.objects.filter(pk=maquina_e2e.pk).update(cliente_refeitorio=True, uo=campus_e2e)
    maquina_e2e.refresh_from_db()

    storage = get_temp_storage()
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, 'w') as pacote:
        pacote.writestr('e2e.txt', 'fotos de teste')
    caminhos = ['fotos/fotos_funcionarios.zip', f'fotos/fotos_alunos_{campus_e2e.sigla}.zip']
    for caminho in caminhos:
        if storage.exists(caminho):
            storage.delete(caminho)
        storage.save(caminho, ContentFile(conteudo.getvalue()))

    yield maquina_e2e

    for caminho in caminhos:
        if storage.exists(caminho):
            storage.delete(caminho)
    Maquina.objects.filter(pk=maquina_e2e.pk).update(cliente_refeitorio=False)


@pytest.fixture
def documentacao_gerada(settings, tmp_path):
    """Os artefatos que ``test_behave --behave_auto_doc`` deixa em ``BEHAVE_AUTO_DOC_PATH``.

    As seis telas de ``/comum/documentacao/`` leem JSON do disco e **não** falham quando ele não
    está lá: respondem ``httprr('/', 'A documentação ainda não foi gerada.', 'error')`` ou
    ``HttpResponseBadRequest``. Quer dizer: sem os artefatos, um teste de status passaria sem
    nunca ter renderizado documentação nenhuma.

    A forma do JSON é copiada de quem o escreve — ``Documentacao.toJSON``
    (``djtools/new_tests/base_test.py:90-134``) para o arquivo por aplicação e
    ``BehavePdfDocumentationService.build_index`` (``djtools/new_tests/pdf_documentation.py:20``)
    para o índice. É justamente esse par gerador↔leitor que o teste protege.

    A aplicação documentada é o ``arquivo``, e não o ``comum``, por duas exigências que só ele
    satisfaz juntas: ``about_view`` faz ``apps.get_app_config(aplicacao)``, então a chave tem de
    ser um app label de verdade; e ``documentacao_bpmn_view`` abre
    ``<aplicacao>/workflows/<bpmn>`` **relativo ao diretório de execução**, isto é, um arquivo
    versionado no repositório — ``arquivo/workflows/diagram.bpmn`` existe, ``comum/workflows/``
    não. Assim o fluxograma que a tela do módulo publica é o mesmo que a rota de BPMN entrega.

    O diretório é o ``tmp_path`` do pytest, e não o ``deploy/media/documentacao`` real, para o
    teste não depender de (nem sujar) a árvore do projeto. Devolve o dicionário da aplicação.
    """
    aplicacao = {
        'sigla': APLICACAO_DOCUMENTADA,
        'nome': 'Arquivo Institucional',
        'area': 'Administração',
        'funcionalidades': [
            {
                'chave': 'gestao-de-arquivo',
                'nome': 'Gestão de Arquivo',
                'descricao': ['Mantém o arquivo documental da instituição.'],
                'app_name': APLICACAO_DOCUMENTADA,
                'cenarios': [
                    {
                        'chave': 'arquivar-documento',
                        'nome': 'Arquivar Documento',
                        'descricao': ['O operador arquiva um documento recebido.'],
                        'passos': [{'nome': 'Acesso a página de arquivamento', 'imagem': IMAGEM_DOCUMENTADA, 'descricao': ''}],
                    }
                ],
            }
        ],
        'workflows': {'Gestão de Arquivo': BPMN_DOCUMENTADO},
    }
    raiz = tmp_path / 'documentacao'
    (raiz / APLICACAO_DOCUMENTADA).mkdir(parents=True)
    (raiz / 'documentacao.json').write_text(
        json.dumps({'aplicacoes': [APLICACAO_DOCUMENTADA], 'data_atualizacao': date.today().strftime('%d/%m/%Y')})
    )
    (raiz / APLICACAO_DOCUMENTADA / 'documentacao.json').write_text(json.dumps({'aplicacoes': {APLICACAO_DOCUMENTADA: aplicacao}}))
    # PNG 1x1 válido: `documentacao_imagem_view` devolve os bytes crus com `content_type=image/png`.
    (raiz / APLICACAO_DOCUMENTADA / IMAGEM_DOCUMENTADA).write_bytes(base64.b64decode(_PNG_1X1_BASE64))

    settings.BEHAVE_AUTO_DOC_PATH = str(raiz)
    return aplicacao


# A aplicação, a imagem e o BPMN que `documentacao_gerada` publica. Ficam aqui, e não no arquivo
# de teste, porque é a fixture que os grava no disco e o teste que os cita na URL.
APLICACAO_DOCUMENTADA = 'arquivo'
IMAGEM_DOCUMENTADA = 'passo-1.png'
BPMN_DOCUMENTADO = 'diagram.bpmn'


# PNG 1x1 transparente (o menor PNG válido) — evita versionar binário só para uma asserção.
_PNG_1X1_BASE64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='


def _matricula_descartavel(marca: str) -> str:
    """Matrícula de 11 dígitos derivada de ``marca`` — estável dentro do teste, única entre eles."""
    return f'{int(marca, 16) % 10**11:011d}'


def _apagar_prestador(prestador) -> None:
    """Apaga prestador, vínculo, usuário, papéis e pessoa física — nesta ordem.

    Explícito porque não há cascata que alcance os quatro: ``Vinculo`` aponta para o ``User`` e
    para a ``Pessoa``, e ``rh.Papel`` aponta para o ``Vinculo``. Deixar qualquer um para trás faz
    a listagem de ``/admin/comum/prestadorservico/`` crescer uma linha por execução — e o banco
    de e2e é reusado.
    """
    from comum.models import PrestadorServico, Vinculo
    from rh.models import Papel, PessoaFisica

    vinculo = prestador.get_vinculo()
    pessoa_fisica_pk = prestador.pessoa_fisica_id
    user = vinculo.user if vinculo else None
    if vinculo:
        Papel.objects.filter(vinculo=vinculo).delete()
        Vinculo.objects.filter(pk=vinculo.pk).delete()
    PrestadorServico.objects.filter(pk=prestador.pk).delete()
    PessoaFisica.objects.filter(pk=pessoa_fisica_pk).delete()
    if user:
        user.delete()


# ---------------------------------------------------------------------------------------
# Criação dos servidores
# ---------------------------------------------------------------------------------------


def _criar_servidor_com_grupo(apelido: str) -> Servidor:
    """Cria (ou reencontra) o servidor de um papel e o põe no grupo declarado em ``PAPEIS``.

    ``Servidor.save()`` já adiciona o grupo ``Servidor`` (``comum/models.py:1246``), que é
    quem carrega ``add_solicitacaoreservasala`` — o grupo de ``PAPEIS`` é o que vem *além*
    disso. ``staff`` porque ``SolicitacaoReservaSalaForm`` filtra o campo ``solicitante`` por
    ``is_staff=True``, e o admin do SUAP (as listagens de solicitação e reserva) também o exige.

    Sem ``setor_lotacao``/``setor_exercicio`` SIAPE de propósito: com eles o ``save`` compara o
    campus SIAPE com o SUAP e anula o ``setor`` (servidor sem setor é deslogado pelo middleware).
    """
    from rh.models import Setor

    matricula, nome_grupo, sigla_setor = PAPEIS[apelido]
    servidor = servidor_com_login(
        matricula,
        Setor.objects.get(sigla=sigla_setor, codigo=None),
        grupos=[nome_grupo] if nome_grupo else (),
        staff=True,
        pessoa_fisica__nome=f'E2E {apelido.replace("_", " ").title()}',
        pessoa_fisica__cpf=_cpf_para(matricula),
        # A troca de senha e o autosserviço mandam o token/código para o e-mail pessoal do
        # vínculo (`Vinculo.email_notificacao`).
        email_pessoal=f'{matricula}_secundario@gmail.com',
    )
    return servidor


def _cpf_para(matricula: str) -> str:
    """CPF válido e **estável** por matrícula (o cadastro valida os dígitos verificadores).

    Deriva de md5 e não de ``hash()`` porque o hash de str do Python é randomizado por
    processo (``PYTHONHASHSEED``): um CPF diferente a cada sessão deixaria a pessoa física de um
    papel com CPF diferente a cada execução no banco reusado.
    """
    digest = hashlib.md5(matricula.encode(), usedforsecurity=False).hexdigest()
    base = f'{int(digest, 16) % 10**9:09d}'
    primeiro = calculation.calculate_first_digit(base)
    segundo = calculation.calculate_second_digit(base + primeiro)
    return f'{base[:3]}.{base[3:6]}.{base[6:9]}-{primeiro}{segundo}'
