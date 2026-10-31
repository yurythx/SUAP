"""Capturas da análise de inscrições por pontuação e da importação de caracterização."""

from datetime import datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAL_ENCERRADO = 'Doc edital com inscrições encerradas'
EDITAL_PROCESSO_SELETIVO = 'Doc Edital de ingresso 2024.1'


@pytest.fixture
def inscricao_em_edital_encerrado(ae_fluxos, caracterizacao_pronta, django_db_blocker):
    """Inscrição de Apoio à Formação Estudantil num edital cujo período terminou em maio.

    A geração da análise lê a matrícula no período, o turno e a última
    ``InscricaoCaracterizacao`` do aluno, que o seed do e2e não cria.
    """
    from ae.models import AnaliseInscricao, Edital, Inscricao, InscricaoCaracterizacao, InscricaoTrabalho, Participacao, PeriodoInscricao
    from comum.models import Ano
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo, Turno

    programa = ae_fluxos['programas']['TRB']
    aluno = ae_fluxos['aluno']
    with django_db_blocker.unblock():
        edital, _ = Edital.objects.get_or_create(descricao=EDITAL_ENCERRADO, defaults={'ativo': True})
        edital.tipo_programa.set([programa.tipo_programa])
        AnaliseInscricao.objects.filter(inscricao__periodo_inscricao__edital=edital).delete()
        Participacao.objects.filter(aluno=aluno, programa=programa).delete()
        Inscricao.objects.filter(aluno=aluno, programa=programa).delete()
        periodo = PeriodoInscricao.objects.filter(edital=edital, campus=programa.instituicao).first()
        if periodo is None:
            periodo = PeriodoInscricao.objects.create(
                edital=edital, campus=programa.instituicao, data_inicio=datetime(2024, 5, 1), data_termino=datetime(2024, 5, 31, 23, 59)
            )
        periodo.programa.set([programa])
        MatriculaPeriodo.objects.get_or_create(
            aluno=aluno,
            ano_letivo=Ano.objects.get(ano=2024),
            periodo_letivo=1,
            defaults={'situacao': SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)},
        )
        aluno.turno = Turno.objects.get(descricao='Matutino')
        aluno.save(update_fields=['turno'])
        InscricaoCaracterizacao.objects.get_or_create(aluno=aluno, defaults={'remuneracao_trabalho': 0})
        InscricaoTrabalho.objects.create(
            aluno=aluno,
            programa=programa,
            periodo_inscricao=periodo,
            data_cadastro=datetime(2024, 5, 10),
            motivo='Doc análise por pontuação',
            ativa=True,
            turno='Tarde',
            habilidades='Organização de eventos',
        )
    return programa


def test_captura_analise_de_inscricoes(logado_doc, ae_fluxos, inscricao_em_edital_encerrado, capturar):
    """Gera a análise do edital encerrado e mostra a lista de candidatos."""
    programa = inscricao_em_edital_encerrado
    tela = Tela(logado_doc('assistente_social')).ir('/ae/analise_inscricoes/').ver_titulo('Análise das Inscrições')
    tela.preencher_formulario([('Edital', 'autocomplete', EDITAL_ENCERRADO), ('Programa', 'lista', programa.titulo)])
    tela.clicar_botao('Enviar').ver_texto('A análise para o edital e programa selecionados ainda não foi gerada.')
    capturar(tela.pagina, 'analise-inscricoes-gerar')

    tela.clicar_botao('Gerar análise').ver_texto('Análises geradas com sucesso.')
    # O "Continuar" da página de processo mantém onclick=history.back(); o destino real está no href.
    continuar = tela.pagina.locator('a#button')
    continuar.wait_for()
    tela.ir(continuar.get_attribute('href')).ver_texto('Análise das inscrições').ver_texto(ae_fluxos['aluno'].matricula)
    capturar(tela.pagina, 'analise-inscricoes-lista')


@pytest.fixture
def edital_de_ingresso(django_db_blocker):
    from comum.models import Ano
    from processo_seletivo.models import Edital

    with django_db_blocker.unblock():
        Edital.objects.get_or_create(
            codigo=990001,
            defaults={
                'descricao': EDITAL_PROCESSO_SELETIVO,
                'ano': Ano.objects.get(ano=2024),
                'semestre': 1,
                'qtd_vagas': 0,
                'qtd_inscricoes': 0,
                'qtd_inscricoes_confirmadas': 0,
                'detalhamento_por_campus': '[]',
            },
        )


def test_captura_importacao_de_caracterizacao(logado_doc, ae_fluxos, edital_de_ingresso, capturar):
    """Importa a caracterização informada pelos candidatos de um edital de ingresso."""
    tela = Tela(logado_doc('coordenador')).ir('/ae/importar_caracterizacao_edital_ano/').ver_titulo('Importar Caracterização')
    tela.preencher_formulario([('Ano', 'lista', '2024'), ('Semestre', 'lista', '1')])
    capturar(tela.pagina, 'importar-caracterizacao-periodo')
    tela.clicar_botao('Continuar').preencher('Edital', 'autocomplete', EDITAL_PROCESSO_SELETIVO)
    capturar(tela.pagina, 'importar-caracterizacao-edital')
    # Sem webservice configurado no edital, nada é recebido; em produção o edital traz o endereço.
    tela.clicar_botao('Finalizar').sucesso('Número de caracterizações recebidas 0 e importadas 0')
