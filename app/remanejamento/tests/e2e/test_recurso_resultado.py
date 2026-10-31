"""Fluxo: recurso **ao resultado** — o contraditório depois da classificação publicada.

Diferente do recurso ao edital, este mora dentro da própria inscrição: o mesmo
``/remanejamento/inscricao/<pk>/`` mostra formulário de recurso para o dono, formulário de
resposta para o coordenador e, a partir da data divulgada, a resposta para o dono
(``views.py:542-595``). Três regressões:

* ``pode_cadastrar_recurso`` (``models.py:1369``) exige quatro coisas ao mesmo tempo — ser o
  dono, a inscrição estar confirmada, a janela de recursos estar aberta e ainda não haver
  texto. Afrouxar qualquer uma abre recurso fora de prazo ou recurso em dobro;
* a **situação** do recurso nasce ``PENDENTE_DE_ANALISE`` e é o que a aba Recursos do
  gerenciamento usa para separar respondidos de não respondidos (``tabs/recursos.html``);
* a resposta só chega ao servidor a partir de ``resultado_recursos``
  (``pode_ver_resultado_recurso``, ``models.py:1356``) — e ao coordenador, sempre.
"""

import datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

INSCRICAO = '/remanejamento/inscricao/{}/'
EXCLUIR_RECURSO = '/remanejamento/inscricao/{}/excluir_recurso/'

TEXTO_RECURSO = 'Solicito revisão: meu tempo de exercício não considerou o período cedido.'
RESPOSTA_RECURSO = 'Recurso deferido: o período cedido foi incluído no cômputo.'


def test_servidor_interpoe_recurso_ao_resultado(logado_remanejamento, servidores, inscricao_em_periodo_de_recurso):
    """Entra pelo atalho da página inicial e protocola o recurso dentro do comprovante.

    O atalho vem de ``index_infos`` (``views.py:77-80``), que lista as inscrições do servidor
    em período de recurso **e sem recurso cadastrado** (``models.py:1447-1454``): é a mesma
    condição do formulário, e é por isso que o caminho é testado a partir dele, e não pela URL.
    """
    from remanejamento.models import Inscricao

    _edital, inscricao = inscricao_em_periodo_de_recurso
    tela = Tela(logado_remanejamento('candidato')).ir('/')
    tela.clicar_link(f'Recurso ao Resultado da Inscrição {inscricao}')

    tela.ver_titulo(f'Comprovante de Inscrição #{inscricao.pk}')
    tela.quadro('Cadastrar recurso').preencher('Texto do Recurso', 'textarea', TEXTO_RECURSO)
    tela.clicar_botao('Enviar')

    tela.sucesso('Recurso ao resultado cadastrado com sucesso')
    inscricao = Inscricao.objects.get(pk=inscricao.pk)
    assert inscricao.recurso_texto == TEXTO_RECURSO, 'a UI disse que cadastrou, mas o recurso não persistiu'
    assert inscricao.situacao_recurso == 'PENDENTE_DE_ANALISE', f'o recurso nasceu na situação {inscricao.situacao_recurso!r}'
    tela.quadro('Recurso cadastrado').ver_texto('Pendente de Análise')


