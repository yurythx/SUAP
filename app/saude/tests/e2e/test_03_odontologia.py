"""Fluxo odontológico: situação clínica, procedimentos, plano e integração com enfermagem.

O teste continua a cadeia do prontuário e percorre as telas que sustentam o tratamento
odontológico. Ele pega regressões no odontograma interativo, nas transições do plano, nas
permissões do Técnico em Saúde Bucal e no encaminhamento para a enfermagem.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Atendimento, Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ATENDIMENTO_ODONTOLOGICO = '/saude/atendimento_odontologico/{}/'
ADICIONAR_ODONTOGRAMA = '/saude/adicionar_odontograma/{}/'
ADICIONAR_PROCEDIMENTO = '/saude/adicionar_procedimento_odontologico/{}/'
ADICIONAR_PERIODONTAL = '/saude/adicionar_exame_periodontal/{}/'
EXCLUIR_PERIODONTAL = '/saude/excluir_exame_periodontal/{}/'
ADICIONAR_ESTOMATOLOGICO = '/saude/adicionar_exame_estomatologico/{}/'
HISTORICO_ESTOMATOLOGICO = '/saude/historico_exame_estomatologico/{}/'
GERAR_PLANO = '/saude/gerar_plano_tratamento/{}/'
INDICAR_PROCEDIMENTO = '/saude/indicar_procedimento/{}/'
REGISTRAR_EXECUCAO = '/saude/registrar_execucao_plano/{}/'
OBS_REGISTRAR_EXECUCAO = '/saude/obs_registrar_execucao/{}/'
ADICIONAR_INTERVENCAO = '/saude/adicionar_intervencao/{}/'
EXCLUIR_INTERVENCAO = '/saude/excluir_intervencao/{}/'
ORDEM_PLANO = '/saude/ordem_plano_tratamento/{}/{}/'
RESOLVER_PERIODONTAL = '/saude/resolver_exame_periodontal/{}/'
ALTERAR_TIPO_CONSULTA = '/saude/alterar_tipo_consulta/{}/'
EXCLUIR_PROCEDIMENTO = '/saude/excluir_procedimento_odontologico/{}/'
ENCAMINHAR_ENFERMAGEM = '/saude/encaminhar_enfermagem_odonto/{}/'
REGISTRAR_INTERVENCAO_ODONTO = '/saude/registrar_intervencao_odonto/{}/{}/'
RELATORIO_ODONTOLOGICO = '/saude/relatorios_atendimentos_odontologicos/'


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _ultimo_atendimento(tipo: int) -> Atendimento:
    """Devolve o atendimento mais recente do paciente para o tipo informado."""
    from saude.models import Atendimento

    atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=tipo).order_by('-id').first()
    assert atendimento is not None, f'atendimento do tipo {tipo} não foi criado pela tela'
    return atendimento


def _abrir_atendimento_odontologico(tela: Tela) -> Atendimento:
    """Abre o atendimento pelo prontuário, como faria o Odontólogo."""
    from saude.models import SituacaoAtendimento, TipoAtendimento

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(f'/saude/prontuario/{vinculo.pk}/').ver_titulo('Prontuário')
    tela.clicar_botao('Atendimento Odontológico')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/atendimento_odontologico/\d+/$'))
    tela.esperar().sucesso('Atendimento Odontológico gerado com sucesso.').ver_titulo('Atendimento Odontológico')
    atendimento = _ultimo_atendimento(TipoAtendimento.ODONTOLOGICO)
    assert atendimento.situacao == SituacaoAtendimento.ABERTO, 'a UI disse que abriu, mas o atendimento não ficou aberto'
    return atendimento


def _preencher_exame_estomatologico(tela: Tela) -> None:
    """Preenche as doze regiões do exame com o roteiro da feature 0001."""
    campos = [
        'Alteração nos lábios',
        'Alteração na língua',
        'Alteração na gengiva',
        'Alteração no assoalho',
        'Alteração na mucosa jugal',
        'Alteração no palato duro',
        'Alteração no palato mole',
        'Alteração no rebordo',
        'Alteração na cadeia ganglionar',
        'Alteração nas tonsilas palatinas',
        'Alteração na ATM',
        'Alteração na Oclusão',
    ]
    tela.preencher_formulario([(campo, 'Texto', 'Não') for campo in campos])


def _marcar_face(tela: Tela, codigo: str) -> Tela:
    """Marca uma face no odontograma e confirma a sincronização com o campo enviado.

    O clique é JS do widget (``saude/static/saude/js/odontograma.js``): ele escreve o código
    da face no campo oculto que o formulário envia, e é esse campo que o teste verifica — sem
    ele o clique pode até pintar a face e não persistir nada.
    """
    alvo = tela.loc(f'//*[@id="{codigo}"]').first
    expect(alvo).to_be_visible()
    alvo.click()
    faces = tela.loc('//input[@id="id_faces" or @id="id_faces_marcadas"]').first
    expect(faces).to_have_value(re.compile(rf'(?:^|-){re.escape(codigo)}(?:_|-)'))
    return tela


def test_fluxo_odontologico_completo(logado_saude: Callable[[str], Page]) -> None:
    """Odontólogo e Técnico percorrem as 21 rotas do tratamento e suas transições."""
    tela = Tela(logado_saude('odontologo'))

    from saude.models import (
        Atendimento,
        ExameEstomatologico,
        ExamePeriodontal,
        Odontograma,
        PlanoTratamento,
        ProcedimentoOdontologico,
        SituacaoAtendimento,
        TipoAtendimento,
    )

    atendimento = _abrir_atendimento_odontologico(tela)

    tela.ir(ADICIONAR_ODONTOGRAMA.format(atendimento.pk)).ver_titulo('Adicionar Odontograma')
    tela.ir(ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)).clicar_aba('Situação Clínica')
    tela.quadro('Odontograma').preencher('Situação Clínica', 'Lista', 'Cárie')
    _marcar_face(tela.quadro('Odontograma'), 'A_O_48').clicar_botao('Salvar')
    tela.sucesso('Odontograma atualizado com sucesso.')
    odontograma = Odontograma.objects.get(atendimento=atendimento)
    assert odontograma.salvo, 'a UI disse que salvou, mas o odontograma não foi marcado como salvo'
    assert 'A_O_48' in odontograma.dentes_alterados, 'a UI disse que salvou, mas a face não persistiu'

    tela.ir(ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)).clicar_aba('Situação Clínica')
    tela.quadro('Exame Periodontal').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_PERIODONTAL.format(atendimento.pk)}$'))
    tela.preencher_formulario([('Ocorrência', 'Lista', 'Sangramento'), ('Sextante', 'FilteredSelectMultiple', 'S1, S2')])
    tela.clicar_botao('Salvar').sucesso('Exame periodontal registrado com sucesso.')
    exame = ExamePeriodontal.objects.get(atendimento=atendimento, ocorrencia=ExamePeriodontal.SANGRAMENTO)
    assert exame.sextante == 'S1; S2', 'a UI disse que salvou, mas o exame periodontal não persistiu'

    # O box "Exame Periodontal" do atendimento odontológico só oferece Adicionar/Resolver/
    # Excluir: o ícone de edição e a `editar_exame_periodontal` vivem na aba Odontograma da
    # avaliação biomédica, onde a view redireciona de volta. Aqui fica o ciclo suportado
    # nesta tela (registrar, resolver e excluir); a edição é coberta em `test_02`.
    tela.ir(ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)).clicar_aba('Situação Clínica')
    tela.quadro('Exame Periodontal').linha('Sangramento').clicar_botao('Resolver')
    expect(tela.pagina).to_have_url(re.compile(rf'{ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)}\?tab=aba_situacao_clinica$'))
    tela.esperar().sucesso('Exame periodontal alterado com sucesso.')
    exame.refresh_from_db()
    assert exame.resolvido, 'a UI disse que resolveu, mas o exame continua pendente'

    tela.clicar_aba('Situação Clínica')
    tela.quadro('Exame Periodontal').linha('Sangramento').clicar_icone('remoção')
    tela.sucesso('Exame periodontal excluido com sucesso.')
    assert not ExamePeriodontal.objects.filter(pk=exame.pk).exists(), 'a UI disse que excluiu, mas o exame permanece'

    tela.clicar_aba('Situação Clínica')
    tela.quadro('Exame Estomatológico').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ESTOMATOLOGICO.format(atendimento.pk)}$'))
    _preencher_exame_estomatologico(tela)
    tela.clicar_botao('Salvar').sucesso('Exame Estomatológico registrado com sucesso.')
    assert ExameEstomatologico.objects.filter(atendimento=atendimento, labios='Não', oclusao='Não').exists(), (
        'a UI disse que salvou, mas o exame estomatológico não persistiu'
    )

    tela.ir(HISTORICO_ESTOMATOLOGICO.format(atendimento.pk)).ver_titulo('Histórico dos Exames Estomatológicos').ver_texto('Não')

    tela.ir(ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)).clicar_aba('Plano de Tratamento')
    tela.clicar_botao('Gerar Plano de Tratamento Automático')
    tela.sucesso('Plano de Tratamento criado com sucesso.')
    plano = PlanoTratamento.objects.get(atendimento=atendimento, situacao_clinica__descricao='Cárie')
    assert plano.procedimento_id is None, 'o plano automático não preservou a etapa de indicação do procedimento'

    tela.clicar_aba('Plano de Tratamento')
    tela.aba('Plano de Tratamento').linha('Cárie').clicar_botao('Indicar Procedimento')
    popup = tela.popup()
    popup.preencher('Procedimento', 'Lista', 'Restauração de Amálgama')
    popup.salvar_no_popup().sucesso('Procedimento registrado com sucesso.')
    plano.refresh_from_db()
    assert plano.procedimento is not None, 'a UI disse que indicou, mas o plano continua sem procedimento'
    assert plano.procedimento.denominacao == 'Restauração de Amálgama', 'o procedimento indicado não persistiu no plano'

    ordem_anterior = plano.ordem
    tela.clicar_aba('Plano de Tratamento')
    tela.aba('Plano de Tratamento').linha('Restauração de Amálgama').clicar_botao('Descer')
    tela.sucesso('Ordem do plano de tratamento alterada com sucesso.')
    plano.refresh_from_db()
    assert plano.ordem != ordem_anterior, 'a UI disse que reordenou, mas a ordem não mudou'

    tela.clicar_aba('Plano de Tratamento')
    tela.aba('Plano de Tratamento').linha('Restauração de Amálgama').clicar_botao('Registrar Execução')
    expect(tela.pagina).to_have_url(re.compile(rf'{OBS_REGISTRAR_EXECUCAO.format(plano.pk)}$'))
    tela.preencher('Observação', 'TextArea', 'Execução odontológica E2E').clicar_botao('Enviar')
    tela.sucesso('Execução registrada com sucesso.')
    plano.refresh_from_db()
    assert plano.realizado, 'a UI disse que executou, mas o plano continua pendente'
    procedimento_executado = ProcedimentoOdontologico.objects.get(atendimento=atendimento, observacao='Execução odontológica E2E')
    assert procedimento_executado.procedimento == plano.procedimento, 'a execução não materializou o procedimento indicado'

    tela.clicar_aba('Plano de Tratamento').clicar_botao('Adicionar Registro no Plano de Tratamento')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_INTERVENCAO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [
            ('Dente', 'Lista', '11'),
            ('Face', 'Lista', 'Vestibular'),
            ('Situação Clínica', 'Lista', 'Cárie'),
            ('Procedimento', 'FilteredSelectMultiple', 'Exame Clínico'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Intervenção cadastrada com sucesso.')
    intervencao = PlanoTratamento.objects.get(atendimento=atendimento, dente='11', face='A_V_11')
    assert intervencao.procedimento.denominacao == 'Exame Clínico', 'a UI disse que cadastrou, mas a intervenção não persistiu'

    tela.clicar_aba('Plano de Tratamento')
    plano_na_tela = tela.aba('Plano de Tratamento')
    plano_na_tela.linha('11').selecionar_item('11')
    plano_na_tela.preencher('Ação', 'Lista', 'Remover').clicar_botao('Aplicar')
    tela.sucesso('Intervenção excluída com sucesso.')
    assert not PlanoTratamento.objects.filter(pk=intervencao.pk).exists(), 'a UI disse que removeu, mas a intervenção permanece'

    tela_tecnico = Tela(logado_saude('tecnico_saude_bucal')).ir(ADICIONAR_PROCEDIMENTO.format(atendimento.pk))
    tela_tecnico.preencher_formulario(
        [
            ('Procedimento', 'FilteredSelectMultiple', 'Aplicação Tópica de Flúor'),
            ('Região Bucal', 'Lista', 'S1'),
            ('Observações', 'TextArea', 'Procedimento realizado pelo técnico E2E'),
        ]
    )
    # A tela do procedimento não tem template próprio: cai no `djtools/templates/default.html`,
    # cujo `render_form` de um `FormPlus` rotula o submit como "Enviar" (não é ModelForm).
    tela_tecnico.clicar_botao('Enviar').sucesso('Procedimento registrado com sucesso.')
    procedimento_tecnico = ProcedimentoOdontologico.objects.get(atendimento=atendimento, observacao='Procedimento realizado pelo técnico E2E')
    assert procedimento_tecnico.profissional.username == '111010', 'a UI disse que salvou, mas não vinculou o procedimento ao técnico'

    # A exclusão é do Odontólogo e só sobre o próprio procedimento: o `group_required` da view
    # não inclui o Técnico, e o template só desenha o ícone para o dono da linha. Quem exclui
    # aqui é o odontólogo, sobre o procedimento que ele mesmo registrou na execução do plano.
    tela.ir(ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)).clicar_aba('Procedimentos')
    tela.aba('Procedimentos').linha('Execução odontológica E2E').clicar_icone('remoção')
    tela.sucesso('Procedimento excluído com sucesso.')
    assert not ProcedimentoOdontologico.objects.filter(pk=procedimento_executado.pk).exists(), 'a UI disse que excluiu, mas o procedimento permanece'

    tela.ir(ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)).clicar_aba('Procedimentos')
    tela.clicar_botao('Informar Tipo de Consulta')
    expect(tela.pagina).to_have_url(re.compile(rf'{ALTERAR_TIPO_CONSULTA.format(atendimento.pk)}$'))
    tela.preencher('Tipos de Consulta', 'FilteredSelectMultiple', 'Avaliação Clínica Inicial')
    tela.clicar_botao('Salvar').sucesso('Tipo de consulta alterado com sucesso.')
    odontograma.refresh_from_db()
    assert odontograma.tipo_consulta.filter(descricao='Avaliação Clínica Inicial').exists(), 'a UI disse que salvou, mas o tipo não persistiu'

    tela.clicar_aba('Procedimentos').clicar_botao('Encaminhar à Enfermagem')
    tela.sucesso('Atendimento encaminhado à enfermagem com sucesso.')
    odontograma.refresh_from_db()
    assert odontograma.encaminhado_enfermagem, 'a UI disse que encaminhou, mas o odontograma não foi marcado'

    atendimento_origem = _ultimo_atendimento(TipoAtendimento.ENFERMAGEM_MEDICO)
    tela_enfermagem = Tela(logado_saude('tecnico_enfermagem')).ir(f'/saude/atendimento_medico_enfermagem/{atendimento_origem.pk}/')
    tela_enfermagem.clicar_aba('Intervenção de Enfermagem')
    tela_enfermagem.clicar_botao('Registrar Intervenção Realizada')
    tela_enfermagem.sucesso('A intervenção de enfermagem foi registrada com sucesso.')
    odontograma.refresh_from_db()
    assert odontograma.atendido, 'a UI disse que registrou, mas a intervenção odontológica continua pendente'
    assert odontograma.atendido_por_vinculo is not None, 'a intervenção foi concluída sem registrar o profissional'

    # Tela de relatório: o corpo só existe depois do GET com o filtro (como o de psicologia).
    tela.ir(RELATORIO_ODONTOLOGICO).ver_titulo('Relatórios de Atendimentos Odontológicos')
    tela.filtros().preencher_formulario([('Data Inicial', 'Data', '01/01/2019'), ('Data Final', 'Data', '31/01/2019')])
    tela.clicar_botao('Enviar')
    tela.ver_texto('Aluno Saúde')
    assert Atendimento.objects.filter(pk=atendimento.pk, tipo=TipoAtendimento.ODONTOLOGICO).exists(), (
        'o relatório abriu sem o atendimento criado pela UI'
    )

    tela.ir(ATENDIMENTO_ODONTOLOGICO.format(atendimento.pk)).clicar_link('Fechar')
    tela.preencher('Observação de Fechamento', 'TextArea', 'Tratamento odontológico E2E')
    tela.clicar_botao('Salvar').sucesso('Atendimento fechado com sucesso.')
    atendimento.refresh_from_db()
    assert atendimento.situacao == SituacaoAtendimento.FECHADO, 'a UI disse que fechou, mas o atendimento continua aberto'
