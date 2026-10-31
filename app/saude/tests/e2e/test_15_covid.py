"""Fluxo do passaporte vacinal da COVID, dos testes e das notificações (modo 2).

O passaporte tem dois lados: a declaração do vínculo e a validação do profissional, que mora
no admin (`/admin/saude/passaportevacinalcovid/`) junto com o histórico e os resultados de
teste. As notificações seguem o mesmo desenho no admin (`/admin/saude/notificacaocovid/`), e os
relatórios fecham o ciclo — inclusive o de chefia, restrito ao grupo `Chefe de Setor`.

ACHADO DE PRODUTO (candidato a issue): `passaporte_vacinacao_covid.html` não renderiza o
formulário de autodeclaração — o `{% if form %}` só traz o alerta do RN+Vacina —, então a
declaração não pode ser preenchida pela tela. Por isso o substrato deste arquivo é montado
pelo domínio, e a tela é coberta pelo que ela de fato mostra.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import PassaporteVacinalCovid

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PASSAPORTE = '/saude/passaporte_vacinacao_covid/'
DEFERIR_PASSAPORTE = '/saude/deferir_passaporte_vacinal/{}/'
INDEFERIR_PASSAPORTE = '/saude/indeferir_passaporte_vacinal/{}/'
CADASTRAR_CARTAO = '/saude/cadastrar_cartao_vacinal_covid/'
RESULTADOS_TESTES = '/saude/resultados_testes_covid/{}/'
DEFERIR_TESTE = '/saude/deferir_teste_covid/{}/'
INDEFERIR_TESTE = '/saude/indeferir_teste_covid/{}/'
HISTORICO_VALIDACAO = '/saude/ver_historico_validacao_passaporte/{}/'
RELATORIO_PASSAPORTE = '/saude/relatorio_passaporte_vacinal/'
RELATORIO_VACINACAO = '/saude/relatorio_vacinacao_covid/'
RELATORIO_CHEFIA = '/saude/relatorio_passaporte_vacinal_chefia/'
RELATORIO_NOTIFICACAO = '/saude/relatorio_notificacao_covid/'
MONITORAR_NOTIFICACAO = '/saude/monitorar_notificacao_covid/{}/'
VER_MONITORAMENTOS = '/saude/ver_monitoramentos_covid/{}/'
VERIFICACAO = '/saude/verificacao_passaporte_vacinal/'

PASSAPORTE_ADMIN = '/admin/saude/passaportevacinalcovid/'
NOTIFICACAO_ADMIN = '/admin/saude/notificacaocovid/'

ARQUIVO = 'upload/saude/prontuario/arquivo.pdf'


def _aluno_e_passaporte() -> tuple[object, PassaporteVacinalCovid]:
    """Cria (ou reusa) a autodeclaração do aluno, que a tela não oferece para preencher."""
    from datetime import datetime

    from edu.models import Aluno
    from saude.models import HistoricoValidacaoPassaporte, PassaporteVacinalCovid

    aluno = Aluno.objects.get(matricula='20191101011111')
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    # A suíte não dá flush: sem limpar o histórico, a validação desta execução soma com a anterior.
    HistoricoValidacaoPassaporte.objects.filter(passaporte__vinculo=vinculo).delete()
    passaporte, _ = PassaporteVacinalCovid.objects.update_or_create(
        vinculo=vinculo,
        defaults={
            'uo': aluno.curso_campus.diretoria.setor.uo,
            'situacao_declaracao': PassaporteVacinalCovid.AGUARDANDO_VALIDACAO,
            'situacao_passaporte': PassaporteVacinalCovid.INVALIDO,
            'termo_aceito_em': datetime(2019, 1, 21, 8, 0),
            'avaliada_por': None,
            'avaliada_em': None,
            'justificativa_indeferimento': None,
            # A execução anterior deixa o passaporte com cartão anexado; sem zerar, o deferimento
            # o tornaria válido e o teste seguinte leria o estado da run anterior.
            'cartao_vacinal': None,
            'cartao_vacinal_cadastrado_em': None,
            'atestado_medico': None,
            'possui_atestado_medico': None,
            'recebeu_alguma_dose': None,
        },
    )
    return aluno, passaporte


def _criar_resultado_teste(passaporte: PassaporteVacinalCovid) -> object:
    """Cria um resultado de teste aguardando validação, com o arquivo que a lista exibe."""
    from datetime import datetime

    from saude.models import ResultadoTesteCovid

    return ResultadoTesteCovid.objects.create(
        passaporte=passaporte,
        arquivo=ARQUIVO,
        realizado_em=datetime(2019, 1, 21, 9, 0),
    )


def _criar_notificacao() -> object:
    """Cria a notificação da Covid do aluno, que nenhuma tela do módulo oferece para preencher."""
    from datetime import date

    from edu.models import Aluno
    from saude.models import NotificacaoCovid

    aluno = Aluno.objects.get(matricula='20191101011111')
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    NotificacaoCovid.objects.filter(vinculo=vinculo).delete()
    return NotificacaoCovid.objects.create(
        vinculo=vinculo,
        uo=aluno.curso_campus.diretoria.setor.uo,
        situacao='Suspeito sintomático',
        data_inicio_sintomas=date(2019, 1, 21),
    )


def test_passaporte_vacinal_do_aluno_e_validacao_no_admin(logado_saude: Callable[[str], Page]) -> None:
    """O aluno vê o passaporte; o médico defere, vê o histórico, indefere e o aluno anexa o cartão."""
    aluno = Tela(logado_saude('aluno'))

    from saude.models import HistoricoValidacaoPassaporte, PassaporteVacinalCovid

    _vinculo, passaporte = _aluno_e_passaporte()
    aluno.ir(PASSAPORTE).ver_titulo('Passaporte Vacinal da COVID')
    aluno.ver_texto('Autodeclaração para o Passaporte Vacinal da COVID')

    medico = Tela(logado_saude('medico'))
    medico.ir(PASSAPORTE_ADMIN).ver_texto('Aluno Saúde')
    expect(medico.linha('Aluno Saúde').botao('Deferir')).to_have_attribute('href', DEFERIR_PASSAPORTE.format(passaporte.pk))
    medico.linha('Aluno Saúde').clicar_botao('Deferir')
    medico.sucesso('Passaporte vacinal avaliado com sucesso.')
    passaporte.refresh_from_db()
    assert passaporte.situacao_declaracao == PassaporteVacinalCovid.DEFERIDA, 'a UI disse que deferiu, mas a declaração não mudou'
    assert passaporte.situacao_passaporte == PassaporteVacinalCovid.INVALIDO, (
        'sem dose, atestado ou cartão, o passaporte deferido tem de continuar inválido'
    )
    assert HistoricoValidacaoPassaporte.objects.filter(passaporte=passaporte).count() == 1, 'a validação precisa gerar o histórico'

    # O histórico é o popup da linha, e a única leitura que existe do registro de validação.
    medico.ir(PASSAPORTE_ADMIN)
    expect(medico.linha('Aluno Saúde').botao('Ver Histórico')).to_have_attribute('href', HISTORICO_VALIDACAO.format(passaporte.pk))
    medico.linha('Aluno Saúde').clicar_botao('Ver Histórico')
    medico.popup().ver_texto('Deferida').ver_texto('Situação do Passaporte')

    medico.ir(PASSAPORTE_ADMIN)
    expect(medico.linha('Aluno Saúde').botao('Indeferir')).to_have_attribute('href', INDEFERIR_PASSAPORTE.format(passaporte.pk))
    medico.linha('Aluno Saúde').clicar_botao('Indeferir')
    medico.preencher('Justificativa para o Indeferimento', 'TextArea', 'Justificativa do indeferimento E2E')
    medico.clicar_botao('Enviar').sucesso('Passaporte vacinal avaliado com sucesso.')
    passaporte.refresh_from_db()
    assert passaporte.situacao_declaracao == PassaporteVacinalCovid.INDEFERIDA, 'a UI disse que indeferiu, mas a declaração não mudou'
    assert passaporte.justificativa_indeferimento == 'Justificativa do indeferimento E2E', 'a justificativa não persistiu'

    # Com o passaporte inválido, o aluno pode anexar o cartão vacinal da Covid.
    aluno.ir(PASSAPORTE).clicar_botao('Cadastrar Cartão Vacinal Covid-19')
    expect(aluno.pagina).to_have_url(re.compile(rf'{CADASTRAR_CARTAO}$'))
    aluno.preencher('Cartão Vacinal Covid-19', 'Arquivo', 'arquivo.pdf')
    # A senha é o campo de confirmação do djtools (`PasswordField` → `PasswordInput`): o rótulo
    # não é irmão do input, então o alvo é o próprio campo.
    aluno.loc('//input[@name="senha"]').fill(SENHA_E2E)
    aluno.clicar_botao('Salvar').sucesso('Cartão vacinal Covid-19 cadastrado com sucesso.')
    passaporte.refresh_from_db()
    assert passaporte.cartao_vacinal, 'a UI disse que cadastrou, mas o cartão vacinal não persistiu'
    assert passaporte.situacao_declaracao == PassaporteVacinalCovid.AGUARDANDO_VALIDACAO, 'o cartão devolve a declaração para validação'


def test_resultados_de_testes_covid(logado_saude: Callable[[str], Page]) -> None:
    """O médico defere e indefere os resultados de teste que o aluno anexou ao passaporte."""
    medico = Tela(logado_saude('medico'))

    from saude.models import PassaporteVacinalCovid, ResultadoTesteCovid

    _vinculo, passaporte = _aluno_e_passaporte()
    deferido = _criar_resultado_teste(passaporte)
    indeferido = _criar_resultado_teste(passaporte)

    medico.ir(PASSAPORTE_ADMIN)
    expect(medico.linha('Aluno Saúde').botao('Ver Resultados dos Testes')).to_have_attribute('href', RESULTADOS_TESTES.format(passaporte.pk))
    medico.linha('Aluno Saúde').clicar_botao('Ver Resultados dos Testes')
    expect(medico.pagina).to_have_url(re.compile(rf'{RESULTADOS_TESTES.format(passaporte.pk)}$'))
    medico.ver_titulo('Resultados de Testes Covid')

    # O resultado realizado agora vale 72h: deferido, ele torna o passaporte válido. As duas
    # linhas mostram o mesmo estado, então o alvo é a âncora do resultado específico.
    expect(medico.loc(f'//a[@href="{DEFERIR_TESTE.format(deferido.pk)}"]')).to_be_visible()
    medico.loc(f'//a[@href="{DEFERIR_TESTE.format(deferido.pk)}"]').click()
    medico.sucesso('Resultado do teste avaliado com sucesso.')
    deferido.refresh_from_db()
    passaporte.refresh_from_db()
    assert deferido.situacao == ResultadoTesteCovid.DEFERIDO, 'a UI disse que deferiu, mas o resultado não mudou'
    assert passaporte.situacao_passaporte == PassaporteVacinalCovid.VALIDO, 'o teste deferido dentro de 72h torna o passaporte válido'

    medico.ir(RESULTADOS_TESTES.format(passaporte.pk))
    expect(medico.loc(f'//a[@href="{INDEFERIR_TESTE.format(indeferido.pk)}"]')).to_be_visible()
    medico.loc(f'//a[@href="{INDEFERIR_TESTE.format(indeferido.pk)}"]').click()
    medico.preencher('Justificativa para o Indeferimento', 'TextArea', 'Teste indeferido E2E')
    medico.clicar_botao('Enviar').sucesso('Resultado do teste avaliado com sucesso.')
    indeferido.refresh_from_db()
    passaporte.refresh_from_db()
    assert indeferido.situacao == ResultadoTesteCovid.INDEFERIDO, 'a UI disse que indeferiu, mas o resultado não mudou'
    assert passaporte.situacao_passaporte == PassaporteVacinalCovid.INVALIDO, 'o teste indeferido invalida o passaporte'


def test_notificacao_covid_monitoramento_e_relatorio(logado_saude: Callable[[str], Page]) -> None:
    """O médico monitora a notificação da Covid e o relatório monta o gráfico das situações."""
    medico = Tela(logado_saude('medico'))

    from saude.models import MonitoramentoCovid, NotificacaoCovid

    notificacao = _criar_notificacao()
    medico.ir(NOTIFICACAO_ADMIN).ver_texto('Aluno Saúde')
    expect(medico.linha('Aluno Saúde').botao('Monitorar')).to_have_attribute('href', MONITORAR_NOTIFICACAO.format(notificacao.pk))
    medico.linha('Aluno Saúde').clicar_botao('Monitorar')
    medico.preencher_formulario([('Situação', 'Lista', 'Suspeito em monitoramento'), ('Monitoramento', 'TextArea', 'Monitoramento E2E')])
    medico.clicar_botao('Salvar').sucesso('Notificação de Síndromes Gripais e Covid-19 monitorada com sucesso.')
    assert MonitoramentoCovid.objects.filter(notificacao=notificacao, situacao='Suspeito em monitoramento').exists(), (
        'a UI disse que monitorou, mas o monitoramento não persistiu'
    )
    notificacao.refresh_from_db()
    assert notificacao.monitoramento == 'Suspeito em monitoramento', 'a situação do monitoramento não voltou para a notificação'
    assert notificacao == NotificacaoCovid.objects.get(pk=notificacao.pk)

    medico.ir(NOTIFICACAO_ADMIN)
    expect(medico.linha('Aluno Saúde').botao('Ver Monitoramentos')).to_have_attribute('href', VER_MONITORAMENTOS.format(notificacao.pk))
    medico.linha('Aluno Saúde').clicar_botao('Ver Monitoramentos')
    medico.ver_titulo('Monitoramentos da Notificação').ver_texto('Monitoramento E2E')

    medico.ir(RELATORIO_NOTIFICACAO).ver_titulo('Relatório de Notificações da Covid-19')
    medico.clicar_botao('Enviar')
    medico.ver_texto('Sem monitoramento').ver_texto('Suspeito em monitoramento')
    expect(medico.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()


def _passaporte_do_servidor_do_czn() -> None:
    """Dá ao coordenador (setor CZN) um passaporte, que é o que o relatório de chefia lista."""
    from rh.models import Servidor
    from saude.models import PassaporteVacinalCovid

    servidor = Servidor.objects.get(matricula='111001')
    vinculo = servidor.get_vinculo()
    assert vinculo is not None, 'o servidor sintético não possui vínculo'
    PassaporteVacinalCovid.objects.update_or_create(
        vinculo=vinculo,
        defaults={
            'uo': servidor.setor.uo,
            'situacao_declaracao': PassaporteVacinalCovid.AGUARDANDO_VALIDACAO,
            'situacao_passaporte': PassaporteVacinalCovid.INVALIDO,
        },
    )


def test_relatorios_do_passaporte_e_verificacao(logado_saude: Callable[[str], Page]) -> None:
    """Os relatórios de passaporte (campus e chefia) e a verificação pública listam o registro."""
    medico = Tela(logado_saude('medico'))

    from saude.models import PassaporteVacinalCovid

    _vinculo, passaporte = _aluno_e_passaporte()
    _passaporte_do_servidor_do_czn()
    assert passaporte.situacao_passaporte == PassaporteVacinalCovid.INVALIDO

    medico.ir(RELATORIO_PASSAPORTE).ver_titulo('Relatório de Passaporte Vacinal de COVID')
    medico.clicar_botao('Enviar')
    medico.ver_texto('Passaportes vacinais encontrados').ver_texto('Aluno Saúde')

    # O relatório de vacinação é só de gráficos (não lista nomes).
    medico.ir(RELATORIO_VACINACAO).ver_titulo('Relatório de Vacinação da COVID')
    medico.clicar_botao('Enviar')
    expect(medico.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()

    # O relatório de chefia responde pelos servidores do setor do chefe: o coordenador é do CZN.
    chefe = Tela(logado_saude('chefe_setor'))
    chefe.ir(RELATORIO_CHEFIA)
    chefe.clicar_botao('Enviar')
    chefe.ver_texto('Passaportes vacinais encontrados').ver_texto('CoordSaudeSistemico')

    verificador = Tela(logado_saude('verificador_passaporte'))
    verificador.ir(VERIFICACAO).ver_titulo('Verificar Passaporte Vacinal')
    # O campo de busca fica dentro do `.search-and-filters`, e ali o localizador por rótulo do
    # harness casa primeiro o `csrfmiddlewaretoken`; o alvo é o campo pelo nome.
    verificador.loc('//input[@name="nome"]').fill('Aluno Saúde')
    verificador.clicar_botao('Enviar')
    verificador.ver_texto('Aluno Saúde')
