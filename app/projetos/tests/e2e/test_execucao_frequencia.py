"""Fluxo: frequência/atividade diária dos membros durante a execução (feature 006).

Cada membro registra, na aba "Registros de Frequência/Atividade Diária", o que fez no dia; o
registro nasce "Aguardando Validação" (o do próprio coordenador já nasce validado). Só o autor
edita ou exclui um registro pendente; o coordenador valida um a um ou em lote — e em lote também
cancela validações e exclui. "Gerar Lista de Frequência" filtra os registros por período, membro
e situação. A regressão cara é a frequência — que vira carga horária e certificado — ser validada
ou apagada por quem não coordena o projeto: por isso a sonda do lote com id de OUTRO projeto.

O membro é o ``avaliador`` (servidor): participação de aluno dispara efeitos no ``edu``
(atividade curricular e prática profissional) que não são desta suíte.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, vinculo

if TYPE_CHECKING:
    from projetos.models import Projeto, RegistroFrequencia

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA = 'Registros de Frequência/Atividade Diária'
CADASTRAR = '/projetos/cadastrar_frequencia/{}/'
EDITAR = '/projetos/editar_frequencia/{}/'
EXCLUIR = '/projetos/excluir_frequencia/{}/'
VALIDAR = '/projetos/validar_frequencia/{}/'
VALIDAR_EM_LOTE = '/projetos/validar_registros_frequencia/{}/'
GERAR_LISTA = '/projetos/gerar_lista_frequencia/{}/'

MEMBRO = 'avaliador'


def com_membro(projeto: Projeto) -> Projeto:
    """Põe o ``MEMBRO`` na equipe do projeto (voluntário, sem coordenação)."""
    from projetos.tests.factories import ParticipacaoFactory

    ParticipacaoFactory(projeto=projeto, vinculo_pessoa=vinculo(MEMBRO))
    return projeto


def frequencia_do_membro(projeto: Projeto, **campos: object) -> RegistroFrequencia:
    from projetos.tests.factories import RegistroFrequenciaFactory

    return RegistroFrequenciaFactory(projeto=projeto, cadastrada_por=vinculo(MEMBRO), descricao=f'Atividade do dia {uuid4().hex[:8]}', **campos)


def lote(tela: Tela) -> Tela:
    """O formulário de ações em lote da aba de frequência.

    A aba "Plano de Desembolso" tem OUTRO formulário com o mesmo "Ação:" / "Aplicar"
    (``desembolsos_form``), e vem antes no DOM: sem o recorte, ``preencher('Ação', ...)`` e
    ``clicar_botao('Aplicar')`` acertam o dele.
    """
    return Tela(tela.pagina, escopo='//form[@id="frequencias_form"]')


def celula(tela: Tela, texto: str) -> Locator:
    """A célula com exatamente ``texto`` — a mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


