"""Fluxo: o coordenador confere e arbitra as inscrições antes do processamento.

Tudo o que acontece entre a inscrição e o resultado passa por aqui, e nada disso é opcional:
``processar_resultado`` recusa rodar enquanto houver inscrição confirmada sem validação nem
verificação de afastamento (``views.py:221`` + ``models.py:979``). São quatro telas, três
delas com efeito colateral permanente no cadastro do servidor.

O que este arquivo pega em regressão:

* **Validar** grava ``validado_por``/``validado_em`` **e**, quando a data de início de
  exercício é corrigida, cria um ``ServidorDataInicioExercicioRemocaoInterna``
  (``forms.py:669-678``) — o ajuste vale para editais futuros, não só para este. É o dado que
  decide a classificação por tempo de serviço;
* **Verificar licenças/afastamentos** transforma os ``ServidorAfastamento`` do SIAPE em
  ``ServidorAfastamentoRemocaoInterna`` validados, e é isso que desconta dias no processamento
  (``models.py:324-331``);
* **Inabilitar/Reabilitar** é o par que tira e devolve a inscrição da disputa, cada uma com o
  seu registro de motivo.

Três destas telas são abertas por URL e não pelo botão da listagem, e o motivo é técnico: só
``editar_inscricao_coordenador`` devolve ``httprr(..., close_popup=True)``
(``views.py:659``). ``inabilitar``, ``reabilitar`` e ``validar_afastamentos`` redirecionam
**dentro** do iframe do fancybox — clicá-las como popup deixaria o teste esperando um desfecho
que nunca chega (armadilha 15 ao contrário: não há o que sincronizar).
"""

import datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

GERENCIAR = '/remanejamento/edital/{}/gerenciar/'
INSCRICAO = '/remanejamento/inscricao/{}/'
EDITAR_INSCRICAO = '/remanejamento/inscricao/{}/editar/'
VALIDAR_AFASTAMENTOS = '/remanejamento/inscricao/{}/validar_afastamentos/'
INABILITAR = '/remanejamento/inscricao/{}/inabilitar/'
REABILITAR = '/remanejamento/inscricao/{}/reabilitar/'
IMPRIMIR = '/remanejamento/inscricao/{}/imprimir/'


def test_coordenador_valida_dados_da_inscricao(logado_remanejamento, servidores, edital_com_inscricoes_abertas):
    """Abre a validação pelo botão da listagem, corrige a data de exercício e valida.

    A data é alterada de propósito: é o único caminho que cria o
    ``ServidorDataInicioExercicioRemocaoInterna`` (o cadastro que o menu chama "Datas de
    Exercício Ajustadas"), e ele vale para **todos** os editais seguintes do servidor — um
    ajuste silenciosamente não gravado aqui reapareceria como classificação errada lá na
    frente.

    Este é o único popup do arquivo, porque é a única das quatro views que fecha o fancybox
    (``views.py:659``).
    """
    from remanejamento.models import Inscricao, ServidorDataInicioExercicioRemocaoInterna
    from remanejamento.tests.e2e.conftest import criar_inscricao, nome_na_listagem

    servidor = servidores['candidato']
    inscricao = criar_inscricao(edital_com_inscricoes_abertas, servidor)

    tela = Tela(logado_remanejamento('coordenador')).ir(GERENCIAR.format(edital_com_inscricoes_abertas.pk))
    linha = tela.linha(nome_na_listagem(servidor))
    linha.ver_texto('Pendente de validação')
    linha.clicar_botao('Validar')

    popup = tela.popup()
    popup.ver_texto(f'Inscrição de {servidor}')
    popup.preencher('Data de Início de Exercício', 'data', '01/01/2009')
    popup.salvar_no_popup('Validar e Salvar')

    tela.sucesso('Inscrição alterada com sucesso')
    inscricao.refresh_from_db()
    assert inscricao.validado_por == servidores['coordenador'].get_vinculo(), 'a UI disse que validou, mas a inscrição não registrou o validador'
    assert inscricao.validado_em, 'a validação não foi carimbada'
    ajuste = ServidorDataInicioExercicioRemocaoInterna.objects.filter(servidor=servidor).first()
    assert ajuste, 'a data corrigida não criou o ajuste de início de exercício do servidor'
    assert ajuste.data_inicio_exercicio == datetime.date(2009, 1, 1), f'o ajuste ficou com a data {ajuste.data_inicio_exercicio}'
    assert Inscricao.objects.get(pk=inscricao.pk).inicio_exercicio == datetime.date(2009, 1, 1), 'a inscrição ficou com a data antiga'

    tela.ir(GERENCIAR.format(edital_com_inscricoes_abertas.pk))
    tela.linha(nome_na_listagem(servidor)).ver_texto('Informações validadas em')


