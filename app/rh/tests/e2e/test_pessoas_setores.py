# ruff: noqa: UP032
"""Servidor e estrutura: dados pessoais persistidos, chefia real, equivalência SIAPE e jornadas de setor.

Consultas de pessoa jurídica, avaliador e viagem verificam os objetos que efetivamente renderizam.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from uuid import uuid4

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela
from rh.tests.factories import (
    AlertaGestaoPessoaFactory,
    PessoaFisicaFactory,
    PessoaJuridicaFactory,
    SetorFactory,
    SolicitacaoAlteracaoFotoFactory,
    ViagemFactory,
    cnpj_valido,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_editar_dados_pessoais(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('servidor'))
    from rh.models import PessoaFisica

    servidor = rh_seed['servidor']
    orcid = 'https://orcid.org/0000-0000-0000-' + uuid4().hex[:4]
    tela.ir('/rh/servidor/{}/'.format(servidor.matricula)).ver_titulo(str(servidor))
    tela.ir('/rh/servidor/editar_informacoes_pessoais/')
    tela.preencher('ORCID', 'texto', orcid)
    tela.clicar_botao('Salvar')
    tela.sucesso('Informações pessoais salvas com sucesso.')
    assert PessoaFisica.objects.filter(pk=servidor.pessoa_fisica_id, orcid=orcid).exists()


def test_setor_equivalencia_e_bases_legais(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import Setor

    setor = rh_seed['setor']
    siape = rh_seed['siape']
    texto = 'Portaria RH E2E ' + uuid4().hex[:10]
    tela.ir('/rh/organograma/').ver_titulo('Organograma')
    resposta = tela.buscar('/rh/setor_detalhes/{}/'.format(setor.pk))
    assert resposta.status == 200
    assert setor.nome in resposta.text()
    assert Setor.objects.filter(pk=setor.pk, nome=setor.nome).exists()
    tela.ir('/rh/setor/{}/'.format(setor.pk)).ver_titulo(f'{setor.sigla} - {setor.nome}')
    tela.clicar_botao('Editar Bases Legais')
    popup = tela.popup()
    popup.preencher('Bases Legais Internas', 'texto rico', texto)
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Bases Legais do Setor')
    assert Setor.objects.filter(pk=setor.pk, bases_legais_internas__contains=texto).exists()
    resposta = tela.buscar('/rh/editar_bases_legais_setor/{}/'.format(setor.pk))
    assert resposta.status == 200
    assert 'Bases Legais' in resposta.text()
    tela.ir('/admin/rh/setor/?q={}'.format(setor.sigla))
    # Pelo href: todo filho do campus mostra "E2ERH" no caminho, e tela.linha pegaria a primeira linha.
    tela.loc('//a[@href="/rh/equivalencia_setor/{}/"]'.format(setor.pk)).click()
    popup = tela.popup()
    popup.preencher('Setor SIAPE', 'autocomplete', siape.sigla)
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Equivalência do setor')
    resposta = tela.buscar('/rh/equivalencia_setor/{}/'.format(setor.pk))
    assert resposta.status == 200
    assert siape.sigla in resposta.text()
    assert Setor.objects.filter(pk=setor.pk, equivalencia_codigo=siape.codigo).exists()


def test_jornada_do_setor(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import JornadaTrabalho, SetorJornadaHistorico

    setor = SetorFactory(sigla='JR' + uuid4().hex[:8], superior=rh_seed['setor'], campus=False)
    jornada = JornadaTrabalho.objects.filter(nome='40 HORAS SEMANAIS').first()
    tela.ir('/rh/setor_jornada_historico/{}/'.format(setor.pk))
    tela.preencher('Jornada de Trabalho', 'autocomplete', jornada.nome)
    tela.preencher('Data Inicial da Jornada', 'data', date.today().strftime('%d/%m/%Y'))
    tela.clicar_botao('Salvar')
    tela.sucesso('Histórico de Jornada adicionado com sucesso.')
    assert SetorJornadaHistorico.objects.filter(setor=setor, jornada_trabalho__nome=jornada.nome, data_inicio_da_jornada=date.today()).exists()


def test_consultas_de_pessoa_e_viagem(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    from rh.models import Avaliador

    pj = PessoaJuridicaFactory(cnpj=cnpj_valido(int(uuid4().hex[:8], 16)), nome='Empresa E2E ' + uuid4().hex[:10])
    avaliador = Avaliador.objects.get(vinculo=rh_seed['servidor'].get_vinculo())
    viagem = ViagemFactory(servidor=rh_seed['servidor'])
    for papel, url, texto in [
        ('auditor', '/rh/pessoajuridica/{}/'.format(pj.pk), pj.nome),
        ('sistemico', '/rh/avaliador/{}/'.format(avaliador.pk), rh_seed['servidor'].nome),
        ('auditor', '/rh/tela_pcdp/{}/'.format(viagem.pk), viagem.objetivo_viagem),
    ]:
        resposta = Tela(logado_rh(papel)).buscar(url)
        assert resposta.status == 200, resposta.text()[:1000]
        assert texto in resposta.text()


def test_avaliador_alheio_negado(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    from rh.models import Avaliador

    avaliador = Avaliador.objects.get(vinculo=rh_seed['servidor'].get_vinculo())
    assert Tela(logado_rh('saude')).buscar('/rh/avaliador/{}/'.format(avaliador.pk)).status == 403


def test_rejeitar_foto(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import SolicitacaoAlteracaoFoto

    solicitacao = SolicitacaoAlteracaoFotoFactory(solicitante=rh_seed['servidor'])
    motivo = 'Foto ilegível ' + uuid4().hex[:8]
    tela.ir('/rh/detalhe_solicitacao_alteracao_foto/{}/'.format(solicitacao.pk))
    tela.ver_titulo('Solicitação de Alteração de Foto')
    resposta = tela.buscar('/rh/rejeitaralteracaofoto/{}/'.format(solicitacao.pk))
    assert resposta.status == 200
    assert 'Motivo da Rejeição' in resposta.text()
    tela.clicar_botao('Rejeitar')
    popup = tela.popup()
    popup.preencher('Motivo da Rejeição', 'textarea', motivo)
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Solicitação rejeitada.')
    assert SolicitacaoAlteracaoFoto.objects.filter(pk=solicitacao.pk, situacao=SolicitacaoAlteracaoFoto.REJEITADA, motivo_rejeicao=motivo).exists()


def test_alerta_registra_visualizacao(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import AlertaGestaoPessoaVisualizacao

    alerta = AlertaGestaoPessoaFactory(vinculo_analizar=rh_seed['sistemico'].get_vinculo())
    tela.ir('/rh/alertagestaopessoa/{}/ver/'.format(alerta.pk)).ver_texto(alerta.registro_afetado)
    assert AlertaGestaoPessoaVisualizacao.objects.filter(alerta_visualizado=alerta, vinculo=rh_seed['sistemico'].get_vinculo()).exists()


def test_unificar_pessoas(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('admin'))
    from rh.models import DeduplicacaoPessoa, PessoaFisica

    sufixo = uuid4().hex[:8]
    fica = PessoaFisicaFactory(nome=f'Unificação Fica {sufixo}')
    sai = PessoaFisicaFactory(nome=f'Unificação Sai {sufixo}', nome_mae='Mãe da Pessoa que Sai')
    tela.ir('/rh/unificar_pessoas/').ver_titulo('Unificar Pessoas Físicas')
    tela.preencher('Pessoa que fica', 'autocomplete', fica.nome)
    tela.preencher('Pessoa que sai', 'autocomplete', sai.nome)
    tela.clicar_botao('Enviar')
    tela.ver_texto('Preenche a que fica').ver_texto('Mãe da Pessoa que Sai')
    assert PessoaFisica.objects.filter(pk=sai.pk).exists(), 'a prévia não pode unificar'
    assert PessoaFisica.objects.filter(pk=fica.pk, nome_mae__isnull=True).exists(), 'a prévia não pode gravar na pessoa que fica'
    tela.preencher('Confirmo a unificação (não há desfazer)', 'checkbox', 'sim')
    tela.clicar_botao('Enviar')
    tela.sucesso(f'Pessoa física {sai.pk} unificada em {fica.pk}')
    assert not PessoaFisica.objects.filter(pk=sai.pk).exists()
    assert PessoaFisica.objects.filter(pk=fica.pk, nome_mae='Mãe da Pessoa que Sai').exists()
    assert DeduplicacaoPessoa.objects.filter(pf_id=sai.pk, sobrevivente_id=fica.pk, acao=DeduplicacaoPessoa.MESCLADA).exists()