def test_membro_cadastra_edita_e_exclui_a_propria_frequencia(logado_projetos, projeto_em_execucao):
    from projetos.models import RegistroFrequencia

    projeto = com_membro(projeto_em_execucao().projeto)
    descricao = f'Aplicação do questionário {uuid4().hex[:8]}'
    tela = Tela(logado_projetos(MEMBRO)).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, CADASTRAR.format(projeto.pk))
    tela.ver_titulo('Registrar Frequência/Atividade Diária').preencher_formulario(
        [
            ('Descrição', 'textarea', descricao),
            ('Data', 'data', datetime.date.today().strftime('%d/%m/%Y')),
            ('Carga Horária Diária', 'texto', '4'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Frequência/Atividade diária cadastrada com sucesso.')
    registro = RegistroFrequencia.objects.filter(projeto=projeto, descricao=descricao).first()
    assert registro is not None, 'a UI disse que cadastrou, mas a frequência não persistiu'
    assert (registro.cadastrada_por, registro.validada_em) == (vinculo(MEMBRO), None), 'a frequência do membro não nasceu pendente'

    tela.clicar_aba(ABA)
    clicar_em(tela, EDITAR.format(registro.pk))
    tela.ver_titulo('Editar Frequência/Atividade Diária').preencher('Carga Horária Diária', 'texto', '6').clicar_botao('Salvar')
    tela.esperar().sucesso('Frequência/Atividade diária editada com sucesso.')
    registro.refresh_from_db()
    assert registro.carga_horaria == 6, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, EXCLUIR.format(registro.pk))  # `.confirm`
    tela.esperar().sucesso('Frequência/Atividade diária excluída com sucesso.')
    assert not RegistroFrequencia.objects.filter(pk=registro.pk).exists(), 'a UI disse que excluiu, mas a frequência continua'


def test_ate_o_dia_gera_um_registro_por_dia(logado_projetos, projeto_em_execucao):
    """ "Até o dia" preenchido: um registro para cada dia do período, todos pendentes para o membro."""
    from projetos.models import RegistroFrequencia

    projeto = com_membro(projeto_em_execucao().projeto)
    descricao = f'Plantão de atendimento {uuid4().hex[:8]}'
    hoje = datetime.date.today()
    tela = Tela(logado_projetos(MEMBRO)).ir(CADASTRAR.format(projeto.pk))

    tela.preencher_formulario(
        [
            ('Descrição', 'textarea', descricao),
            ('Data', 'data', hoje.strftime('%d/%m/%Y')),
            ('Até o dia', 'data', (hoje + datetime.timedelta(days=2)).strftime('%d/%m/%Y')),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Frequência/Atividade diária cadastrada com sucesso.')
    datas = list(
        RegistroFrequencia.objects.filter(projeto=projeto, descricao=descricao, validada_em=None).order_by('data').values_list('data', flat=True)
    )
    assert datas == [hoje + datetime.timedelta(days=dias) for dias in range(3)], f'o período não virou um registro por dia: {datas}'


def test_frequencia_do_coordenador_ja_nasce_validada(logado_projetos, projeto_em_execucao):
    from projetos.models import RegistroFrequencia

    projeto = projeto_em_execucao().projeto
    descricao = f'Reunião de planejamento {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(CADASTRAR.format(projeto.pk))

    tela.preencher_formulario([('Descrição', 'textarea', descricao), ('Data', 'data', datetime.date.today().strftime('%d/%m/%Y'))])
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Frequência/Atividade diária cadastrada com sucesso.')
    registro = RegistroFrequencia.objects.get(projeto=projeto, descricao=descricao)
    assert registro.validada_por == vinculo('coordenador_projeto'), 'a frequência do coordenador não nasceu validada por ele'


def test_coordenador_valida_a_frequencia_do_membro(logado_projetos, projeto_em_execucao):
    projeto = com_membro(projeto_em_execucao().projeto)
    registro = frequencia_do_membro(projeto)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, VALIDAR.format(registro.pk))  # `.confirm`; volta ao Referer, a tela do projeto
    tela.esperar().sucesso('Frequência/Atividade diária validada com sucesso.')
    registro.refresh_from_db()
    assert registro.validada_por == vinculo('coordenador_projeto'), 'a UI disse que validou, mas não persistiu'


def test_coordenador_valida_cancela_e_exclui_em_lote(logado_projetos, projeto_em_execucao):
    """Seleção + "Ação" + "Aplicar": Validar → Cancelar Validação → Excluir Registros, nos dois registros do membro."""
    from projetos.models import RegistroFrequencia

    projeto = com_membro(projeto_em_execucao().projeto)
    registros = [frequencia_do_membro(projeto), frequencia_do_membro(projeto)]
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))
    expect(tela.loc(f'//form[@action="{VALIDAR_EM_LOTE.format(projeto.pk)}"]')).to_have_count(1)

    for acao, mensagem in (
        ('Validar', 'Registros de Frequência/Atividade diária validados com sucesso.'),
        ('Cancelar Validação', 'Validações dos Registros de Frequência/Atividade diária canceladas com sucesso.'),
    ):
        tela.clicar_aba(ABA)
        for registro in registros:
            lote(tela).selecionar_item(registro.descricao)
        lote(tela).preencher('Ação', 'lista', acao).clicar_botao('Aplicar')
        tela.esperar().sucesso(mensagem)
        situacao = set(RegistroFrequencia.objects.filter(pk__in=[r.pk for r in registros]).values_list('validada_por', flat=True))
        assert situacao == ({vinculo('coordenador_projeto').pk} if acao == 'Validar' else {None}), f'"{acao}" em lote não persistiu: {situacao}'

    tela.clicar_aba(ABA)
    for registro in registros:
        lote(tela).selecionar_item(registro.descricao)
    lote(tela).preencher('Ação', 'lista', 'Excluir Registros').clicar_botao('Aplicar')
    tela.esperar().sucesso('Os Registros de Frequência/Atividade diária não validados foram excluídos com sucesso.')
    assert not RegistroFrequencia.objects.filter(pk__in=[r.pk for r in registros]).exists(), 'a UI disse que excluiu, mas os registros continuam'


def test_lista_de_frequencia_filtra_por_situacao(logado_projetos, projeto_em_execucao):
    projeto = com_membro(projeto_em_execucao().projeto)
    pendente = frequencia_do_membro(projeto)
    validada = frequencia_do_membro(projeto, validada_em=datetime.datetime.now(), validada_por=vinculo('coordenador_projeto'))
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, GERAR_LISTA.format(projeto.pk))
    tela.ver_titulo('Gerar Lista de Frequência/Atividade Diária').preencher('Situação da Validação', 'lista', 'Pendentes').clicar_botao('Enviar')

    tela.esperar()
    expect(celula(tela, pendente.descricao)).to_have_count(1)
    expect(celula(tela, validada.descricao)).to_have_count(0)