def test_coordenador_verifica_licencas_e_afastamentos(logado_remanejamento, servidores, inscricao_com_afastamento):
    """Confere o afastamento importado do SIAPE e o valida para efeito de desconto de tempo.

    A tela só lista afastamento que satisfaça os dois lados ao mesmo tempo: o edital tem de
    tê-lo marcado como ``desconta_exercicio`` e o servidor tem de tê-lo usufruído depois do
    início do exercício no cargo (``views.py:922-928``). Validar cria o
    ``ServidorAfastamentoRemocaoInterna`` com carimbo — é o registro que o processamento
    desconta, e sem o carimbo o desconto não acontece (``models.py:324``).
    """
    from remanejamento.models import ServidorAfastamentoRemocaoInterna
    from remanejamento.tests.e2e.conftest import nome_na_listagem

    edital, inscricao = inscricao_com_afastamento
    tela = Tela(logado_remanejamento('coordenador')).ir(VALIDAR_AFASTAMENTOS.format(inscricao.pk))
    tela.quadro('Afastamentos').ver_texto('Licença para capacitação (e2e)')

    tela.clicar_botao('Validar Afastamentos')

    tela.sucesso('Afastamentos do servidor validados com sucesso')
    inscricao.refresh_from_db()
    assert inscricao.licenca_afastamento_verificado_por == servidores['coordenador'].get_vinculo(), (
        'a UI disse que validou, mas a inscrição não registrou quem verificou'
    )
    validados = ServidorAfastamentoRemocaoInterna.objects.filter(inscricao=inscricao, validado_em__isnull=False)
    assert validados.count() == 1, f'esperava 1 afastamento validado, veio {validados.count()}'

    tela.ir(GERENCIAR.format(edital.pk))
    tela.linha(nome_na_listagem(servidores['candidato'])).ver_texto('Verificado em')


def test_coordenador_inabilita_e_reabilita_inscricao(logado_remanejamento, servidores, edital_com_inscricoes_abertas):
    """Tira a inscrição da disputa com motivo e depois a devolve — o par completo.

    Um teste só porque reabilitar sem inabilitar antes não existe: ``is_pode_inabilitar``
    governa os dois lados (``models.py:1418``) e o botão "Reabilitar" só aparece no quadro
    "Inscrições inabilitadas" (``tabs/inscricoes.html``). A inabilitação **desconfirma** a
    inscrição, e é essa mudança que a tira do processamento.
    """
    from remanejamento.tests.e2e.conftest import criar_inscricao, nome_na_listagem

    servidor = servidores['candidato']
    inscricao = criar_inscricao(edital_com_inscricoes_abertas, servidor)
    motivo = 'Servidor não atende ao tempo mínimo de exercício exigido no item 3.1.'

    tela = Tela(logado_remanejamento('coordenador')).ir(INABILITAR.format(inscricao.pk))
    tela.preencher('Motivo', 'textarea', motivo)
    tela.clicar_botao('Enviar')

    tela.sucesso('Inscrição inabilitada com sucesso')
    inscricao.refresh_from_db()
    assert inscricao.data_inapta, 'a UI disse que inabilitou, mas a inscrição não foi carimbada'
    assert not inscricao.confirmada, 'a inabilitação não desconfirmou a inscrição'
    assert inscricao.motivo_inapta == motivo, f'o motivo gravado foi {inscricao.motivo_inapta!r}'
    # O motivo é conferido no comprovante e não na listagem: o quadro "Inscrições inabilitadas"
    # nasce `class='collapsed'` (`tabs/inscricoes.html`) e a linha existe no DOM porém oculta —
    # afirmar sobre ela exigiria expandir o accordion, que não é o fato que interessa.
    tela.ir(INSCRICAO.format(inscricao.pk))
    tela.ver_texto(motivo)

    tela.ir(REABILITAR.format(inscricao.pk))
    tela.preencher('Observação', 'textarea', 'Documentação complementar apresentada dentro do prazo.')
    tela.clicar_botao('Enviar')

    tela.sucesso('Inscrição reabilitada com sucesso')
    inscricao.refresh_from_db()
    assert not inscricao.data_inapta, 'a UI disse que reabilitou, mas a inscrição continua inapta'
    assert inscricao.confirmada, 'a reabilitação não reconfirmou a inscrição'


def test_coordenador_imprime_a_avaliacao_por_assunto(logado_remanejamento, servidores, edital_com_inscricoes_abertas):
    """A versão para impressão da inscrição responde e traz os dados do inscrito.

    ``inscricao_imprimir`` (``views.py:890``) monta ``pode_imprimir`` com um ``or`` cujo último
    termo é ``inscricao.disciplina.avaliadores`` — que estoura em ``AttributeError`` quando não
    há disciplina. Só não estoura porque o coordenador satisfaz o termo anterior e o ``or``
    curto-circuita: é exatamente esse curto-circuito que este teste protege.
    """
    from remanejamento.tests.e2e.conftest import criar_inscricao

    inscricao = criar_inscricao(edital_com_inscricoes_abertas, servidores['candidato'])

    tela = Tela(logado_remanejamento('coordenador')).ir(IMPRIMIR.format(inscricao.pk))

    tela.ver_texto(edital_com_inscricoes_abertas.titulo)
    tela.ver_texto(str(servidores['candidato']))
