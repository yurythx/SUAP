"""Fluxo: registro de propriedade intelectual (modo 2).

O subdomínio PROPRIEDADE INTELECTUAL é o menor do `pesquisa` em cenários, e é inteiramente
operado pelo **Diretor de Pesquisa**. São duas telas do admin: o cadastro do registro (patente,
software, desenho industrial) e o termo de cessão que o formaliza.

O que este arquivo pega: o ``Autocomplete`` do campo ``Tipo`` — que só tem opções porque o seed
cria as três ``PropriedadeIntelectual`` do behave (``Patente``, ``Software``, ``Desenho
Industrial``) —, a unicidade de ``numero_processo`` (o teste roda sobre banco reusado, e o
cadastro é limpo por esse número na entrada da sessão) e o upload do termo de cessão, que é
``PrivateFileField``.

Os dois cenários são uma cadeia: o segundo abre o registro que o primeiro criou.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A feature 016 não fixa data; a sessão congela em DATA_BASE (01/01/2018) e a data digitada no
# formulário é a do cenário (26/01/2024), como a `.feature` escreve.
DATA = '01/01/2018'

LISTAGEM = '/admin/pesquisa/registropropriedadeintelectual/'
FORMULARIO = '/admin/pesquisa/registropropriedadeintelectual/add/'

# O título é longo de propósito: é com ele que o cenário 2 afirma a tela de detalhe.
TITULO_PI = 'PROCESSO DE PRODUÇÃO DE BISCOITO TIPO COOKIE À BASE DE PÓLEN APÍCOLA'
NUMERO_PROCESSO = 'BR1020240016033'


def test_cadastro_do_registro_de_propriedade_intelectual(logado_pesquisa):
    """O Diretor de Pesquisa cadastra um registro de PI com os cinco campos do cenário.

    A asserção é dupla e cobre o que a mensagem não cobre: o registro persistiu **com o tipo**
    (o ``Autocomplete`` é o campo que a `Tela` precisa resolver pelo ``select2``, e um
    preenchimento que não escolhe a opção deixa a FK nula e o formulário recusa).
    """
    from pesquisa.models import RegistroPropriedadeIntelectual

    tela = Tela(logado_pesquisa('diretor')).ir(FORMULARIO)
    tela.ver_titulo('Adicionar Registro propriedade intelectual')

    tela.preencher_formulario(
        [
            ('Título', 'Texto', TITULO_PI),
            ('Nº do Pedido/processo', 'Texto', NUMERO_PROCESSO),
            ('Tipo', 'Autocomplete', 'Patente'),
            ('Nº da primeira RPI', 'Texto', '2770'),
            ('Data do Depósito', 'Data', '26/01/2024'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Registro cadastrado com sucesso.')
    registro = RegistroPropriedadeIntelectual.objects.filter(numero_processo=NUMERO_PROCESSO).first()
    assert registro is not None, 'a UI disse que cadastrou, mas o registro não persistiu'
    assert registro.tipo is not None, 'a UI disse que cadastrou, mas o tipo ficou vazio'
    assert registro.tipo.descricao == 'Patente', f'a UI disse que cadastrou, mas o tipo gravou {registro.tipo.descricao!r}'
    assert registro.data.strftime('%d/%m/%Y') == '26/01/2024', f'a UI disse que cadastrou, mas a data gravou {registro.data:%d/%m/%Y}'


def test_visualizar_registro_de_propriedade_intelectual(logado_pesquisa):
    """O Diretor abre o registro e anexa o termo de cessão.

    O ``Título`` é lido da listagem pelo ícone de exibição — e a linha é recortada pelo número
    do processo, que é a chave única do registro: o título da `.feature` tem acento e
    parênteses, e o recorte por ele funcionaria, mas o número é o que identifica a linha sem
    ambiguidade quando houver mais de um registro.
    """
    from pesquisa.models import RegistroPropriedadeIntelectual

    tela = Tela(logado_pesquisa('diretor')).ir(LISTAGEM)
    tela.ver_titulo('Registros propriedades intelectuais')

    tela.linha(NUMERO_PROCESSO).clicar_icone('exibição')
    tela.ver_titulo(TITULO_PI)

    tela.clicar_botao('Adicionar Termo de Cessão')
    tela.preencher('Termo de Cessão (PDF)', 'Arquivo', 'termo_cessao.pdf')
    tela.clicar_botao('Salvar')

    tela.sucesso('Termo de cessão cadastrado com sucesso.')
    registro = RegistroPropriedadeIntelectual.objects.get(numero_processo=NUMERO_PROCESSO)
    registro.refresh_from_db()
    assert registro.termo_cessao, 'a UI disse que cadastrou, mas o termo de cessão não foi anexado'