@pytest.mark.parametrize(
    ('papel', 'esperado'),
    [
        (MEMBRO, (200, 200)),
        ('coordenador_extensao', (403, 200)),  # do campus: lê a lista, mas não é da equipe para registrar
        ('outro_coordenador', (403, 403)),
    ],
)
def test_frequencia_por_papel(logado_projetos, projeto_em_execucao, papel, esperado):
    """(cadastrar, gerar lista) por papel — o membro e quem vê as frequências do campus leem; só a equipe registra."""
    projeto = com_membro(projeto_em_execucao().projeto)
    tela = Tela(logado_projetos(papel))

    assert (tela.buscar(CADASTRAR.format(projeto.pk)).status, tela.buscar(GERAR_LISTA.format(projeto.pk)).status) == esperado


def test_so_o_coordenador_valida_e_so_o_autor_edita(logado_projetos, projeto_em_execucao):
    """O membro não valida a própria frequência; o coordenador não edita nem exclui, pelo link individual, a do membro."""
    from projetos.models import RegistroFrequencia

    projeto = com_membro(projeto_em_execucao().projeto)
    registro = frequencia_do_membro(projeto)

    membro, coordenador = Tela(logado_projetos(MEMBRO)), Tela(logado_projetos('coordenador_projeto'))
    respostas = (
        membro.buscar(VALIDAR.format(registro.pk)).status,
        coordenador.buscar(EDITAR.format(registro.pk)).status,
        coordenador.buscar(EXCLUIR.format(registro.pk)).status,
        coordenador.buscar(VALIDAR_EM_LOTE.format(projeto.pk)).status,  # só POST
    )
    assert respostas == (403, 403, 403, 403), f'validar (membro) / editar, excluir, lote por GET (coordenador): {respostas}'
    assert RegistroFrequencia.objects.filter(pk=registro.pk, validada_em=None).exists(), 'a frequência mudou por uma rota que respondeu 403'


def forjar_registro(tela: Tela, registro: RegistroFrequencia) -> None:
    """Acrescenta ao formulário do lote um ``registros`` com o id de uma frequência que a lista NÃO ofereceu."""
    tela.loc('//form[@id="frequencias_form"]').evaluate(
        '(form, pk) => { const campo = document.createElement("input"); campo.type = "hidden"; campo.name = "registros"; '
        'campo.value = pk; form.appendChild(campo); }',
        str(registro.pk),
    )


def test_coordenador_nao_valida_frequencia_de_projeto_alheio(logado_projetos, projeto_em_execucao):
    proprio = projeto_em_execucao(sufixo='proprio').projeto
    do_proprio = frequencia_do_membro(com_membro(proprio))
    alheia = frequencia_do_membro(com_membro(projeto_em_execucao(coordenador='outro_coordenador', sufixo='alheio').projeto))
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(proprio.pk))

    tela.clicar_aba(ABA)
    lote(tela).selecionar_item(do_proprio.descricao)
    forjar_registro(tela, alheia)
    lote(tela).clicar_botao('Aplicar')  # "Validar" é a ação selecionada por padrão

    tela.esperar().sucesso('Registros de Frequência/Atividade diária validados com sucesso.')
    alheia.refresh_from_db()
    assert alheia.validada_em is None, 'o coordenador validou a frequência de um membro de projeto alheio'
