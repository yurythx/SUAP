"""Infraestrutura dos e2e do módulo Documento Eletrônico.

O módulo não tem mais ``features/``: o behave dele foi removido depois de a paridade fechar em
zero órfãos e a suíte rodar verde. A unidade de cobertura passou a ser a **rota** — o gate é
``bin/scripts/paridade_e2e.py documento_eletronico --rotas`` — e a rastreabilidade de cada arquivo
é a sua docstring de módulo. O seed reproduz os usuários do antigo ``features/steps/given.py``
antes do primeiro acesso HTTP; o documento ``MEMO 1/2020`` é pré-requisito dos fluxos de
assinatura e vínculo.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import TYPE_CHECKING

import pytest
from freezegun import freeze_time

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores, semear_base, setor

if TYPE_CHECKING:
    from documento_eletronico.models import ConfiguracaoVinculoDocumento

DATA_BASE = '08/01/2020'

PAPEIS = {
    'reitor': '000001',
    'gerente': '200001',
    'chefe': '200002',
    'operador': '200003',
    'leitor': '200004',
}

# Matrícula -> (nome, grupos), do antigo `features/steps/given.py`. O setor de cada um está em
# `documento_seed`: o reitor na raiz, o gerente no campus CEN, os demais em DIDE/CEN.
SERVIDORES = {
    PAPEIS['reitor']: ('Reitor', ['Gerente Sistêmico de Documento Eletrônico', 'Servidor']),
    PAPEIS['gerente']: ('Servidor Documento Gerente Sistêmico', ['Gerente Sistêmico de Documento Eletrônico', 'Servidor']),
    PAPEIS['chefe']: ('Servidor Documento Chefe Setor', ['Chefe de Setor', 'Servidor']),
    PAPEIS['operador']: ('Servidor Documento Operador', ['Operador de Documento Eletrônico']),
    PAPEIS['leitor']: ('Servidor Documento Leitor', ['Servidor']),
}

ROTAS_DISPENSADAS = {
    '/documento_eletronico/meus_documentos/': 'view atual usa RegistroAcaoDocumento.objects, mas o modelo não expõe esse manager; retorna 500.',
    '/documento_eletronico/gerar_sugestao_identificador_documento_texto/<int:tipo_documento_id>/<int:setor_dono_id>/': (
        'view atual chama o gerador sem o parâmetro pessoal; rota retorna 500 antes de qualquer interação UI.'
    ),
    '/documento_eletronico/assinar_documento_com_gov_br/<int:documento_id>/': (
        'integração Gov.br protegida por token externo; o ambiente e2e não possui autenticação Gov.br.'
    ),
    '/documento_eletronico/enviar_codigo_verificacao_govbr': (
        'integração Gov.br protegida por token externo; o ambiente e2e não possui autenticação Gov.br.'
    ),
}


class _Relogio:
    def __init__(self) -> None:
        self._congelador = None

    def congelar(self, data_br: str) -> None:
        self.descongelar()
        dia, mes, ano = (int(parte) for parte in data_br.split('/'))
        self._congelador = freeze_time(datetime(ano, mes, dia, 12, 0))
        self._congelador.start()

    def descongelar(self) -> None:
        if self._congelador:
            self._congelador.stop()
            self._congelador = None


@pytest.fixture(scope='session')
def relogio() -> Iterator[_Relogio]:
    """Aquece a URLconf antes de congelar a data que o behave usava nos cenários (08/01/2020)."""
    from django.urls import get_resolver

    _ = get_resolver().url_patterns
    relogio_documento = _Relogio()
    yield relogio_documento
    relogio_documento.descongelar()


@pytest.fixture(autouse=True)
def data_do_documento(relogio: _Relogio) -> Iterator[None]:
    """Isola o relógio por teste e reproduz ``Quando a data ... 08/01/2020``."""
    relogio.congelar(DATA_BASE)
    yield
    relogio.descongelar()


@pytest.fixture(scope='session')
def documento_seed(e2e_seed, relogio: _Relogio) -> None:
    """Reproduz o setup que o behave fazia e prepara o memorando usado como alvo.

    Árvore RAIZ → CEN → DIDE/CEN (o identificador do memorando, ``DIDE/CEN/RAIZ``, sai dela),
    os servidores de ``SERVIDORES`` e as chefias. Funções e o documento-alvo são os únicos dados
    específicos do módulo que os cenários pressupunham.
    """
    from documento_eletronico.models import DocumentoTexto, ModeloDocumento, TipoDocumentoTexto
    from documento_eletronico.status import DocumentoStatus
    from rh.models import Atividade, Funcao, Servidor, ServidorFuncaoHistorico
    from rh.tests.factories import FuncaoFactory

    setor_raiz = semear_base()
    setor_cen = campus('CEN', 'Campus Central')
    setor_dide = setor('DIDE/CEN', setor_cen)
    setor('DIAC/CEN', setor_cen)  # só alvo do compartilhamento por setor (`test_02_documento`)
    por_setor = {PAPEIS['reitor']: setor_raiz, PAPEIS['gerente']: setor_cen}
    for matricula, dados in SERVIDORES.items():
        criar_servidores(por_setor.get(matricula, setor_dide), {matricula: dados})

    atividade_reitor = Atividade.objects.get_or_create(codigo=Atividade.REITOR, defaults={'nome': 'Reitor'})[0]
    funcao_chefe = FuncaoFactory(codigo=Funcao.CODIGO_FG, nome='Chefe de Setor')
    funcao_reitor = FuncaoFactory(codigo=Funcao.CODIGO_CD, nome='Reitor')

    for matricula, setor_chefia, funcao in (
        ('200001', setor_cen, funcao_chefe),
        ('200002', setor_dide, funcao_chefe),
    ):
        ServidorFuncaoHistorico.objects.get_or_create(
            servidor=Servidor.objects.get(matricula=matricula),
            data_inicio_funcao=date(2010, 3, 10),
            funcao=funcao,
            setor=setor_chefia,
            setor_suap=setor_chefia,
        )

    ServidorFuncaoHistorico.objects.get_or_create(
        atividade=atividade_reitor,
        setor=setor_raiz,
        setor_suap=setor_raiz,
        data_inicio_funcao=date(2010, 3, 10),
        servidor=Servidor.objects.get(matricula=PAPEIS['reitor']),
        funcao=funcao_reitor,
    )

    for tipo_documento in TipoDocumentoTexto.objects.all():
        tipo_documento.save()

    tipo = TipoDocumentoTexto.objects.get(sigla='MEMO')
    modelo = ModeloDocumento.objects.get(nome='Interrupção de Férias')
    chefe = Servidor.objects.get(matricula=PAPEIS['chefe']).get_user()
    DocumentoTexto.objects.filter(assunto__startswith='E2E Documento ').delete()
    DocumentoTexto.objects.filter(assunto__startswith='Clone E2E ').delete()
    DocumentoTexto.objects.filter(
        modelo__tipo_documento_texto=tipo,
        setor_dono=setor_dide,
        identificador_ano=datetime.now().year,
        usuario_criacao=chefe,
    ).delete()
    memo = DocumentoTexto.objects.filter(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ').first()
    if memo is None:
        memo = DocumentoTexto(
            assunto='Memorando pré-existente dos cenários',
            nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO,
            setor_dono=setor_dide,
            modelo=modelo,
            corpo='<p>Documento pré-existente para o fluxo de assinatura.</p>',
            cabecalho='',
            rodape='',
            variaveis='{}',
            usuario_criacao=chefe,
            usuario_ultima_modificacao=chefe,
            data_ultima_modificacao=datetime.now(),
            status=DocumentoStatus.STATUS_CONCLUIDO,
            identificador_tipo_documento_sigla=tipo.sigla,
            identificador_numero=1,
            identificador_ano=2020,
            identificador_setor_sigla='DIDE/CEN/RAIZ',
        )
        memo.save()
    else:
        memo.solicitacaoassinatura_set.all().delete()
        memo.assinaturadocumentotexto_set.all().delete()
    DocumentoTexto.objects.filter(pk=memo.pk).update(
        status=DocumentoStatus.STATUS_CONCLUIDO,
        assinatura_balizadora=None,
        nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO,
        hipotese_legal=None,
        usuario_criacao=chefe,
        usuario_ultima_modificacao=chefe,
    )


@pytest.fixture(autouse=True)
def estado_documento_seed(documento_seed) -> None:
    """Restaura o documento-alvo antes de cada teste, pois a UI confirma transações."""
    from documento_eletronico.models import DocumentoTexto, SolicitacaoAssinatura
    from documento_eletronico.status import DocumentoStatus
    from processo_eletronico.models import SolicitacaoAlteracaoNivelAcesso

    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    DocumentoTexto.objects.filter(pk=documento.pk).update(
        status=DocumentoStatus.STATUS_CONCLUIDO,
        nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO,
        hipotese_legal=None,
        assinatura_balizadora=None,
    )
    SolicitacaoAssinatura.objects.filter(documento=documento).delete()
    SolicitacaoAlteracaoNivelAcesso.objects.filter(documento_texto=documento).delete()


IDENTIFICADOR_MEMO = 'MEMO 1/2020 - DIDE/CEN/RAIZ'


@pytest.fixture
def configuracao_de_vinculo(estado_documento_seed) -> ConfiguracaoVinculoDocumento:
    """Configuração (PORTARIA revoga MEMO) que habilita a rota de documento relacionado.

    ``_pode_criar_documento_relacionado`` (views.py:534) exige uma ``ConfiguracaoVinculoDocumento``
    ativa para o tipo do documento alvo — sem ela a view é 403 **por construção**, e é por isso que
    o smoke de rotas não a cobria. A suíte não dá flush: o vínculo e o documento base que a execução
    anterior deixou são apagados antes de a configuração ser reusada (armadilha 8).
    """
    from documento_eletronico.models import (
        ConfiguracaoVinculoDocumento,
        DocumentoTexto,
        ModeloDocumento,
        TipoDocumentoTexto,
        TipoVinculoDocumento,
        VinculoDocumentoTexto,
    )
    from documento_eletronico.status import DocumentoStatus

    memo = DocumentoTexto.objects.get(identificador=IDENTIFICADOR_MEMO)
    # `_pode_criar_documento_relacionado` exige `estah_finalizado` (status FINALIZADO, não
    # CONCLUIDO): o MEMO do seed vive CONCLUIDO para os fluxos de assinatura, e é aqui que ele passa
    # a FINALIZADO — o `estado_documento_seed` (autouse, dependência acima) o devolve a CONCLUIDO
    # antes do teste seguinte.
    DocumentoTexto.objects.filter(pk=memo.pk).update(status=DocumentoStatus.STATUS_FINALIZADO)
    configuracao, _ = ConfiguracaoVinculoDocumento.objects.update_or_create(
        tipo_vinculo_documento=TipoVinculoDocumento.objects.get(descricao='Revogação'),
        tipo_documento_base=TipoDocumentoTexto.objects.get(sigla='PORTARIA'),
        tipo_documento_alvo=TipoDocumentoTexto.objects.get(sigla='MEMO'),
        defaults={'modelo_padrao': ModeloDocumento.objects.get(nome='Substituição de Chefia'), 'ativo': True},
    )
    vinculos_antigos = VinculoDocumentoTexto.objects.filter(configuracao=configuracao, documento_texto_alvo=memo)
    documentos_base = list(vinculos_antigos.values_list('documento_texto_base_id', flat=True))
    # `.delete()` de queryset, e não `vinculo.delete()`: o modelo bloqueia a remoção de vínculo com
    # configuração — a guarda existe para a UI/histórico (models.py:2979), não para a faxina da
    # suíte, que precisa ser idempotente entre execuções.
    vinculos_antigos.delete()
    DocumentoTexto.objects.filter(pk__in=documentos_base).delete()
    return configuracao


@pytest.fixture
def logado_documento(logado, documento_seed):
    """Devolve uma página autenticada por papel declarado em ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado
