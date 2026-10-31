"""Testes do ciclo de deliberação LAI: transições de situação e linha do tempo de eventos.

O foco é a regra, não a tela: toda transição de ``PDABaseDados.situacao_lai`` deve passar pelo
``lai_service`` e deixar um evento. Os testes de "sem buracos na linha do tempo" existem para
impedir que uma transição volte a ser feita com ``.update()`` cru em algum ponto do módulo.
"""

import datetime

import pytest

from rh.tests.factories import ServidorFactory
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from dados_abertos.enums import SituacaoLAI, TipoEventoLAI
from dados_abertos.models import BaseDados, DeliberacaoLAI, PDABaseDados, PlanoDadosAbertos
from dados_abertos.services.lai_service import (
    PREVIEW_MAX_REGISTROS,
    enviar_para_analise,
    registrar_deliberacao,
    registrar_reenvio,
)

CSV_EXEMPLO = 'curso,campus,total\nInformatica,NAT-CN,320\nEdificacoes,NAT-ZN,210\n'


def _criar_pda(titulo: str = 'PDA 2026-2027', ano: int = 2026) -> PlanoDadosAbertos:
    return PlanoDadosAbertos.objects.create(
        titulo=titulo,
        vigencia_inicio=datetime.date(ano, 1, 1),
        vigencia_fim=datetime.date(ano, 12, 31),
    )


def _criar_base(titulo: str = 'Matrículas por curso', com_recurso: bool = True) -> BaseDados:
    base = BaseDados.objects.create(nome=titulo.lower().replace(' ', '-')[:120], titulo=titulo)
    if com_recurso:
        recurso = base.recursos.create(nome='matriculas', formato='CSV')
        recurso.arquivo.save('matriculas.csv', ContentFile(CSV_EXEMPLO.encode()), save=True)
    return base


def _relacionar(pda, base, situacao=SituacaoLAI.EM_ANALISE) -> PDABaseDados:
    return PDABaseDados.objects.create(pda=pda, base_dados=base, situacao_lai=situacao)


def _tipos(relacao) -> list[int]:
    return list(relacao.eventos_lai.order_by('data', 'id').values_list('tipo', flat=True))


@pytest.fixture
def relacao_em_analise(db):
    return _relacionar(_criar_pda(), _criar_base())


@pytest.fixture
def vinculo(db, sync_permissions):
    """Autor das deliberações. Antes vinha do `admin` que o `light_data` commitava."""
    return ServidorFactory().get_vinculo()


# --------------------------------------------------------------------------- transições


def test_liberar_registra_evento_e_muda_situacao(relacao_em_analise, vinculo):
    registrar_deliberacao(
        relacao_id=relacao_em_analise.pk,
        decisao=SituacaoLAI.LIBERADO,
        parecer='Sem dado pessoal identificado.',
        vinculo=vinculo,
        ip='10.0.0.1',
        user_agent='pytest',
    )

    relacao_em_analise.refresh_from_db()
    assert relacao_em_analise.situacao_lai == SituacaoLAI.LIBERADO
    evento = relacao_em_analise.eventos_lai.get()
    assert evento.tipo == TipoEventoLAI.LIBERACAO
    assert evento.autor == vinculo
    assert evento.ip == '10.0.0.1'


def test_devolver_exige_texto_e_nao_grava_nada_sem_ele(relacao_em_analise, vinculo):
    with pytest.raises(ValidationError):
        registrar_deliberacao(
            relacao_id=relacao_em_analise.pk,
            decisao=SituacaoLAI.DEVOLVIDO,
            parecer='   ',
            vinculo=vinculo,
            ip=None,
            user_agent='',
        )

    relacao_em_analise.refresh_from_db()
    assert relacao_em_analise.situacao_lai == SituacaoLAI.EM_ANALISE, 'a transação deveria ter abortado por inteiro'
    assert not relacao_em_analise.eventos_lai.exists()


def test_devolver_registra_parecer(relacao_em_analise, vinculo):
    registrar_deliberacao(
        relacao_id=relacao_em_analise.pk,
        decisao=SituacaoLAI.DEVOLVIDO,
        parecer='Remover a coluna CPF antes de publicar.',
        vinculo=vinculo,
        ip=None,
        user_agent='',
    )

    relacao_em_analise.refresh_from_db()
    assert relacao_em_analise.situacao_lai == SituacaoLAI.DEVOLVIDO
    evento = relacao_em_analise.eventos_lai.get()
    assert evento.tipo == TipoEventoLAI.DEVOLUCAO
    assert evento.texto == 'Remover a coluna CPF antes de publicar.'


def test_reenvio_devolve_para_analise_com_a_resposta_do_gestor(relacao_em_analise, vinculo):
    registrar_deliberacao(
        relacao_id=relacao_em_analise.pk,
        decisao=SituacaoLAI.DEVOLVIDO,
        parecer='Remover a coluna CPF.',
        vinculo=vinculo,
        ip=None,
        user_agent='',
    )

    registrar_reenvio(
        relacao_id=relacao_em_analise.pk,
        texto='CPF removido, CSV regerado.',
        vinculo=vinculo,
        ip=None,
        user_agent='',
    )

    relacao_em_analise.refresh_from_db()
    assert relacao_em_analise.situacao_lai == SituacaoLAI.EM_ANALISE
    assert _tipos(relacao_em_analise) == [TipoEventoLAI.DEVOLUCAO, TipoEventoLAI.REENVIO]


def test_reenvio_exige_resposta_escrita(relacao_em_analise, vinculo):
    relacao_em_analise.situacao_lai = SituacaoLAI.DEVOLVIDO
    relacao_em_analise.save(update_fields=['situacao_lai'])

    with pytest.raises(ValidationError):
        registrar_reenvio(relacao_id=relacao_em_analise.pk, texto='', vinculo=vinculo, ip=None, user_agent='')

    relacao_em_analise.refresh_from_db()
    assert relacao_em_analise.situacao_lai == SituacaoLAI.DEVOLVIDO
    assert not relacao_em_analise.eventos_lai.exists()


@pytest.mark.parametrize('situacao', [SituacaoLAI.EM_ANALISE, SituacaoLAI.LIBERADO, SituacaoLAI.PENDENTE])
def test_so_reenvia_o_que_esta_devolvido(relacao_em_analise, vinculo, situacao):
    """Reenviar algo que não foi devolvido não faz sentido e não pode reabrir análise já concluída."""
    relacao_em_analise.situacao_lai = situacao
    relacao_em_analise.save(update_fields=['situacao_lai'])

    with pytest.raises(PDABaseDados.DoesNotExist):
        registrar_reenvio(relacao_id=relacao_em_analise.pk, texto='ajustado', vinculo=vinculo, ip=None, user_agent='')

    relacao_em_analise.refresh_from_db()
    assert relacao_em_analise.situacao_lai == situacao


def test_reenvio_de_base_sem_recurso_e_recusado(db, vinculo):
    """Sem recurso não há prévia para o LAI avaliar — mesma regra do envio."""
    relacao = _relacionar(_criar_pda(), _criar_base(com_recurso=False), situacao=SituacaoLAI.DEVOLVIDO)

    with pytest.raises(ValidationError):
        registrar_reenvio(relacao_id=relacao.pk, texto='ajustado', vinculo=vinculo, ip=None, user_agent='')

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.DEVOLVIDO
    assert not relacao.eventos_lai.exists()


# ------------------------------------------------------- linha do tempo sem buracos


def test_envio_automatico_pela_etapa_registra_evento(db):
    """A etapa marcada com ``dispara_analise_lai`` envia à análise — e isso precisa virar evento."""
    from dados_abertos.models import Acao, Etapa

    pda = _criar_pda()
    etapa = Etapa.objects.create(titulo='Análise LAI', ordem=1, dispara_analise_lai=True)
    Acao.objects.create(etapa=etapa, titulo='Deliberar', ordem=1, obrigatoria=True)
    relacao = _relacionar(pda, _criar_base(), situacao=SituacaoLAI.PENDENTE)

    pda.inicializar_checklist()
    pda.atualizar_etapa_atual()

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE
    assert _tipos(relacao) == [TipoEventoLAI.ENVIO]


def test_reabertura_por_edicao_registra_evento(db):
    """Editar o conteúdo de uma base liberada reabre a análise — com rastro permanente."""
    base = _criar_base()
    relacao = _relacionar(_criar_pda(), base, situacao=SituacaoLAI.LIBERADO)

    base.titulo = 'Matrículas por curso e turno'
    base.save()

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE
    assert _tipos(relacao) == [TipoEventoLAI.REABERTURA_POR_EDICAO]


def test_sincronizar_recurso_nao_reabre_a_analise(db):
    """Publicar no CKAN não altera o conteúdo — gravar ``id_remoto`` não pode anular a liberação.

    Regressão: ``RecursoDados.save()`` reabria a análise em todo save, e a sincronização de
    recursos salva justamente ``id_remoto``/``sincronizado_em``.
    """
    from django.utils import timezone

    base = _criar_base()
    relacao = _relacionar(_criar_pda(), base, situacao=SituacaoLAI.LIBERADO)
    recurso = base.recursos.get()

    recurso.id_remoto = 'abc-123'
    recurso.sincronizado_em = timezone.now()
    recurso.save(update_fields=['id_remoto', 'sincronizado_em'])

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.LIBERADO, 'sincronizar o recurso reabriu a análise sem necessidade'
    assert not relacao.eventos_lai.exists()


def test_editar_conteudo_do_recurso_reabre_a_analise(db):
    """O que muda o dado publicado continua invalidando a liberação."""
    base = _criar_base()
    relacao = _relacionar(_criar_pda(), base, situacao=SituacaoLAI.LIBERADO)
    recurso = base.recursos.get()

    recurso.nome = 'matriculas_v2'
    recurso.save()

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE
    assert _tipos(relacao) == [TipoEventoLAI.REABERTURA_POR_EDICAO]


def test_adicionar_recurso_reabre_a_analise(db):
    """Recurso novo é conteúdo novo a publicar: o LAI precisa ver antes de ir ao ar."""
    base = _criar_base()
    relacao = _relacionar(_criar_pda(), base, situacao=SituacaoLAI.LIBERADO)

    novo = base.recursos.create(nome='extra', formato='CSV')
    novo.arquivo.save('extra.csv', ContentFile(CSV_EXEMPLO.encode()), save=True)

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE


def test_envio_em_lote_registra_um_evento_por_base(db, vinculo):
    pda = _criar_pda()
    pendente = _relacionar(pda, _criar_base('Base A'), situacao=SituacaoLAI.PENDENTE)
    devolvida = _relacionar(pda, _criar_base('Base B'), situacao=SituacaoLAI.DEVOLVIDO)
    sem_recurso = _relacionar(pda, _criar_base('Base C', com_recurso=False), situacao=SituacaoLAI.PENDENTE)

    enviadas = enviar_para_analise(PDABaseDados.objects.filter(pda=pda), autor=vinculo)

    assert enviadas == 2, 'a base sem recurso não pode ser enviada'
    assert _tipos(pendente) == [TipoEventoLAI.ENVIO]
    assert _tipos(devolvida) == [TipoEventoLAI.REENVIO], 'quem já tinha sido devolvido volta como reenvio, não como envio inicial'
    assert not sem_recurso.eventos_lai.exists()
    sem_recurso.refresh_from_db()
    assert sem_recurso.situacao_lai == SituacaoLAI.PENDENTE


def test_deliberacao_nao_apaga_o_historico_anterior(relacao_em_analise, vinculo):
    """Rodadas anteriores continuam legíveis — era o que ``motivo_reabertura`` perdia."""
    for rodada in range(2):
        registrar_deliberacao(
            relacao_id=relacao_em_analise.pk,
            decisao=SituacaoLAI.DEVOLVIDO,
            parecer=f'Ajuste da rodada {rodada + 1}.',
            vinculo=vinculo,
            ip=None,
            user_agent='',
        )
        registrar_reenvio(relacao_id=relacao_em_analise.pk, texto=f'Feito na rodada {rodada + 1}.', vinculo=vinculo, ip=None, user_agent='')

    textos = list(relacao_em_analise.eventos_lai.order_by('data', 'id').values_list('texto', flat=True))
    assert textos == [
        'Ajuste da rodada 1.',
        'Feito na rodada 1.',
        'Ajuste da rodada 2.',
        'Feito na rodada 2.',
    ]


def test_rodada_atual_conta_as_devolucoes(relacao_em_analise, vinculo):
    assert relacao_em_analise.rodada_atual == 1

    registrar_deliberacao(
        relacao_id=relacao_em_analise.pk,
        decisao=SituacaoLAI.DEVOLVIDO,
        parecer='Ajustar.',
        vinculo=vinculo,
        ip=None,
        user_agent='',
    )
    registrar_reenvio(relacao_id=relacao_em_analise.pk, texto='Ajustado.', vinculo=vinculo, ip=None, user_agent='')

    relacao_em_analise.refresh_from_db()
    assert relacao_em_analise.rodada_atual == 2


def test_previa_nao_le_o_arquivo_inteiro(db):
    """Mostrar 5 linhas não pode custar carregar um CSV de dados abertos inteiro na memória."""
    from dados_abertos.services.lai_service import PREVIEW_MAX_BYTES, _ler_inicio_do_arquivo, preview_recurso

    base = _criar_base(com_recurso=False)
    recurso = base.recursos.create(nome='grande', formato='CSV')
    linhas = 'coluna_a,coluna_b\n' + ''.join(f'valor{i},{i}\n' for i in range(60_000))
    conteudo = linhas.encode()
    assert len(conteudo) > PREVIEW_MAX_BYTES, 'o teste precisa de um arquivo maior que o teto de leitura'
    recurso.arquivo.save('grande.csv', ContentFile(conteudo), save=True)

    lido = _ler_inicio_do_arquivo(recurso)
    assert len(lido) <= PREVIEW_MAX_BYTES, 'a leitura da prévia passou do teto'
    linhas_lidas = lido.decode().splitlines()
    assert linhas_lidas[-1].count(',') == linhas_lidas[0].count(','), 'o corte deixou uma linha truncada no fim'

    previa = preview_recurso(recurso)
    assert previa['colunas'] == ['coluna_a', 'coluna_b']
    assert len(previa['linhas']) == PREVIEW_MAX_REGISTROS


def test_previa_de_json_maior_que_o_teto_do_csv(db):
    """JSON não é orientado a linha: cortá-lo no meio produz documento inválido, não prévia parcial.

    Regressão real: um recurso de 389 KB (envelope paginado da API) virava "JSON inválido" na tela
    de deliberação porque a leitura parava no teto de bytes do CSV.
    """
    import json as jsonlib

    from dados_abertos.services.lai_service import PREVIEW_MAX_BYTES, preview_recurso

    base = _criar_base(com_recurso=False)
    recurso = base.recursos.create(nome='projetos', formato='JSON')
    registros = [{'titulo': f'Projeto {i}', 'justificativa': 'x' * 200} for i in range(2_000)]
    conteudo = jsonlib.dumps({'results': registros, 'count': len(registros), 'next': None, 'previous': None}).encode()
    assert len(conteudo) > PREVIEW_MAX_BYTES, 'o teste precisa de um JSON maior que o teto do CSV'
    recurso.arquivo.save('projetos.json', ContentFile(conteudo), save=True)

    previa = preview_recurso(recurso)

    assert previa['erro'] is None, f'a prévia falhou: {previa["erro"]}'
    assert previa['colunas'] == ['titulo', 'justificativa']
    assert previa['linhas'][0][0] == 'Projeto 0'


def test_previa_recusa_json_grande_demais_com_mensagem_clara(db):
    """Acima do teto de JSON a prévia se recusa explicitamente, em vez de mentir 'JSON inválido'."""
    from dados_abertos.services import lai_service

    base = _criar_base(com_recurso=False)
    recurso = base.recursos.create(nome='enorme', formato='JSON')
    recurso.arquivo.save('enorme.json', ContentFile(b'[' + b'{"a": 1},' * 500 + b'{"a": 1}]'), save=True)

    original = lai_service.PREVIEW_MAX_BYTES_JSON
    lai_service.PREVIEW_MAX_BYTES_JSON = 100
    try:
        previa = lai_service.preview_recurso(recurso)
    finally:
        lai_service.PREVIEW_MAX_BYTES_JSON = original

    assert previa['linhas'] == []
    assert 'grande' in previa['erro'].lower(), f'mensagem pouco clara: {previa["erro"]!r}'


def test_evento_automatico_dispensa_autor(db):
    """Envio pela etapa e reabertura por edição não têm autor humano — e nem por isso deixam de existir."""
    base = _criar_base()
    relacao = _relacionar(_criar_pda(), base, situacao=SituacaoLAI.LIBERADO)

    base.notas = 'Nova descrição.'
    base.save()

    evento = DeliberacaoLAI.objects.get(pda_base_dados=relacao)
    assert evento.autor is None
    assert evento.texto, 'o evento automático precisa explicar por que a base voltou'


def test_rodada_atual_usa_o_prefetch_sem_consulta_nova(relacao_em_analise, vinculo, django_assert_num_queries):
    """Com ``eventos_lai`` pré-carregado, ler a rodada não pode disparar consulta por base.

    O plano de ação lê ``rodada_atual`` dentro do laço das bases devolvidas; uma consulta ali
    vira N+1 proporcional ao número de bases.
    """
    registrar_deliberacao(
        relacao_id=relacao_em_analise.pk,
        decisao=SituacaoLAI.DEVOLVIDO,
        parecer='Remova o CPF.',
        vinculo=vinculo,
        ip=None,
        user_agent='',
    )

    relacao = PDABaseDados.objects.prefetch_related('eventos_lai').get(pk=relacao_em_analise.pk)
    with django_assert_num_queries(0):
        assert relacao.rodada_atual == 2


def test_transicao_lai_atualiza_a_data_de_atualizacao(relacao_em_analise, vinculo):
    """Deliberar muda a relação, então a "Data de Atualização" exibida no admin tem de andar.

    ``auto_now`` só é gravado quando o campo entra em ``update_fields`` — omiti-lo congela a data.
    """
    antes = PDABaseDados.objects.values_list('data_atualizacao', flat=True).get(pk=relacao_em_analise.pk)

    registrar_deliberacao(
        relacao_id=relacao_em_analise.pk,
        decisao=SituacaoLAI.LIBERADO,
        parecer='',
        vinculo=vinculo,
        ip=None,
        user_agent='',
    )

    depois = PDABaseDados.objects.values_list('data_atualizacao', flat=True).get(pk=relacao_em_analise.pk)
    assert depois > antes
