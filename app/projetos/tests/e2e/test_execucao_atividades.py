"""Fluxo: execução das atividades e o monitoramento delas (features 006 e 007).

Com o projeto aprovado e o resultado divulgado, o coordenador registra a execução de cada
atividade (aba "Metas/Atividades") e o monitor do projeto — por padrão o Coordenador de
Extensão que o pré-selecionou — aprova, reprova com justificativa ou cancela a avaliação em
"Validar Execução". Registro aprovado não pode mais ser editado. A regressão cara é a execução
mudar de situação por quem não é o monitor.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, vinculo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA = 'Metas/Atividades'
REGISTRAR_EXECUCAO = '/projetos/registro_execucao_etapa/{}/'
EXCLUIR_EXECUCAO = '/projetos/excluir_registro_execucao_etapa/{}/'
VALIDAR = '/projetos/validar_execucao_etapa/{}/'
REPROVAR_ATIVIDADE = '/projetos/reprovar_execucao_etapa/{}/'
CANCELAR_ATIVIDADE = '/projetos/cancelar_avaliacao_etapa/{}/'


def test_coordenador_registra_e_remove_a_execucao_da_atividade(logado_projetos, projeto_em_execucao):
    """ "Registrar Execução" (popup) → a atividade fica aguardando avaliação → "Remover Registro de Execução"."""
    from projetos.models import RegistroExecucaoEtapa

    execucao = projeto_em_execucao()
    etapa = execucao.etapa
    observacao = f'Oficina realizada {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(execucao.projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, REGISTRAR_EXECUCAO.format(etapa.pk))
    popup = popup_em(tela, REGISTRAR_EXECUCAO.format(etapa.pk)).preencher_formulario(
        [
            ('Indicadores Qualitativos', 'lista', 'Atendido Parcialmente'),
            ('Quantidade', 'texto', '3'),
            ('Descrição da Atividade Realizada', 'textarea', observacao),
        ]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Execução registrada com sucesso.')
    registro = RegistroExecucaoEtapa.objects.filter(etapa=etapa, obs=observacao).first()
    assert registro is not None, 'a UI disse que registrou, mas a execução não persistiu'
    assert (registro.tipo_indicador_qualitativo, registro.qtd, registro.dt_avaliacao) == (RegistroExecucaoEtapa.ATENDIDO_PARCIALMENTE, 3, None)

    tela.clicar_aba(ABA)
    clicar_em(tela, EXCLUIR_EXECUCAO.format(etapa.pk))  # `.btn.danger`: o `logado` aceita o confirm
    tela.esperar().sucesso('Registro de execução de etapa removido com sucesso.')
    assert not RegistroExecucaoEtapa.objects.filter(pk=registro.pk).exists(), 'a UI disse que removeu, mas o registro continua'


def test_monitor_aprova_cancela_e_reprova_a_execucao_da_atividade(logado_projetos, projeto_em_execucao):
    """Na aba "Metas" de "Validar Execução": Aprovar → Cancelar Avaliação → Não Aprovar (popup com justificativa)."""
    from projetos.tests.factories import RegistroExecucaoEtapaFactory

    execucao = projeto_em_execucao()
    registro = RegistroExecucaoEtapaFactory(etapa=execucao.etapa)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(VALIDAR.format(execucao.projeto.pk))

    tela.ver_titulo('Validar Execução').clicar_aba('Metas')
    tela.linha(execucao.etapa.descricao).clicar_botao('Aprovar')  # `.confirm`
    tela.esperar().sucesso('Execução de atividade validada com sucesso.')
    registro.refresh_from_db()
    assert (registro.aprovado, registro.avaliador) == (True, vinculo('coordenador_extensao').relacionamento), 'a aprovação não persistiu'

    tela.clicar_aba('Metas')
    clicar_em(tela, CANCELAR_ATIVIDADE.format(registro.pk))
    tela.esperar().sucesso('Avaliação da atividade cancelada com sucesso.')
    registro.refresh_from_db()
    assert (registro.aprovado, registro.dt_avaliacao, registro.avaliador) == (False, None, None), 'o cancelamento não persistiu'

    tela.clicar_aba('Metas')
    clicar_em(tela, REPROVAR_ATIVIDADE.format(registro.pk))
    popup = popup_em(tela, REPROVAR_ATIVIDADE.format(registro.pk)).preencher('Justificativa da Não Aprovação', 'textarea', 'Sem comprovação.')
    popup.salvar_no_popup('Enviar').sucesso('Execução de atividade avaliada com sucesso.')
    registro.refresh_from_db()
    assert (registro.aprovado, registro.justificativa_reprovacao) == (False, 'Sem comprovação.'), 'a reprovação não persistiu'
    assert registro.dt_avaliacao is not None, 'reprovada, a execução continuou sem data de avaliação'


def test_execucao_aprovada_nao_e_mais_registrada(logado_projetos, projeto_em_execucao):
    """``registro_execucao_etapa``: execução já aprovada pelo monitor é 403 — e a tela deixa de oferecer "Editar Execução"."""
    import datetime

    from projetos.tests.factories import RegistroExecucaoEtapaFactory

    execucao = projeto_em_execucao()
    RegistroExecucaoEtapaFactory(etapa=execucao.etapa, aprovado=True, dt_avaliacao=datetime.date.today())
    tela = Tela(logado_projetos('coordenador_projeto'))

    assert tela.buscar(REGISTRAR_EXECUCAO.format(execucao.etapa.pk)).status == 403
    tela.ir(PROJETO.format(execucao.projeto.pk)).clicar_aba(ABA).linha(execucao.etapa.descricao).ver_texto('Aprovado')
    expect(tela.loc(f'//a[@href="{REGISTRAR_EXECUCAO.format(execucao.etapa.pk)}"]')).to_have_count(0)


@pytest.mark.parametrize(
    ('papel', 'status'),
    [
        ('coordenador_extensao', 200),  # o monitor do projeto
        ('gerente', 200),
        ('coordenador_projeto', 200),  # o responsável acompanha, sem os botões de avaliar
        ('outro_coordenador', 403),
        ('avaliador', 403),
    ],
)
def test_validar_execucao_por_papel(logado_projetos, projeto_em_execucao, papel, status):
    execucao = projeto_em_execucao()
    assert Tela(logado_projetos(papel)).buscar(VALIDAR.format(execucao.projeto.pk)).status == status


def test_so_o_monitor_avalia_a_atividade(logado_projetos, projeto_em_execucao):
    """O coordenador do projeto abre "Validar Execução", mas não aprova (``?registro_id`` não grava), não reprova nem cancela."""
    import datetime

    from projetos.tests.factories import EtapaFactory, RegistroExecucaoEtapaFactory

    execucao = projeto_em_execucao()
    pendente = RegistroExecucaoEtapaFactory(etapa=execucao.etapa)
    avaliado = RegistroExecucaoEtapaFactory(
        etapa=EtapaFactory(meta=execucao.meta, responsavel=execucao.participacao, ordem=2), aprovado=True, dt_avaliacao=datetime.date.today()
    )
    tela = Tela(logado_projetos('coordenador_projeto'))

    respostas = (
        tela.buscar(f'{VALIDAR.format(execucao.projeto.pk)}?registro_id={pendente.pk}').status,
        tela.buscar(REPROVAR_ATIVIDADE.format(pendente.pk)).status,
        tela.buscar(CANCELAR_ATIVIDADE.format(avaliado.pk)).status,
    )
    assert respostas == (200, 403, 403), f'validar/reprovar/cancelar pelo coordenador: {respostas}'
    pendente.refresh_from_db()
    avaliado.refresh_from_db()
    assert (pendente.dt_avaliacao, avaliado.aprovado) == (None, True), 'a avaliação mudou pela mão de quem não é o monitor'


def test_estranho_nao_registra_nem_remove_a_execucao(logado_projetos, projeto_em_execucao):
    """Sem ``tem_permissao`` na view, quem barra o coordenador de OUTRO projeto é ``Etapa.pode_registrar_execucao`` (gerenciador do projeto da etapa)."""
    from projetos.models import RegistroExecucaoEtapa
    from projetos.tests.factories import RegistroExecucaoEtapaFactory

    execucao = projeto_em_execucao()
    registro = RegistroExecucaoEtapaFactory(etapa=execucao.etapa)
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = (tela.buscar(REGISTRAR_EXECUCAO.format(execucao.etapa.pk)).status, tela.buscar(EXCLUIR_EXECUCAO.format(execucao.etapa.pk)).status)
    assert respostas == (403, 403)
    assert RegistroExecucaoEtapa.objects.filter(pk=registro.pk).exists(), 'o registro foi apagado por uma rota que respondeu 403'


def test_monitoramento_oferecido_ao_coordenador_de_extensao_abre(logado_projetos, projeto_em_execucao):
    execucao = projeto_em_execucao(monitor='pre_avaliador')
    rota = VALIDAR.format(execucao.projeto.pk)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(execucao.projeto.pk))

    oferecido = tela.loc(f'//a[@href="{rota}"]').count() > 0  # no submenu "Visualizar" (escondido até o clique)
    status = tela.buscar(rota).status
    assert not oferecido or status == 200, f'a tela oferece o monitoramento ao Coordenador de Extensão, e a rota responde {status}'


def test_edital_que_exige_comprovante_recusa_execucao_sem_arquivo(logado_projetos, projeto_em_execucao):
    """``RegistroExecucaoEtapaForm.clean``: com ``exige_comprovante_atividade``, atividade atendida sem arquivo é recusada."""
    from projetos.models import Edital, RegistroExecucaoEtapa

    execucao = projeto_em_execucao()
    Edital.objects.filter(pk=execucao.projeto.edital_id).update(exige_comprovante_atividade=True)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(REGISTRAR_EXECUCAO.format(execucao.etapa.pk))

    tela.preencher('Indicadores Qualitativos', 'lista', 'Atendido').clicar_botao('Salvar')
    tela.esperar().erro('O cadastro do arquivo de comprovação é obrigatório.')
    assert not RegistroExecucaoEtapa.objects.filter(etapa=execucao.etapa).exists(), 'o formulário recusou, mas a execução foi gravada'
