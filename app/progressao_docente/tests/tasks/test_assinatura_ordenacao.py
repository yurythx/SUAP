"""Testes da correção da assinatura inválida (ordenação determinística) na progressão docente."""

from datetime import date

import pytest
from django.apps.registry import apps

from progressao_docente.tests.factories import AvaliacaoFactory, AvaliacaoItemFactory, CriterioFactory, ItemFactory, ProgressaoDocenteFactory
from rh.tests.factories import ServidorFactory

ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')

pytestmark = pytest.mark.django_db


def _criar_avaliacao_com_itens(qtd_itens=3):
    """Avaliação em andamento com ``qtd_itens`` itens do mesmo critério, todos do avaliado.

    O avaliado sai em ``avaliacao.progressao.avaliado`` — quem precisa dele não recebe mais
    um servidor pronto de fora.
    """
    progressao = ProgressaoDocenteFactory(situacao=ProgressaoDocente.EM_AVALIACAO)
    avaliacao = AvaliacaoFactory(progressao=progressao, situacao=Avaliacao.EM_AVALIACAO)
    criterio = CriterioFactory(formulario=avaliacao.formulario, nome='Critério X')
    vinculo = progressao.avaliado.get_vinculo()
    itens = [
        AvaliacaoItemFactory(avaliacao=avaliacao, item=ItemFactory(criterio=criterio), responsavel=vinculo, pontuacao_form=n + 1)
        for n in range(qtd_itens)
    ]
    return avaliacao, itens


def test_conteudo_avaliacao_ordenado_por_pk(sync_permissions):
    avaliacao, itens = _criar_avaliacao_com_itens(qtd_itens=3)
    conteudo = avaliacao.conteudo_a_ser_assinado_da_avaliacao
    segmentos = conteudo.split('|')
    pks_itens_na_ordem = [str(ai.item.pk) for ai in sorted(itens, key=lambda x: x.pk)]
    pks_no_conteudo = [seg.split('-')[0] for seg in segmentos]
    assert pks_no_conteudo == pks_itens_na_ordem
    # determinismo: ao reler do banco, a ordenação por pk produz o mesmo conteúdo
    avaliacao.refresh_from_db()
    assert avaliacao.conteudo_a_ser_assinado_da_avaliacao == conteudo


def test_conteudo_ciencia_inclui_responsavel_avaliacao(sync_permissions):
    avaliacao, itens = _criar_avaliacao_com_itens(qtd_itens=1)
    avaliado = avaliacao.progressao.avaliado
    avaliador = ServidorFactory()
    ai = itens[0]
    ai.responsavel = avaliado.get_vinculo()
    ai.responsavel_avaliacao = avaliador.get_vinculo()
    ai.save()
    conteudo = avaliacao.conteudo_a_ser_assinado_da_ciencia_de_resultado
    # o bug sobrescrevia o responsável (servidor_a) com o avaliador e zerava o avaliador:
    # ambas as matrículas precisam aparecer para o bug estar corrigido
    assert str(avaliado.matricula) in conteudo
    assert str(avaliador.matricula) in conteudo


def _assinar_com_conteudo(avaliacao, assinatura_attr, snapshot_attr, conteudo):
    # gera uma assinatura sobre um conteúdo arbitrário (simula assinatura da época)
    import_assinatura = __import__('progressoes', fromlist=['assinatura']).assinatura
    chave = avaliacao.chave_a_ser_utilizada_na_assinatura_da_avaliacao
    setattr(avaliacao, assinatura_attr, import_assinatura.gera_assinatura(conteudo, chave))
    setattr(avaliacao, snapshot_attr, conteudo)
    avaliacao.save()


def test_revalida_quando_apenas_ordem(sync_permissions):
    from datetime import datetime

    avaliacao, _itens = _criar_avaliacao_com_itens(qtd_itens=3)
    avaliacao.data_assinatura_avaliador = datetime.now()
    conteudo_atual = avaliacao.conteudo_a_ser_assinado_da_avaliacao
    invertido = '|'.join(reversed(conteudo_atual.split('|')))
    _assinar_com_conteudo(avaliacao, 'assinatura_avaliador', 'string_assinatura_avaliador', invertido)

    import_assinatura = __import__('progressoes', fromlist=['assinatura']).assinatura
    assert import_assinatura.verifica_assinatura(avaliacao.conteudo_a_ser_assinado_da_avaliacao, avaliacao.assinatura_avaliador) is False

    resultado = avaliacao.revalidar_assinaturas_se_apenas_ordenacao()
    assert resultado['avaliador'] == 'revalidada'
    avaliacao.refresh_from_db()
    assert import_assinatura.verifica_assinatura(avaliacao.conteudo_a_ser_assinado_da_avaliacao, avaliacao.assinatura_avaliador) is True


