"""Fluxo: cadastro do edital de Remoção Interna pela tela do admin (o "001" deste módulo).

É a porta de entrada de todo o processo: sem edital não há inscrição, resultado nem
homologação. O que este arquivo pega em regressão:

* o formulário do edital tem **12 marcos temporais** em ``input[type=datetime-local]``
  (``DateTimeFieldPlus``) e três validações cruzadas de data em ``EditalForm``
  (``forms.py:244-260``); qualquer uma que passe a rejeitar o caso feliz trava o módulo
  inteiro na primeira tela;
* ``Categoria`` amarra o cargo permitido (``clean_cargos``, ``forms.py:262``): categoria
  Docente só aceita cargo com código iniciado em 707. O teste afirma os dois lados — o TAE
  passa, o Docente com cargo TAE é recusado com a mensagem que explica o porquê;
* o botão **Gerenciar** da listagem só aparece para quem é coordenador *daquele* edital
  (``admin.py:70``), e é o único caminho da UI para ``gerenciar_edital``.
"""

import datetime
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/remanejamento/edital/'
FORMULARIO = '/admin/remanejamento/edital/add/'
GERENCIAR = '/remanejamento/edital/{}/gerenciar/'


def _prazos(base: datetime.date) -> list[tuple[str, str, str]]:
    """A tabela de prazos do edital, escrita relativa a ``base`` e em ordem cronológica.

    Datas relativas e não fixas pela decisão 3 do ``conftest`` (o relógio não é congelado):
    um edital com prazos de 2020 nasceria encerrado e nenhuma das telas seguintes teria o que
    mostrar. ``data e hora`` é o tipo novo da ``Tela`` — ver a docstring de
    ``Tela._preencher_data_e_hora``.
    """

    def dia(delta: int) -> str:
        return (base + datetime.timedelta(days=delta)).strftime('%d/%m/%Y')

    return [
        ('Início dos Recursos ao Edital', 'data e hora', f'{dia(-20)} 08:00'),
        ('Fim dos Recursos ao Edital', 'data e hora', f'{dia(-19)} 18:00'),
        ('Resultado dos Recursos ao Edital', 'data e hora', f'{dia(-18)} 08:00'),
        ('Início das inscrições', 'data e hora', f'{dia(-1)} 08:00'),
        ('Fim das inscrições', 'data e hora', f'{dia(7)} 18:00'),
        ('Início dos recursos do resultado', 'data e hora', f'{dia(10)} 08:00'),
        ('Fim dos recursos do resultado', 'data e hora', f'{dia(15)} 18:00'),
        ('Resultado dos recursos', 'data e hora', f'{dia(16)} 08:00'),
        ('Resultado Parcial', 'data e hora', f'{dia(9)} 08:00'),
        ('Resultado Final', 'data e hora', f'{dia(16)} 08:00'),
        ('Homologação do Resultado Final', 'data e hora', f'{dia(20)} 08:00'),
    ]


def test_cadastra_edital_tae_e_o_gerencia(logado_remanejamento, servidores):
    """Cadastra o edital pela tela e chega à tela de gerenciamento por onde a UI leva.

    O título leva ``uuid4`` porque a suíte não dá flush e o CI usa ``--reuse-db``: nome fixo
    encontraria o registro da execução anterior (armadilha 8).
    """
    from remanejamento.models import Edital

    titulo = f'E2E Remoção Interna {uuid4().hex[:8]}'
    tela = Tela(logado_remanejamento('coordenador')).ir(LISTAGEM)
    tela.ver_titulo('Editais')
    tela.ver_botao('Adicionar Edital')
    tela.ir(FORMULARIO)

    tela.preencher_formulario(
        [
            ('Categoria', 'lista', 'Técnico-Administrativo em Educação'),
            ('Título', 'texto', titulo),
            ('Descrição', 'textarea', 'Edital cadastrado pelo e2e do remanejamento.'),
            ('Campi', 'filteredselectmultiple', 'A0, B0'),
            ('Cargos', 'autocomplete multiplo', 'Assistente e2e'),
            ('Coordenadores', 'autocomplete multiplo', servidores['coordenador'].matricula),
            ('Chave hash', 'texto', uuid4().hex),
            *_prazos(datetime.date.today()),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso')
    edital = Edital.objects.filter(titulo=titulo).first()
    assert edital, 'a UI disse que salvou, mas o edital não persistiu'
    assert edital.categoria == Edital.TAE, f'categoria gravada errada: {edital.categoria!r}'
    assert sorted(edital.campus.values_list('sigla', flat=True)) == ['A0', 'B0'], 'os campi do FilteredSelectMultiple não foram gravados'
    assert edital.coordenadores.filter(username=servidores['coordenador'].matricula).exists(), 'o coordenador não foi vinculado'

    # A listagem é o único caminho da UI para o gerenciamento, e o botão só existe para quem
    # coordena o edital (`admin.py:70`).
    tela.ir(LISTAGEM)
    tela.linha(titulo).ver_botao('Gerenciar')

    # A aba "Edital" precisa de clique: `gerenciar_edital` (`views.py:192`) põe `tab='inscricoes'`
    # no contexto sempre que o formulário de filtro valida — e ele valida em GET, porque todos os
    # campos são opcionais. A aba inicial, portanto, é a de Inscrições, não a primeira do HTML.
    tela.ir(GERENCIAR.format(edital.pk))
    tela.ver_texto(titulo)
    tela.clicar_aba('Edital')
    tela.quadro('Vagas').ver_texto('Nenhum cargo adicionado.')


def test_edital_docente_recusa_cargo_fora_da_carreira_ebtt(logado_remanejamento, servidores):
    """Categoria Docente com cargo TAE é recusada, dizendo quais cargos remover.

    ``EditalForm.clean_cargos`` (``forms.py:262-278``) exige código iniciado em 707 — o
    identificador SIAPE da carreira EBTT. É a única regra de negócio do formulário do edital, e
    quebrá-la deixaria um edital docente aceitar inscrição de técnico.
    """
    from remanejamento.models import Edital

    titulo = f'E2E Remoção Interna docente inválido {uuid4().hex[:8]}'
    tela = Tela(logado_remanejamento('coordenador')).ir(FORMULARIO)
    tela.preencher_formulario(
        [
            ('Categoria', 'lista', 'Docente'),
            ('Título', 'texto', titulo),
            ('Descrição', 'textarea', 'Edital docente com cargo TAE — deve ser recusado.'),
            ('Campi', 'filteredselectmultiple', 'A0'),
            ('Cargos', 'autocomplete multiplo', 'Assistente e2e'),
            ('Coordenadores', 'autocomplete multiplo', servidores['coordenador'].matricula),
            ('Chave hash', 'texto', uuid4().hex),
            *_prazos(datetime.date.today()),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.erro('apenas são permitidos cargos cujo código inicia com 707')
    assert not Edital.objects.filter(titulo=titulo).exists(), 'a validação recusou na tela, mas o edital foi gravado assim mesmo'
