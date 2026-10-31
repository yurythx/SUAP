# ruff: noqa: UP032
"""Telas de admin do menu do RH: listagem pelo papel que o ``menu.yaml`` libera e os CRUDs que o RH opera.

O gate ``--rotas`` não enxerga ``/admin/``: este arquivo é o que prova que as 25 telas de admin do
menu (além de instituição, função, histórico de função, setor e ação de saúde, cobertas em outros
arquivos) abrem para o papel real, e não só para o superusuário. O smoke de listagem afirma uma linha
de um objeto criado no próprio teste (ou do seed) — o rótulo da tela coincide com o item do menu
lateral e passaria em qualquer 200. Os cadastros voltam para a listagem e afirmam a mensagem e o
banco; as reativações afirmam a transição de estado entre o RH do campus (que solicita) e o RH
sistêmico (que decide).

``campoexcecao`` é aberto como ``admin`` porque nenhum ``permissions.yaml`` concede permissão sobre
``rh.CampoExcecao``: o item de menu só existe para superusuário.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from urllib.parse import quote
from uuid import uuid4

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela
from rh.tests.factories import (
    AcaoSaudeFactory,
    AfastamentoSiapeEfetivoExercicioFactory,
    AfastamentoSiapeFactory,
    AgendaAtendimentoHorarioFactory,
    AlertaGestaoPessoaFactory,
    AreaVinculacaoFactory,
    CargaHorariaReduzidaFactory,
    CronogramaFolhaFactory,
    HorarioAgendadoFactory,
    IndicadoresPublicosFactory,
    PadraoVencimentoFactory,
    QuantitativoCargoClassePorCampusFactory,
    ServidorAfastamentoFactory,
    ServidorFactory,
    ServidorOcorrenciaFactory,
    ServidorSetorLotacaoHistoricoFactory,
    SetorFactory,
    SetorJornadaHistoricoFactory,
    SolicitacaoAlteracaoFotoFactory,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def _nome(prefixo: str) -> str:
    return '{} E2E {}'.format(prefixo, uuid4().hex[:10])


def _servidor(setor: object, **campos: object) -> object:
    """Servidor novo no campus do seed: estado consumível não se compartilha (a suíte não dá flush)."""
    return ServidorFactory(matricula=str(int(uuid4().hex[:8], 16)), setor=setor, pessoa_fisica__nome=_nome('Servidor'), **campos)


def _afastamento() -> object:
    # `codigo` tem 4 caracteres e é get-or-create: numa colisão a factory devolve o de outra rodada,
    # então as asserções usam o nome do objeto devolvido, não o pedido.
    return AfastamentoSiapeFactory(codigo=uuid4().hex[:4], nome=_nome('Afastamento'))


def _afastamento_siape(seed: dict) -> list[tuple[str, str]]:
    afastamento = _afastamento()
    return [
        ('/admin/rh/afastamentosiape/?q={}'.format(afastamento.codigo), afastamento.nome),
        ('/admin/rh/afastamentosiape/{}/change/'.format(afastamento.pk), afastamento.nome),
    ]


def _efetivo_exercicio(seed: dict) -> list[tuple[str, str]]:
    afastamento = _afastamento()
    AfastamentoSiapeEfetivoExercicioFactory(afastamentos=[afastamento])
    return [('/admin/rh/afastamentosiapeefetivoexercicio/?q={}'.format(afastamento.codigo), afastamento.nome)]


def _agenda_horario(seed: dict) -> list[tuple[str, str]]:
    horario = AgendaAtendimentoHorarioFactory(profissional=seed['saude'])
    return [('/admin/rh/agendaatendimentohorario/?q={}'.format(quote(horario.acao_saude.descricao)), '/rh/agendar_horario/{}/'.format(horario.pk))]


def _alerta(seed: dict) -> list[tuple[str, str]]:
    servidor = _servidor(seed['setor'])
    alerta = AlertaGestaoPessoaFactory(vinculo_analizar=servidor.get_vinculo())
    return [
        ('/admin/rh/alertagestaopessoa/?q={}'.format(servidor.matricula), alerta.registro_afetado),
        ('/admin/rh/alertagestaopessoa/{}/change/'.format(alerta.pk), alerta.registro_afetado),
    ]


def _avaliador(seed: dict) -> list[tuple[str, str]]:
    servidor = seed['servidor']
    return [('/admin/rh/avaliador/?q={}'.format(servidor.matricula), servidor.nome)]


def _carga_horaria(seed: dict) -> list[tuple[str, str]]:
    processo = CargaHorariaReduzidaFactory(servidor=_servidor(seed['setor']))
    url = '/admin/rh/cargahorariareduzida/?tab=tab_processos_pendentes_de_validacao_rh&q={}'
    return [(url.format(processo.servidor.matricula), '/rh/abrir_processo_afastamento_parcial/{}/'.format(processo.pk))]


def _cargo_emprego(seed: dict) -> list[tuple[str, str]]:
    cargo = seed['servidor'].cargo_emprego
    return [('/admin/rh/cargoemprego/?usado_no_sistema=SIM&q={}'.format(cargo.codigo), '/admin/rh/cargoemprego/{}/'.format(cargo.pk))]


def _horario_agendado(seed: dict) -> list[tuple[str, str]]:
    agendamento = HorarioAgendadoFactory(horario__profissional=seed['saude'], solicitante=seed['servidor'].get_vinculo())
    acao = agendamento.horario.acao_saude
    return [('/admin/rh/horarioagendado/?horario__acao_saude__id__exact={}'.format(acao.pk), '/rh/cancelar_agendamento/{}/'.format(agendamento.pk))]


def _indicador(seed: dict) -> list[tuple[str, str]]:
    indicador = IndicadoresPublicosFactory()
    return [('/admin/rh/indicadorespublicos/?titulo={}'.format(quote(indicador.titulo)), '/admin/rh/indicadorespublicos/{}/'.format(indicador.pk))]


def _padrao_vencimento(seed: dict) -> list[tuple[str, str]]:
    padrao = PadraoVencimentoFactory()
    return [
        ('/admin/rh/padraovencimento/?categoria=docente&classe=E', '/admin/rh/padraovencimento/{}/'.format(padrao.pk)),
        # Só `view`: nenhum grupo tem change, e o `/change/` responde 403. O título é o `str` (classe + mérito).
        ('/admin/rh/padraovencimento/{}/view/'.format(padrao.pk), str(padrao)),
    ]


def _quadro_referencia(seed: dict) -> list[tuple[str, str]]:
    quantitativo = QuantitativoCargoClassePorCampusFactory(uo=seed['setor'].uo)
    url = '/admin/rh/quantitativocargoclasseporcampus/?cargo_classe__id__exact={}'
    return [(url.format(quantitativo.cargo_classe_id), '/admin/rh/quantitativocargoclasseporcampus/{}/'.format(quantitativo.pk))]


def _servidor_ativo(seed: dict) -> list[tuple[str, str]]:
    servidor = seed['servidor']
    return [('/admin/rh/servidor/?ativo__exact=1&q={}'.format(servidor.matricula), servidor.nome)]


def _servidor_afastamento(seed: dict) -> list[tuple[str, str]]:
    hoje = date.today()
    afastamento = ServidorAfastamentoFactory(
        servidor=seed['servidor'], afastamento=_afastamento(), data_inicio=hoje - timedelta(days=10), data_termino=hoje - timedelta(days=5)
    )
    nome = afastamento.afastamento.nome
    return [
        # O filtro lateral lista todo afastamento do catálogo: na listagem, só o link da linha prova o registro.
        ('/admin/rh/servidorafastamento/?q={}'.format(afastamento.afastamento.codigo), '/admin/rh/servidorafastamento/{}/'.format(afastamento.pk)),
        ('/admin/rh/servidorafastamento/{}/change/'.format(afastamento.pk), nome),
    ]


def _solicitacao_foto(seed: dict) -> list[tuple[str, str]]:
    solicitacao = SolicitacaoAlteracaoFotoFactory(solicitante=_servidor(seed['setor']))
    url = '/admin/rh/solicitacaoalteracaofoto/?q={}'.format(quote(solicitacao.solicitante.nome))
    return [(url, '/rh/detalhe_solicitacao_alteracao_foto/{}/'.format(solicitacao.pk))]


def _campi(seed: dict) -> list[tuple[str, str]]:
    setor = seed['setor']
    return [('/admin/rh/unidadeorganizacional/?q={}'.format(setor.sigla), '/admin/rh/unidadeorganizacional/{}/'.format(setor.uo_id))]


def _cronograma_folha(seed: dict) -> list[tuple[str, str]]:
    cronograma = CronogramaFolhaFactory()
    return [('/admin/rh/cronogramafolha/?id__exact={}'.format(cronograma.pk), str(cronograma))]


def _historico_setor(seed: dict) -> list[tuple[str, str]]:
    """O ``save`` do servidor já abre o histórico no setor SUAP."""
    servidor = _servidor(seed['setor'])
    return [('/admin/rh/servidorsetorhistorico/?q={}'.format(servidor.matricula), servidor.nome)]


def _historico_lotacao(seed: dict) -> list[tuple[str, str]]:
    servidor = _servidor(seed['setor'])
    ServidorSetorLotacaoHistoricoFactory(servidor=servidor, setor_lotacao=seed['siape'], setor_exercicio=seed['siape'])
    return [('/admin/rh/servidorsetorlotacaohistorico/?q={}'.format(servidor.matricula), servidor.nome)]


def _jornada_setor(seed: dict) -> list[tuple[str, str]]:
    setor = SetorFactory(sigla='JOR' + uuid4().hex[:6], superior=seed['setor'])
    SetorJornadaHistoricoFactory(setor=setor)
    return [('/admin/rh/setorjornadahistorico/?q={}'.format(setor.sigla), '/rh/setor_jornada_historico/{}/'.format(setor.pk))]


LISTAGENS = [
    ('sistemico', _afastamento_siape),
    ('sistemico', _efetivo_exercicio),
    ('saude', _agenda_horario),
    ('sistemico', _alerta),
    ('sistemico', _avaliador),
    ('campus', _carga_horaria),
    ('auditor', _cargo_emprego),
    ('saude', _horario_agendado),
    ('sistemico', _indicador),
    ('campus', _padrao_vencimento),
    ('sistemico', _quadro_referencia),
    ('sistemico', _servidor_ativo),
    ('sistemico', _servidor_afastamento),
    ('sistemico', _solicitacao_foto),
    ('campus', _campi),
    ('sistemico', _cronograma_folha),
    ('auditor', _historico_setor),
    ('auditor', _historico_lotacao),
    ('campus', _jornada_setor),
]


@pytest.mark.parametrize(('papel', 'fabrica'), LISTAGENS, ids=[fabrica.__name__.strip('_') for _, fabrica in LISTAGENS])
def test_listagem_admin(logado_rh: Callable[[str], Page], rh_seed: dict, papel: str, fabrica: Callable[[dict], list[tuple[str, str]]]) -> None:
    tela = Tela(logado_rh(papel))
    for url, texto in fabrica(rh_seed):
        resposta = tela.buscar(url)
        assert resposta.status == 200, f'{url}: HTTP {resposta.status}: {resposta.text()[:1000]}'
        assert texto in resposta.text(), f'{url}: {texto!r} ausente da tela'


def test_area_de_vinculacao(logado_rh: Callable[[str], Page]) -> None:
    """Entra no fim da ordem: inserir numa posição já ocupada é o bug do teste seguinte."""
    tela = Tela(logado_rh('sistemico'))
    from rh.models import AreaVinculacao

    descricao = _nome('Área')
    ultima = AreaVinculacao.objects.count() + 1
    tela.ir('/admin/rh/areavinculacao/add/')
    tela.preencher_formulario([('Descrição', 'texto', descricao), ('Ordem', 'lista', str(ultima))])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert AreaVinculacao.objects.filter(descricao=descricao, ordem=ultima).exists(), 'a UI disse que salvou, mas não persistiu'


def test_area_de_vinculacao_no_inicio_da_ordem(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import AreaVinculacao

    AreaVinculacaoFactory.create_batch(2)
    descricao = _nome('Área')
    tela.ir('/admin/rh/areavinculacao/add/')
    tela.preencher_formulario([('Descrição', 'texto', descricao), ('Ordem', 'lista', '1')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.', timeout=3000)
    assert AreaVinculacao.objects.filter(descricao=descricao, ordem=1).exists()


def test_data_de_consulta_bloqueada(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('saude'))
    from rh.models import DataConsultaBloqueada

    acao = AcaoSaudeFactory()
    dia = date.today() + timedelta(days=3)
    motivo = _nome('Bloqueio')
    tela.ir('/admin/rh/dataconsultabloqueada/add/')
    tela.preencher_formulario(
        [
            ('Ação de Saúde', 'autocomplete', acao.descricao),
            ('Data da Consulta', 'data', dia.strftime('%d/%m/%Y')),
            ('Motivo do Bloqueio', 'texto', motivo),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert DataConsultaBloqueada.objects.filter(acao_saude=acao, data_consulta_bloqueada=dia, motivo_bloqueio=motivo).exists()
    tela.ver_texto(motivo)


def test_excecao_de_atualizacao(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """O campo de exceção nasce pelo superusuário (único com permissão) e o RH sistêmico o aplica a um servidor."""
    tela = Tela(logado_rh('admin'))
    from rh.enums import TipoExtracao
    from rh.models import CampoExcecao, ExcecaoDado

    campo = 'campo_e2e_' + uuid4().hex[:10]
    tela.ir('/admin/rh/campoexcecao/add/')
    tela.preencher('Campo', 'texto', campo)
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert CampoExcecao.objects.filter(campo=campo).exists(), 'a UI disse que salvou, mas não persistiu'

    servidor = _servidor(rh_seed['setor'])
    tela = Tela(logado_rh('sistemico')).ir('/admin/rh/excecaodado/add/')
    tela.preencher_formulario(
        [('Dados', 'autocomplete multiplo', campo), ('Servidor', 'autocomplete', servidor.matricula), ('Tipo de Extração', 'lista', 'Webservice')]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert ExcecaoDado.objects.filter(servidor=servidor, tipo_extracao=TipoExtracao.TIPO_WEBSERVICE, campos__campo=campo).exists()


def test_editar_campus(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """Edita o campus do seed: criar um campus por rodada acumularia campi no banco que os módulos dividem."""
    tela = Tela(logado_rh('sistemico'))
    from rh.models import UnidadeOrganizacional

    setor = rh_seed['setor']
    telefone = '(84) 4005-{}'.format(str(int(uuid4().hex[:4], 16) % 10000).zfill(4))
    tela.ir('/admin/rh/unidadeorganizacional/{}/change/'.format(setor.uo_id))
    tela.preencher('Telefone', 'texto', telefone)
    tela.clicar_botao('Salvar')
    tela.sucesso('Atualização realizada com sucesso.')
    assert UnidadeOrganizacional.objects.filter(pk=setor.uo_id, telefone=telefone).exists()


def test_reativacao_temporaria_solicitada_e_negada(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """O RH do campus só solicita; o sistêmico decide. Autorizar consultaria o SIAPE externo, negar não."""
    tela = Tela(logado_rh('campus'))
    from rh.models import ServidorReativacaoTemporaria

    inativo = _servidor(rh_seed['setor'], ativo=False)
    justificativa = _nome('Reativação temporária')
    fim = date.today() + timedelta(days=30)
    tela.ir('/admin/rh/servidorreativacaotemporaria/add/')
    tela.preencher_formulario(
        [
            ('Servidor', 'autocomplete', inativo.matricula),
            ('Data de Fim', 'data', fim.strftime('%d/%m/%Y')),
            ('Justificativa', 'textarea', justificativa),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    solicitada = ServidorReativacaoTemporaria.objects.filter(
        servidor=inativo, situacao=ServidorReativacaoTemporaria.STATUS_SOLICITADA, data_fim=fim, cadastrado_por=rh_seed['campus'].get_user()
    )
    assert solicitada.exists(), 'a UI disse que salvou, mas não persistiu'
    pk = solicitada.get().pk

    tela = Tela(logado_rh('sistemico')).ir('/admin/rh/servidorreativacaotemporaria/?q={}'.format(inativo.matricula))
    tela.linha(inativo.matricula).clicar_botao('Não autorizar')
    tela.sucesso('Solicitação não autorizada.')
    assert ServidorReativacaoTemporaria.objects.filter(pk=pk, situacao=ServidorReativacaoTemporaria.STATUS_NEGADA).exists()


def test_reativacao_permanente_solicitada_e_autorizada(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """Autorizar remove a ocorrência de exclusão e reativa servidor e vínculo — a regra que importa na reativação."""
    tela = Tela(logado_rh('campus'))
    from rh.models import Servidor, ServidorOcorrencia, ServidorReativacaoPermanente

    inativo = _servidor(rh_seed['setor'], ativo=False)
    exclusao = ServidorOcorrenciaFactory(servidor=inativo)
    justificativa = _nome('Reativação permanente')
    tela.ir('/admin/rh/servidorreativacaopermanente/add/')
    tela.preencher_formulario([('Servidor', 'autocomplete', inativo.matricula), ('Justificativa', 'textarea', justificativa)])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    solicitada = ServidorReativacaoPermanente.objects.filter(servidor=inativo, situacao=ServidorReativacaoPermanente.STATUS_SOLICITADA)
    assert solicitada.exists(), 'a UI disse que salvou, mas não persistiu'
    pk = solicitada.get().pk

    tela = Tela(logado_rh('sistemico')).ir('/admin/rh/servidorreativacaopermanente/?q={}'.format(inativo.matricula))
    tela.linha(inativo.matricula).clicar_botao('Autorizar')
    tela.sucesso('Solicitação autorizada com sucesso.')
    assert ServidorReativacaoPermanente.objects.filter(
        pk=pk,
        situacao=ServidorReativacaoPermanente.STATUS_AUTORIZADA,
        ocorrencia_removida=True,
        ocorrencia_codigo=exclusao.ocorrencia.codigo,
    ).exists()
    assert Servidor.objects.filter(pk=inativo.pk, ativo=True).exists(), 'autorizou, mas o servidor continua inativo'
    assert not ServidorOcorrencia.objects.filter(pk=exclusao.pk).exists(), 'autorizou, mas a ocorrência de exclusão ficou'
