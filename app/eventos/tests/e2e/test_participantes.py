"""Gestão de participantes de um evento deferido (modo 2).

Cobre o ciclo que o coordenador percorre depois do deferimento: cadastrar um participante
pelo popup e, com o evento já encerrado, confirmar presença, finalizar e disparar o
certificado. As duas regressões que este arquivo pega são de estado: a tela de participantes
só mostra os botões de ação quando `pode_gerenciar` e `eh_editavel` valem
(`eventos/templates/tabs/evento_participantes.html:17,120`), e o envio de certificado
depende de uma cadeia de guardas em `views.py:3092-3140` (evento realizado, presença
confirmada, carga horária) que falha em silêncio — devolvendo "Nenhum certificado foi
emitido." — quando qualquer elo cai.
"""

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_coordenador_adiciona_organizador(logado_eventos, evento_deferido):
    """Adiciona um organizador pelo popup da aba "Organizador"."""
    from eventos.models import Participante

    evento, tipo = evento_deferido
    nome = f'Participante {uuid4().hex[:8]}'

    tela = Tela(logado_eventos('coordenador')).ir(f'/eventos/evento/{evento.pk}/')
    tela.ver_titulo(evento.nome)
    tela.clicar_botao('Participantes')
    tela.ver_titulo(f'Participantes: {evento.nome}')

    tela.clicar_aba('Organizador')
    tela.aba('Organizador').clicar_botao('Adicionar')
    popup = tela.popup()
    # Âncora de espera antes de LER o formulário: `Tela.popup` só afirma que o `body` do
    # iframe está visível, e o body de um iframe recém-criado já está — sem uma asserção
    # com retry no meio, `rotulos_na_tela()` fotografa o documento ainda vazio e devolve [].
    popup.ver_botao('Salvar')
    # O `vejo os seguintes campos no formulário` do behave: os quatro rótulos que o teste
    # nomeia têm de estar no formulário do popup antes de qualquer preenchimento.
    rotulos = set(popup.rotulos_na_tela())
    assert {'Nome:', 'CPF:', 'E-mail:', 'Perfil:'} <= rotulos, f'formulário do popup sem os campos do cenário: {sorted(rotulos)}'
    popup.preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('CPF', 'texto', '268.058.310-83'),
            ('E-mail', 'texto', 'email@participante.com'),
            ('Perfil', 'autocomplete', 'Público Externo'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Organizador adicionado com sucesso.')
    assert Participante.objects.filter(evento=evento, tipo=tipo, nome=nome).exists(), 'a UI disse que salvou, mas não persistiu'


def test_confirma_presenca_finaliza_evento_e_envia_certificado(logado_eventos, evento_realizado_com_organizador):
    """Percorre confirmar inscrição (recusada) → confirmar presença → finalizar → certificado.

    Os quatro blocos são um cenário só e continuam um teste só: cada um só faz sentido sobre
    o estado que o anterior deixou. A primeira asserção é de **erro** de propósito — o
    participante já está com inscrição validada, e `views.py:3050` responde "Nenhuma
    inscrição confirmada." quando nada muda.
    """
    from eventos.models import Evento, Participante

    evento, _tipo, participante = evento_realizado_com_organizador
    participantes = f'/eventos/participantes/{evento.pk}/'

    tela = Tela(logado_eventos('coordenador')).ir(participantes)
    tela.ver_titulo(f'Participantes: {evento.nome}')

    tela.clicar_aba('Organizador')
    tela.aba('Organizador').selecionar_cartao(participante.nome)
    tela.aba('Organizador').clicar_botao('Confirmar inscrição')
    tela.erro('Nenhuma inscrição confirmada.')

    tela.ir(participantes).clicar_aba('Organizador')
    tela.aba('Organizador').selecionar_cartao(participante.nome)
    tela.aba('Organizador').clicar_botao('Confirmar presença')
    tela.sucesso('1 presença(s) confirmada(s) com sucesso.')
    assert Participante.objects.get(pk=participante.pk).presenca_confirmada, 'a UI disse que confirmou, mas não persistiu'

    tela.ir(f'/eventos/evento/{evento.pk}/')
    tela.ver_botao('Finalizar')
    tela.clicar_botao('Finalizar')
    tela.sucesso('O evento foi finalizado com sucesso.')
    assert Evento.objects.get(pk=evento.pk).finalizado, 'a UI disse que finalizou, mas não persistiu'

    tela.ir(participantes).clicar_aba('Organizador')
    tela.aba('Organizador').selecionar_cartao(participante.nome)
    tela.aba('Organizador').clicar_botao('Enviar certificado')
    tela.sucesso('1 E-mail(s) enviado(s) com sucesso.')
    assert Participante.objects.get(pk=participante.pk).certificado_enviado, 'a UI disse que enviou, mas não persistiu'