def test_coordenador_responde_recurso_ao_resultado(logado_remanejamento, servidores, inscricao_em_periodo_de_recurso):
    """Responde o recurso pela aba Recursos do gerenciamento e define a situação.

    A resposta e a situação são um par: ``InscricaoRespostaRecursoForm`` grava os dois
    (``forms.py:461``) e a view carimba quem respondeu e quando (``views.py:566-568``). Deferir
    sem registrar o autor deixaria a decisão sem responsável.
    """
    from remanejamento.models import Inscricao

    _edital, inscricao = inscricao_em_periodo_de_recurso
    Inscricao.objects.filter(pk=inscricao.pk).update(recurso_texto=TEXTO_RECURSO, situacao_recurso='PENDENTE_DE_ANALISE')

    tela = Tela(logado_remanejamento('coordenador')).ir(INSCRICAO.format(inscricao.pk))
    tela.quadro('Recurso cadastrado').ver_texto(TEXTO_RECURSO)
    tela.quadro('Resposta ao recurso').preencher_formulario(
        [
            ('Resposta ao recurso', 'textarea', RESPOSTA_RECURSO),
            ('Situação do Recurso', 'lista', 'Deferido'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso('Resposta ao recurso do resultado parcial cadastrado com sucesso')
    inscricao = Inscricao.objects.get(pk=inscricao.pk)
    assert inscricao.avaliacao_recurso == RESPOSTA_RECURSO, 'a UI disse que respondeu, mas a resposta não persistiu'
    assert inscricao.situacao_recurso == 'DEFERIDO', f'a situação ficou {inscricao.situacao_recurso!r}'
    assert inscricao.recurso_respondido_por == servidores['coordenador'].get_vinculo(), 'a resposta foi gravada sem responsável'
    assert inscricao.recurso_respondido_em, 'a resposta foi gravada sem data/hora'


def test_resposta_ao_recurso_so_aparece_para_o_servidor_apos_a_data_divulgada(logado_remanejamento, servidores):
    """A mesma resposta, dois editais: visível depois de ``resultado_recursos``, oculta antes.

    O par no mesmo teste pelo mesmo motivo do recurso ao edital: afirmar só um dos lados
    passaria com a regra invertida. O quadro "Recurso cadastrado" mostra a resposta sob o
    ``if pode_ver_resultado_recurso`` (``inscricao.html``), e essa é a única diferença entre as
    duas telas.
    """
    from remanejamento.models import Inscricao
    from remanejamento.tests.e2e.conftest import configurar_vagas, criar_edital, criar_inscricao

    agora = datetime.datetime.now()
    inscricoes = {}
    for chave, deslocamento in (('divulgado', -1), ('sob_sigilo', 5)):
        edital = criar_edital(
            inicio_inscricoes=agora - datetime.timedelta(days=20),
            fim_inscricoes=agora - datetime.timedelta(days=10),
            data_resultado_parcial=agora - datetime.timedelta(days=5),
            inicio_recursos=agora - datetime.timedelta(days=4),
            fim_recursos=agora - datetime.timedelta(days=2),
            resultado_recursos=agora + datetime.timedelta(days=deslocamento),
        )
        configurar_vagas(edital)
        inscricao = criar_inscricao(edital, servidores['candidato'])
        Inscricao.objects.filter(pk=inscricao.pk).update(recurso_texto=TEXTO_RECURSO, avaliacao_recurso=RESPOSTA_RECURSO, situacao_recurso='DEFERIDO')
        inscricoes[chave] = inscricao

    tela = Tela(logado_remanejamento('candidato')).ir(INSCRICAO.format(inscricoes['divulgado'].pk))
    tela.quadro('Recurso cadastrado').ver_texto(RESPOSTA_RECURSO)

    tela.ir(INSCRICAO.format(inscricoes['sob_sigilo'].pk))
    tela.quadro('Recurso cadastrado').ver_texto(TEXTO_RECURSO)
    assert RESPOSTA_RECURSO not in tela.pagina.locator('//main').inner_text(), (
        'a resposta apareceu antes da data de divulgação do resultado dos recursos'
    )

    tela = Tela(logado_remanejamento('coordenador')).ir(INSCRICAO.format(inscricoes['sob_sigilo'].pk))
    tela.ver_texto(RESPOSTA_RECURSO)


def test_servidor_exclui_o_proprio_recurso(logado_remanejamento, servidores, inscricao_em_periodo_de_recurso):
    """Desfaz o recurso enquanto a janela está aberta, para poder reescrevê-lo.

    ``inscricao_excluir_recurso`` (``views.py:903``) **não tem link em template nenhum** — grep
    por ``excluir_recurso`` em ``remanejamento/templates/`` não retorna nada —, mas é rota
    registrada, exercitável por URL e governada por ``pode_excluir_recurso`` (``models.py:1386``,
    as mesmas quatro condições do cadastro, com o texto presente em vez de ausente). Por isso
    aqui se navega pela URL: não há botão a clicar, e é justamente esse o achado.

    Depois de excluir, o formulário de cadastro volta — é o fato positivo que prova que o
    servidor recuperou o direito de recorrer, e não apenas que o texto sumiu.
    """
    from remanejamento.models import Inscricao

    _edital, inscricao = inscricao_em_periodo_de_recurso
    Inscricao.objects.filter(pk=inscricao.pk).update(recurso_texto=TEXTO_RECURSO, situacao_recurso='PENDENTE_DE_ANALISE')

    tela = Tela(logado_remanejamento('candidato')).ir(INSCRICAO.format(inscricao.pk))
    tela.quadro('Recurso cadastrado').ver_texto(TEXTO_RECURSO)

    tela.ir(EXCLUIR_RECURSO.format(inscricao.pk))

    assert Inscricao.objects.get(pk=inscricao.pk).recurso_texto == '', 'a exclusão não apagou o texto do recurso'
    tela.quadro('Cadastrar recurso').ver_texto('Texto do Recurso')
