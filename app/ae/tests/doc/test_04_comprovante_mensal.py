"""Capturas do envio e da validação do comprovante mensal de participação."""

from datetime import date

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_captura_comprovante_mensal(logado_ae, ae_fluxos, inscricao_deferida, django_db_blocker, capturar):
    """O aluno envia o comprovante pendente e o Serviço Social o valida."""
    from ae.models import ComprovanteParticipacao, Participacao

    programa = ae_fluxos['programas']['PAS']
    aluno = ae_fluxos['aluno']
    inscricao = inscricao_deferida(programa)
    with django_db_blocker.unblock():
        ComprovanteParticipacao.objects.filter(aluno=aluno).delete()
        participacao = Participacao.objects.create(
            programa=programa, aluno=aluno, inscricao=inscricao, data_inicio=date(2024, 5, 1), motivo_entrada='Doc comprovante'
        )
        # ponytail: a pendência nasce do comando mensal; aqui é criada direto para a captura.
        comprovante = ComprovanteParticipacao.objects.create(
            aluno=aluno,
            campus=programa.instituicao,
            programa=programa,
            participacao=participacao,
            tipo=ComprovanteParticipacao.TIPO_PAGAMENTO,
            mes='Maio',
            ano=2024,
        )

    tela = Tela(logado_ae('aluno')).ir('/ae/meus_comprovantes_mensais/').ver_titulo('Comprovantes Mensais Pendentes')
    capturar(tela.pagina, 'comprovantes-mensais-aluno')
    tela.clicar_botao('Enviar Documento').ver_titulo('Enviar Comprovante Mensal')
    capturar(tela.pagina, 'comprovante-mensal-envio')
    tela.preencher('Arquivo', 'arquivo', 'comprovante.png').clicar_botao('Salvar')
    tela.sucesso('Comprovante mensal cadastrado com sucesso.')

    tela = Tela(logado_ae('assistente_social')).ir(f'/admin/ae/comprovanteparticipacao/?q={aluno.matricula}')
    tela.ver_titulo('Comprovantes')
    capturar(tela.pagina, 'comprovantes-mensais-staff')
    tela.clicar_botao('Validar').sucesso('Comprovante mensal avaliado com sucesso.')
    assert ComprovanteParticipacao.objects.get(pk=comprovante.pk).valido
