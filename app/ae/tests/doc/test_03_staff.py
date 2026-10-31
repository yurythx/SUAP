"""Capturas das telas de análise e participação do AE."""

from datetime import datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def _capturar_popup(tela: Tela, capturar, nome: str) -> None:
    """Espera o fade de abertura do fancybox terminar; sem isso o diálogo sai esmaecido."""
    tela.pagina.locator('.fancybox-slide--complete').wait_for()
    capturar(tela.pagina, nome)


def _inscricao_sem_parecer(ae_fluxos, programa):
    from ae.models import Inscricao, Participacao

    aluno = ae_fluxos['aluno']
    Participacao.objects.filter(aluno=aluno, programa=programa).delete()
    Inscricao.objects.filter(aluno=aluno, programa=programa).delete()
    return Inscricao.objects.create(
        aluno=aluno,
        programa=programa,
        periodo_inscricao=ae_fluxos['periodos'][programa.tipo_programa.sigla],
        data_cadastro=datetime(2024, 6, 3),
        motivo='Doc análise',
        ativa=True,
        situacao_parecer=Inscricao.SEM_PARECER,
    )


def test_captura_documentacao_e_parecer(logado_ae, ae_fluxos, django_db_blocker, capturar):
    """Valida a documentação pela lista de inscrições e registra o parecer."""
    from ae.models import Inscricao

    programa = ae_fluxos['programas']['ALM']
    matricula = ae_fluxos['aluno'].matricula
    with django_db_blocker.unblock():
        inscricao = _inscricao_sem_parecer(ae_fluxos, programa)

    tela = Tela(logado_ae('assistente_social')).ir(f'/admin/ae/inscricao/?programa={programa.pk}&q={matricula}')
    capturar(tela.pagina, 'inscricoes-lista')
    tela.selecionar_item(matricula)
    tela.preencher('Ação', 'lista', 'Validar documentação').clicar_acao('Aplicar')
    tela.ver_titulo('Validar documentação')
    capturar(tela.pagina, 'validar-documentacao-formulario')
    tela.preencher('Data', 'data', '03/06/2024').clicar_botao('Enviar')
    tela.sucesso('Documentação(ões) validada(s) com sucesso.')

    tela.clicar_botao('Adicionar Parecer').ver_texto('Parecer da Inscrição')
    capturar(tela.pagina, 'parecer-inscricao-formulario')
    tela.preencher_formulario(
        [('Situação do Parecer', 'lista', 'Deferido'), ('Parecer da Inscrição', 'textarea', 'Documentação conferida e critérios atendidos.')]
    ).clicar_botao('Salvar')
    tela.sucesso('Parecer cadastrado com sucesso.')
    assert Inscricao.objects.get(pk=inscricao.pk).situacao_parecer == Inscricao.DEFERIDO

    tela.ir(f'/ae/inscricao/{inscricao.pk}/').ver_titulo(f'Inscrição de {inscricao.aluno} para {inscricao.programa}')
    tela.ver_texto('Documentação conferida e critérios atendidos.')
    capturar(tela.pagina, 'inscricao-detalhe-staff')


def test_captura_participacoes(logado_ae, ae_fluxos, inscricao_deferida, capturar):
    """Inclui, abre a edição e finaliza a participação de uma inscrição deferida."""
    from ae.models import Participacao

    programa = ae_fluxos['programas']['ALM']
    matricula = ae_fluxos['aluno'].matricula
    inscricao = inscricao_deferida(programa)
    rota = f'/ae/gerenciar_participacao/{programa.pk}/'
    tela = Tela(logado_ae('assistente_social')).ir(f'/ae/programa/{programa.pk}/')
    tela.ver_titulo(f'Programa: {programa.titulo}').clicar_botao('Gerenciar Participações')
    tela.ver_titulo('Gerenciar Participações')
    capturar(tela.pagina, 'participacoes-lista')

    tela.cartao(matricula).clicar_link('Adicionar Participação')
    popup = tela.popup().ver_titulo('Adicionar Participação')
    popup.preencher_formulario(
        [
            ('Data de Entrada', 'data', '03/06/2024'),
            ('Motivo de Entrada', 'textarea', 'Inscrição deferida no edital.'),
            ('Almoço', 'checkbox multiplo', 'Segunda, Terça'),
            ('Categoria', 'autocomplete', 'AS'),
            ('Motivo do Atendimento', 'autocomplete', 'Aula no turno inverso'),
        ]
    )
    _capturar_popup(tela, capturar, 'participacao-adicionar')
    tela = popup.salvar_no_popup('Salvar')
    tela.sucesso('Participação adicionada com sucesso.')

    tela.ir(rota).cartao(matricula).clicar_link('Editar')
    tela.popup().ver_titulo('Editar Participação').preencher('Data de Saída', 'data', '14/06/2024')
    _capturar_popup(tela, capturar, 'participacao-editar')

    tela.ir(rota).cartao(matricula).clicar_link('Finalizar')
    popup = tela.popup().ver_titulo('Finalizar Participação')
    popup.preencher_formulario([('Data da Saída', 'data', '28/06/2024'), ('Motivo da Saída', 'textarea', 'Conclusão do curso.')])
    _capturar_popup(tela, capturar, 'participacao-finalizar')
    tela = popup.salvar_no_popup('Salvar')
    tela.sucesso('Participação finalizada com sucesso.')
    assert Participacao.objects.filter(inscricao=inscricao, data_termino__isnull=False).exists()
