"""Fluxo: a lista telefônica institucional e a manutenção dos contatos de cada setor.

``/comum/telefones/`` é a lista telefônica do IFRN — a tela que qualquer pessoa da instituição
abre para achar o ramal de um setor, com exportação em CSV para quem precisa da planilha. As
outras três rotas deste arquivo são o lado de quem mantém esses dados: adicionar telefone, trocar
o e-mail do setor e remover um número.

A regressão que o arquivo pega tem duas metades. A primeira é a lista ficar vazia ou explodir —
ela varre todos os setores SUAP ativos com campus, e é a tela mais visitada por quem não usa o
SUAP para mais nada. A segunda é a guarda: as três telas de manutenção mudam dado institucional a
partir do ``pk`` na URL, e ``setor_remover_telefone`` apaga **por GET**, sem confirmação. Quem não
tem ``rh.pode_gerenciar_setor_telefone`` nem chefia o setor precisa levar 403 nas três.

Todos os fluxos que gravam usam ``setor_descartavel``, um setor criado e apagado pelo próprio
teste: mexer num setor de ``PAPEIS`` deixaria o ``Vinculo`` em cache dos usuários compartilhados
apontando para uma instância velha.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
TELEFONES = '/comum/telefones/'
TELEFONES_CSV = '/comum/telefones_csv/'
ADICIONAR_TELEFONE = '/comum/setor_adicionar_telefone/{setor}/'
EDITAR_EMAIL = '/comum/setor_editar_email/{setor}/'
REMOVER_TELEFONE = '/comum/setor_remover_telefone/{telefone}/'


def test_lista_telefonica_e_exportacao_csv(logado_comum, telefone_do_setor):
    """A lista telefônica mostra o ramal do setor, e o CSV exporta o mesmo dado.

    As duas rotas num teste porque o CSV é o botão "Exportar CSV" da própria lista: o que se
    afirma é que os dois caminhos enxergam o **mesmo** telefone — a tela monta a lista por
    ``setortelefone_set`` e o CSV percorre ``SetorTelefone.objects.all()``, duas consultas
    diferentes que têm de concordar.

    O CSV é buscado com ``buscar`` (requisição da sessão do navegador, sem renderizar): a resposta
    é um anexo ``text/csv``, e um ``goto`` nela só produziria um download sem DOM para afirmar.

    Papel sem permissão nenhuma de propósito — a lista é aberta a qualquer pessoa logada, e é
    assim que ela é usada.
    """
    tela = Tela(logado_comum('solicitante')).ir(TELEFONES)

    tela.ver_titulo('Telefones')
    tela.ver_texto(telefone_do_setor.setor.nome)
    tela.ver_texto(telefone_do_setor.numero)

    csv = tela.buscar(TELEFONES_CSV)
    assert csv.status == 200, f'a exportação em CSV respondeu HTTP {csv.status}'
    assert csv.headers['content-type'] == 'text/csv', f'a exportação veio como {csv.headers["content-type"]!r}'
    assert 'attachment' in csv.headers['content-disposition'], 'a exportação deixou de ser anexo — o navegador abriria o CSV na tela'
    assert telefone_do_setor.ramal in csv.text(), 'o ramal que a lista mostra não saiu no CSV'


def test_ciclo_do_telefone_do_setor(logado_comum, setor_descartavel):
    """Cadastra um telefone no setor e o remove pelo botão da própria linha.

    Um teste para o ciclo porque a remoção só existe depois do cadastro, e é o cadastro que
    produz o ``pk`` que a remoção consome — o endereço de remoção sai do ``href`` da linha, nunca
    de um ``pk`` montado pelo teste.

    A remoção é por GET, sem ``require_POST`` e sem confirmação (``comum/views.py``): é por isso
    que o alvo é um telefone criado por este teste, num setor descartável.
    """
    from comum.models import SetorTelefone

    ramal = '4711'
    rota = ADICIONAR_TELEFONE.format(setor=setor_descartavel.pk)

    tela = Tela(logado_comum('gestor_pessoal')).ir(rota)
    tela.ver_texto('Nenhum telefone cadastrado.')
    tela.preencher_formulario(
        [
            ('Número telefônico', 'texto', '(84) 4005-4711'),
            ('Ramal', 'texto', ramal),
            ('Observação', 'texto', 'Sala de reuniões'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso('Telefone adicionado com sucesso.')
    telefone = SetorTelefone.objects.filter(setor=setor_descartavel, ramal=ramal).first()
    assert telefone is not None, 'a UI disse que adicionou, mas o telefone não persistiu'

    url_remover = REMOVER_TELEFONE.format(telefone=telefone.pk)
    botao = tela.linha(ramal).loc(f'//a[@href="{url_remover}"]').first
    assert botao.count(), f'a linha do telefone não ofereceu a remoção em {url_remover}'
    botao.click()

    tela.sucesso('Telefone removido com sucesso.')
    assert not SetorTelefone.objects.filter(pk=telefone.pk).exists(), 'a UI disse que removeu, mas o telefone continua no banco'


def test_editar_email_do_setor(logado_comum, setor_descartavel):
    """Grava o e-mail institucional do setor.

    É o endereço para onde o SUAP manda o que é do setor e não de uma pessoa, então o campo é
    dado institucional: o teste afirma a persistência, não a mensagem.
    """
    from rh.models import Setor

    email = f'{setor_descartavel.sigla.lower()}@ifrn.edu.br'

    tela = Tela(logado_comum('gestor_pessoal')).ir(EDITAR_EMAIL.format(setor=setor_descartavel.pk))
    tela.preencher('E-mail', 'texto', email)
    tela.clicar_botao('Salvar')

    tela.sucesso('E-mail editado com sucesso.')
    assert Setor.objects.get(pk=setor_descartavel.pk).email == email, 'a UI disse que editou, mas o e-mail do setor não persistiu'


def test_manutencao_de_telefone_fechada_a_quem_nao_gerencia(logado_comum, telefone_do_setor):
    """Quem não gerencia telefone de setor nem chefia o setor leva 403 nas três telas.

    Medido por status HTTP, não por ausência de botão no menu: as três rotas recebem o ``pk`` pela
    URL e uma delas **apaga** com um GET — esconder o link não protege nada.
    """
    setor = telefone_do_setor.setor
    tela = Tela(logado_comum('solicitante'))

    assert tela.buscar(ADICIONAR_TELEFONE.format(setor=setor.pk)).status == 403, 'o cadastro de telefone ficou aberto a quem não gerencia setor'
    assert tela.buscar(EDITAR_EMAIL.format(setor=setor.pk)).status == 403, 'a edição do e-mail do setor ficou aberta a quem não gerencia setor'
    assert tela.buscar(REMOVER_TELEFONE.format(telefone=telefone_do_setor.pk)).status == 403, (
        'a remoção de telefone ficou aberta a quem não gerencia setor'
    )
