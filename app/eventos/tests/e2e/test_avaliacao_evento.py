"""Avaliação (deferimento) de um evento submetido (modo 2).

O deferimento é o portão do módulo: enquanto ele não acontece o evento não é gerenciável,
não aceita participante e não aparece na área pública. A regressão que este teste pega é a
do casamento avaliador↔evento — `Evento.pode_avaliar` (`eventos/models.py:1618`) exige que
o grupo do usuário esteja em `Dimensao.grupos_avaliadores_locais` **e** que o campus do
evento seja o do avaliador, e a aba "Aguardando minha aprovação" do admin
(`eventos/admin.py:322`) repete esse filtro. Quebrar um dos dois some com o evento da lista
em vez de dar erro.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/eventos/evento/'


def test_avaliador_local_defere_evento(logado_eventos, evento_submetido):
    """Defere pela ação "Avaliar → Deferir" da tela do evento, como o avaliador local."""
    from eventos.models import Evento

    tela = Tela(logado_eventos('avaliador')).ir(LISTAGEM)
    tela.ver_titulo('Eventos')
    tela.clicar_aba('Aguardando minha aprovação')
    tela.linha(evento_submetido.nome).clicar_icone('exibição')

    tela.ver_titulo(evento_submetido.nome)
    tela.ver_botao('Avaliar')
    tela.clicar_botao('Avaliar')
    tela.clicar_botao('Deferir')

    tela.sucesso('O evento foi deferido.')
    evento = Evento.objects.get(pk=evento_submetido.pk)
    assert (evento.deferido, evento.ativo) == (True, True), 'a UI disse que deferiu, mas não persistiu'