def test_nao_revalida_quando_divergencia_real(sync_permissions):
    from datetime import datetime

    avaliacao, _itens = _criar_avaliacao_com_itens(qtd_itens=2)
    avaliacao.data_assinatura_avaliador = datetime.now()
    conteudo_adulterado = avaliacao.conteudo_a_ser_assinado_da_avaliacao + '|999-conteudo-extra'
    _assinar_com_conteudo(avaliacao, 'assinatura_avaliador', 'string_assinatura_avaliador', conteudo_adulterado)

    resultado = avaliacao.revalidar_assinaturas_se_apenas_ordenacao()
    assert resultado['avaliador'] == 'divergencia'
    import_assinatura = __import__('progressoes', fromlist=['assinatura']).assinatura
    avaliacao.refresh_from_db()
    assert import_assinatura.verifica_assinatura(avaliacao.conteudo_a_ser_assinado_da_avaliacao, avaliacao.assinatura_avaliador) is False


def test_dry_run_nao_grava(sync_permissions):
    avaliacao, _itens = _criar_avaliacao_com_itens(qtd_itens=2)
    conteudo_atual = avaliacao.conteudo_a_ser_assinado_da_avaliacao
    invertido = '|'.join(reversed(conteudo_atual.split('|')))
    _assinar_com_conteudo(avaliacao, 'assinatura_avaliador', 'string_assinatura_avaliador', invertido)
    assinatura_antes = avaliacao.assinatura_avaliador

    resultado = avaliacao.revalidar_assinaturas_se_apenas_ordenacao(dry_run=True)
    assert resultado['avaliador'] == 'revalidada'
    avaliacao.refresh_from_db()
    assert avaliacao.assinatura_avaliador == assinatura_antes


def test_command_revalida(sync_permissions):
    from django.core.management import call_command

    avaliacao, _itens = _criar_avaliacao_com_itens(qtd_itens=2)
    conteudo_atual = avaliacao.conteudo_a_ser_assinado_da_avaliacao
    invertido = '|'.join(reversed(conteudo_atual.split('|')))
    _assinar_com_conteudo(avaliacao, 'assinatura_avaliador', 'string_assinatura_avaliador', invertido)

    call_command('revalidar_assinaturas_progressao_docente')

    import_assinatura = __import__('progressoes', fromlist=['assinatura']).assinatura
    avaliacao.refresh_from_db()
    assert import_assinatura.verifica_assinatura(avaliacao.conteudo_a_ser_assinado_da_avaliacao, avaliacao.assinatura_avaliador) is True


def test_command_revalida_apenas_avaliacao_especifica(sync_permissions):
    from django.core.management import call_command

    import_assinatura = __import__('progressoes', fromlist=['assinatura']).assinatura
    alvo, _itens = _criar_avaliacao_com_itens(qtd_itens=2)
    outra, _itens2 = _criar_avaliacao_com_itens(qtd_itens=2)
    for av in (alvo, outra):
        invertido = '|'.join(reversed(av.conteudo_a_ser_assinado_da_avaliacao.split('|')))
        _assinar_com_conteudo(av, 'assinatura_avaliador', 'string_assinatura_avaliador', invertido)

    call_command('revalidar_assinaturas_progressao_docente', avaliacao=alvo.pk)

    alvo.refresh_from_db()
    outra.refresh_from_db()
    # só a avaliação alvo foi revalidada; a outra permanece inválida
    assert import_assinatura.verifica_assinatura(alvo.conteudo_a_ser_assinado_da_avaliacao, alvo.assinatura_avaliador) is True
    assert import_assinatura.verifica_assinatura(outra.conteudo_a_ser_assinado_da_avaliacao, outra.assinatura_avaliador) is False


def test_revalida_ciencia_quando_apenas_ordem(sync_permissions):
    # cobre o ramo simétrico da ciência (onde estava o bug do responsavel_avaliacao)
    import_assinatura = __import__('progressoes', fromlist=['assinatura']).assinatura
    avaliacao, _itens = _criar_avaliacao_com_itens(qtd_itens=3)
    conteudo_atual = avaliacao.conteudo_a_ser_assinado_da_ciencia_de_resultado
    invertido = '|'.join(reversed(conteudo_atual.split('|')))
    avaliacao.assinatura_avaliado_processo = import_assinatura.gera_assinatura(
        invertido, avaliacao.chave_a_ser_utilizada_na_assinatura_da_ciencia_de_resultado
    )
    avaliacao.string_assinatura_avaliado_processo = invertido
    avaliacao.save()
    assert (
        import_assinatura.verifica_assinatura(avaliacao.conteudo_a_ser_assinado_da_ciencia_de_resultado, avaliacao.assinatura_avaliado_processo)
        is False
    )

    resultado = avaliacao.revalidar_assinaturas_se_apenas_ordenacao()
    assert resultado['ciencia'] == 'revalidada'
    avaliacao.refresh_from_db()
    assert (
        import_assinatura.verifica_assinatura(avaliacao.conteudo_a_ser_assinado_da_ciencia_de_resultado, avaliacao.assinatura_avaliado_processo)
        is True
    )
