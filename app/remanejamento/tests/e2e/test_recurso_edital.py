"""Fluxo: recurso **contra o edital** — o servidor questiona as regras antes das inscrições.

É o contraditório da publicação: acontece antes de existir inscrição, tem janela própria
(``inicio_recursos_edital``/``fim_recursos_edital``) e uma data separada para a divulgação da
resposta. Três regressões cobertas aqui:

* o atalho da página inicial (``index_infos``, ``views.py:70-72``) só aparece dentro da janela
  **e** com ``permite_recursos_contra_edital`` ligado — é o único caminho da UI até o
  formulário;
* a mesma tela (``visualizar_recurso_edital``) serve dois papéis com formulários diferentes:
  o coordenador responde, o autor apenas lê (``views.py:118-136``);
* a **data de divulgação** separa "respondido" de "visível":
  ``pode_exibir_resposta_recurso_edital`` (``models.py:1003``) libera a resposta ao servidor só
  a partir de ``resultado_recursos_edital`` — e sempre ao coordenador. Antecipar isso vaza a
  resposta antes da hora; atrasar esconde para sempre.
"""

import datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM_RECURSOS = '/admin/remanejamento/editalrecurso/'
RECURSO_EDITAL = '/remanejamento/recurso_edital/{}/'
VISUALIZAR_RECURSO = '/remanejamento/visualizar_recurso_edital/{}/'


def test_servidor_interpoe_recurso_ao_edital(logado_remanejamento, servidores, edital_em_recurso_ao_edital):
    """Entra pelo atalho da página inicial e protocola o recurso.

    A URL não é digitada de propósito: ``index_infos`` é quem decide que este servidor, hoje,
    pode recorrer deste edital — o cargo dele tem de estar entre os do edital e a janela tem de
    estar aberta (``models.py:174-178``).
    """
    from remanejamento.models import EditalRecurso

    tela = Tela(logado_remanejamento('candidato')).ir('/')
    tela.clicar_link(f'Recurso ao Edital {edital_em_recurso_ao_edital.titulo}')

    tela.ver_titulo(f'Recurso ao {edital_em_recurso_ao_edital.titulo}')
    assert tela.pagina.url.endswith(RECURSO_EDITAL.format(edital_em_recurso_ao_edital.pk)), (
        f'o atalho deveria levar ao recurso do edital, foi para {tela.pagina.url!r}'
    )
    texto = 'A exigência de tempo mínimo de exercício não consta da resolução citada.'
    tela.preencher('Recurso', 'textarea', texto)
    tela.clicar_botao('Enviar')

    tela.sucesso('Recurso cadastrado com sucesso')
    recurso = EditalRecurso.objects.filter(edital=edital_em_recurso_ao_edital, servidor=servidores['candidato']).last()
    assert recurso, 'a UI disse que cadastrou, mas o recurso não persistiu'
    assert recurso.recurso_texto == texto, f'o texto do recurso foi gravado como {recurso.recurso_texto!r}'
    assert not recurso.recurso_respondido, 'o recurso nasceu marcado como respondido'


def test_coordenador_responde_recurso_ao_edital(logado_remanejamento, servidores, edital_em_recurso_ao_edital):
    """Da listagem de recursos até a resposta, pelo ícone de exibição.

    ``EditalRecursoAdmin`` troca as colunas conforme o grupo (``admin.py:145-153``): a coluna
    "O recurso foi respondido?" só existe para o coordenador, e é por isso que a listagem é o
    ponto de partida.

    A conferência na tela é feita reabrindo o recurso, e não lendo aquela coluna: ela renderiza
    o booleano como ícone, sem texto nenhum (medido — a célula vem vazia em ``inner_text``), e
    afirmar sobre ela seria afirmar sobre o vazio.
    """
    from remanejamento.models import EditalRecurso

    recurso = EditalRecurso.objects.create(
        edital=edital_em_recurso_ao_edital,
        servidor=servidores['candidato'],
        recurso_texto='Peço revisão do critério de desempate.',
    )

    tela = Tela(logado_remanejamento('coordenador')).ir(LISTAGEM_RECURSOS)
    tela.ver_titulo('Recursos ao Edital')
    tela.linha(edital_em_recurso_ao_edital.titulo).clicar_icone('exibição')

    tela.ver_titulo(f'Recurso ao {edital_em_recurso_ao_edital.titulo}')
    assert tela.pagina.url.endswith(VISUALIZAR_RECURSO.format(recurso.pk)), f'o ícone deveria abrir o recurso, foi para {tela.pagina.url!r}'
    resposta = 'Recurso indeferido: o critério consta do item 4.2 do edital.'
    tela.preencher('Resposta', 'textarea', resposta)
    tela.clicar_botao('Enviar')

    tela.sucesso('Resposta ao Recurso cadastrada com sucesso')
    recurso.refresh_from_db()
    assert recurso.recurso_resposta == resposta, 'a UI disse que respondeu, mas a resposta não persistiu'
    assert recurso.recurso_respondido, 'a resposta foi gravada sem marcar o recurso como respondido'
    assert recurso.dh_resposta, 'a resposta foi gravada sem data/hora'
    tela.ir(VISUALIZAR_RECURSO.format(recurso.pk))
    tela.quadro('Resposta ao Recurso').ver_texto(resposta)


def test_resposta_ao_recurso_so_aparece_para_o_servidor_apos_a_data_divulgada(logado_remanejamento, servidores):
    """A mesma resposta, dois editais: visível depois da data de divulgação, oculta antes.

    Os dois casos moram no mesmo teste porque é o **par** que expressa a regra
    (``models.py:1003-1006``): afirmar só a versão visível passaria com a data ignorada, e
    afirmar só a oculta passaria com a resposta nunca exibida. O quadro "Resposta ao Recurso"
    do template (``visualizar_recurso_edital.html``) é renderizado sob esse mesmo ``if``.
    """
    from remanejamento.models import EditalRecurso
    from remanejamento.tests.e2e.conftest import criar_edital

    agora = datetime.datetime.now()
    resposta = 'Recurso deferido parcialmente.'
    recursos = {}
    for chave, deslocamento in (('divulgado', -1), ('sob_sigilo', 5)):
        edital = criar_edital(
            inicio_recursos_edital=agora - datetime.timedelta(days=10),
            fim_recursos_edital=agora - datetime.timedelta(days=2),
            resultado_recursos_edital=agora + datetime.timedelta(days=deslocamento),
        )
        recursos[chave] = EditalRecurso.objects.create(
            edital=edital,
            servidor=servidores['candidato'],
            recurso_texto='Peço revisão.',
            recurso_resposta=resposta,
            recurso_respondido=True,
            dh_resposta=agora,
        )

    tela = Tela(logado_remanejamento('candidato')).ir(VISUALIZAR_RECURSO.format(recursos['divulgado'].pk))
    tela.ver_texto('Resposta ao Recurso')
    tela.ver_texto(resposta)

    tela.ir(VISUALIZAR_RECURSO.format(recursos['sob_sigilo'].pk))
    tela.ver_texto('Texto do Recurso')
    assert resposta not in tela.pagina.locator('//main').inner_text(), 'a resposta apareceu antes da data de divulgação do resultado dos recursos'

    # Para o coordenador a data não vale: ele responde e revê a resposta a qualquer momento.
    tela = Tela(logado_remanejamento('coordenador')).ir(VISUALIZAR_RECURSO.format(recursos['sob_sigilo'].pk))
    tela.ver_texto(resposta)
