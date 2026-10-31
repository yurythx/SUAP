"""Fluxo: o coordenador configura o edital — cargos/áreas, vagas por campus, correlatas, apoio.

É a etapa entre "o edital existe" e "alguém pode se inscrever": sem ``VagaEdital`` não há
inscrição possível (``is_em_periodo_de_inscricao_servidor``, ``models.py:220``) nem
processamento (``views.py:215``). Todas as telas daqui são **popups do fancybox** abertos a
partir da aba Edital, e cada uma grava um pedaço diferente do mesmo agregado:

* ``configurar_cargos`` cria uma ``VagaEdital`` por (campus x cargo/área) — o produto
  cartesiano é a regressão silenciosa mais provável (``forms.py:748-766``);
* ``cadastrar_vagas`` distribui a quantidade **por campus**, e só ali;
* ``cadastrar_areas_correlatas`` é o que deixa servidor de área vizinha concorrer à vaga;
* ``cadastrar_cargos_correlatos`` faz o mesmo para cargo distinto no SIAPE (ex.: odontólogo DEC JUD);
* ``atualizar_afastamentos`` copia o cadastro global de licenças para dentro do edital;
* ``excluir_vagas`` remove o par cargo/área inteiro, e só enquanto ninguém foi contemplado.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

GERENCIAR = '/remanejamento/edital/{}/gerenciar/'
CONFIGURAR_CARGOS = '/remanejamento/edital/{}/configurar_cargos/'
CADASTRAR_VAGAS = '/remanejamento/edital/{}/vagaedital_id/{}/cadastrar_vagas/'
EXCLUIR_VAGAS = '/remanejamento/edital/{}/vagaedital_id/{}/excluir_vagas/'
CADASTRAR_AREAS_CORRELATAS = '/remanejamento/edital/vagaedital_id/{}/cadastrar_areas_correlatas/'
CADASTRAR_CARGOS_CORRELATOS = '/remanejamento/edital/vagaedital_id/{}/cadastrar_cargos_correlatos/'
ATUALIZAR_AFASTAMENTOS = '/remanejamento/edital/{}/atualizar_afastamentos/'

CARGO_SEM_AREA = 'Assistente e2e'
CARGO_COM_AREA = 'Técnico de Laboratório e2e - Informática e2e'


def _aba_edital(logado_remanejamento, edital) -> Tela:
    """Abre o gerenciamento do edital já na aba "Edital".

    O clique é necessário porque, sem ``?tab=``, ``gerenciar_edital`` abre na aba de inscrições.
    """
    tela = Tela(logado_remanejamento('coordenador')).ir(GERENCIAR.format(edital.pk))
    tela.clicar_aba('Edital')
    return tela


def test_configura_cargos_e_distribui_vagas_por_campus(logado_remanejamento, edital_sem_vagas):
    """Configura cargo simples + cargo com área e depois lança a vaga no campus de destino.

    As duas telas são o mesmo agregado em dois passos, e o segundo só existe porque o primeiro
    cria as vagas **zeradas**: ``ConfigurarCargosVagasEditalForm.processar`` grava
    ``qtd_edital=0`` para todo (campus, cargo) marcado, e é ``CadastrarVagasEditalForm`` que
    põe número. Entre eles, a listagem tem de sair de "Nenhum cargo adicionado." para duas
    linhas.
    """
    from remanejamento.models import VagaEdital

    tela = _aba_edital(logado_remanejamento, edital_sem_vagas)
    tela.quadro('Vagas').ver_texto('Nenhum cargo adicionado.')

    tela.ir(CONFIGURAR_CARGOS.format(edital_sem_vagas.pk))
    tela.ver_texto('Configurar Cargos e Áreas do Edital')
    tela.preencher(CARGO_SEM_AREA, 'checkbox', 'marcar')
    tela.preencher(CARGO_COM_AREA, 'checkbox', 'marcar')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cargos configurados com sucesso')
    vagas = VagaEdital.objects.filter(edital=edital_sem_vagas)
    assert vagas.count() == 4, f'esperava 2 campi x 2 cargos/áreas, veio {vagas.count()}: {list(vagas)}'
    assert set(vagas.values_list('campus__sigla', flat=True)) == {'A0', 'B0'}, 'a vaga não foi replicada nos dois campi do edital'

    vaga_destino = vagas.get(campus__sigla='B0', cargo_emprego_area__isnull=True)
    tela.ir(CADASTRAR_VAGAS.format(edital_sem_vagas.pk, vaga_destino.pk))
    tela.ver_texto('Vagas do Cargo/Área')
    tela.preencher('B0', 'número', '2')
    tela.clicar_botao('Salvar')

    tela.sucesso('Vagas cadastradas com sucesso')
    vaga_destino.refresh_from_db()
    assert vaga_destino.qtd_edital == 2, f'a UI disse que salvou, mas a vaga continua com {vaga_destino.qtd_edital}'

    tela.clicar_aba('Edital')
    tela.quadro('Vagas').linha(CARGO_SEM_AREA)


def test_cadastra_area_correlata_da_vaga(logado_remanejamento, edital_com_inscricoes_abertas):
    """Acrescenta uma área correlata à vaga e confere que a listagem passa a exibi-la.

    A área correlata é o que permite um servidor de área vizinha concorrer à vaga
    (``models.py:226-229``). O edital já nasce com uma correlata pela fábrica do conftest, e o
    teste acrescenta a segunda: ``processar()`` usa ``set()``
    (``forms.py:837``), então o que se afirma é que a tela **soma** em vez de substituir —
    trocar ``set`` por uma atribuição destrutiva aqui apagaria calado o que já estava.
    """
    from remanejamento.models import VagaEdital

    vaga = VagaEdital.objects.get(edital=edital_com_inscricoes_abertas, campus__sigla='B0', cargo_emprego_area__isnull=False)
    tela = Tela(logado_remanejamento('coordenador')).ir(CADASTRAR_AREAS_CORRELATAS.format(vaga.pk))
    tela.ver_texto('Cargo/Área')
    # O rótulo é "Areas correlatas", sem acento e sem caixa alta: o campo não declara `label`
    # (`forms.py:817`) e o Django o deriva do nome do atributo.
    tela.preencher('Areas correlatas', 'autocomplete multiplo', 'Redes e2e')
    # "Enviar" e não "Salvar": este formulário é um `forms.Form` cru, sem `SUBMIT_LABEL`
    # (`forms.py:816`), e `djtools/templates/form.html:26` usa "Enviar" como default.
    tela.clicar_botao('Enviar')

    tela.sucesso('Áreas correlatas cadastradas com sucesso')
    correlatas = set(vaga.areas_correlatas.values_list('descricao', flat=True))
    assert correlatas == {'Sistemas de Computação e2e', 'Redes e2e'}, f'a UI disse que salvou, mas as correlatas são {correlatas}'

    tela = _aba_edital(logado_remanejamento, edital_com_inscricoes_abertas)
    tela.quadro('Vagas').linha(CARGO_COM_AREA).ver_texto('Redes e2e')


def test_cadastra_cargo_correlato_da_vaga(logado_remanejamento, edital_com_inscricoes_abertas):
    """Torna outro cargo do edital correlato da vaga de cargo sem área.

    É o caso dos odontólogos: o mesmo cargo vem do SIAPE com códigos distintos (40 HORAS, DEC JUD),
    e todos têm de concorrer na mesma lista. A gravação vale para as vagas do cargo em **todos**
    os campi (``CadastrarCargosCorrelatosVagaEditalForm.processar``), e não só na linha clicada.
    """
    from remanejamento.models import VagaEdital

    vaga = VagaEdital.objects.get(edital=edital_com_inscricoes_abertas, campus__sigla='B0', cargo_emprego_area__isnull=True)
    tela = Tela(logado_remanejamento('coordenador')).ir(CADASTRAR_CARGOS_CORRELATOS.format(vaga.pk))
    tela.ver_texto(f'Cargo: {CARGO_SEM_AREA}')
    tela.preencher('Cargos Correlatos', 'autocomplete multiplo', 'Técnico de Laboratório e2e')
    tela.clicar_botao('Enviar')

    tela.sucesso('Cargos correlatos cadastrados com sucesso')
    # salvar devolve para a aba "Edital" (?tab=edital_info), e não para a de inscrições
    tela.quadro('Vagas').linha(CARGO_SEM_AREA).ver_texto('Técnico de Laboratório e2e')
    vagas_do_cargo = VagaEdital.objects.filter(edital=edital_com_inscricoes_abertas, cargo=vaga.cargo)
    assert all(v.cargos_correlatos.filter(nome='Técnico de Laboratório e2e').exists() for v in vagas_do_cargo), (
        'o correlato não foi gravado em todas as vagas do cargo'
    )


def test_gerenciar_respeita_aba_da_url_e_filtro_abre_inscricoes(logado_remanejamento, edital_com_inscricoes_abertas):
    """A aba pedida em ``?tab=`` prevalece; só o uso do filtro de inscrições leva à aba "Inscrições".

    Regressão: o filtro era montado sobre ``request.POST`` vazio, validava em todo GET e forçava a
    aba de inscrições — quem salvava qualquer coisa na aba "Edital" voltava em outra aba.
    """
    tela = Tela(logado_remanejamento('coordenador')).ir(GERENCIAR.format(edital_com_inscricoes_abertas.pk) + '?tab=edital_info')
    tela.quadro('Vagas').linha(CARGO_SEM_AREA)

    tela.ir(GERENCIAR.format(edital_com_inscricoes_abertas.pk) + '?tab=edital_info&texto=nenhum-servidor')
    tela.quadro('Inscrições confirmadas')


def test_atualiza_licencas_e_afastamentos_do_edital(logado_remanejamento, edital_com_inscricoes_abertas):
    """Importa o cadastro global de licenças para dentro do edital.

    ``atualizar_afastamentos`` (``views.py:791-806``) copia cada ``AfastamentoRemocaoInterna``
    para um ``EditalAfastamento``, preservando ``impeditivo`` e ``desconta_exercicio``. É desse
    par que dependem a recusa da inscrição de quem está afastado e o desconto de tempo no
    processamento — o edital guarda a **cópia**, e não o cadastro, justamente para que uma
    mudança futura na tabela global não reescreva a regra de um edital já publicado.
    """
    from remanejamento.models import AfastamentoRemocaoInterna, EditalAfastamento

    tela = _aba_edital(logado_remanejamento, edital_com_inscricoes_abertas)
    tela.quadro('Licenças e Afastamentos').ver_texto('Nenhuma Licença/Afastamento para este edital.')

    tela.ir(ATUALIZAR_AFASTAMENTOS.format(edital_com_inscricoes_abertas.pk))

    tela.sucesso('Afastamentos atualizados com sucesso')
    copiados = EditalAfastamento.objects.filter(edital=edital_com_inscricoes_abertas)
    assert copiados.count() == AfastamentoRemocaoInterna.objects.count(), 'nem todo afastamento do cadastro global chegou ao edital'
    assert copiados.filter(desconta_exercicio=True).exists(), 'a cópia perdeu o "desconta tempo de exercício"'


def test_remove_cargo_do_edital(logado_remanejamento, edital_com_inscricoes_abertas):
    """Remove o par cargo/área inteiro — as duas vagas, uma por campus.

    ``excluir_vagas_edital`` (``views.py:727-746``) apaga por (edital, cargo, área) e não pelo
    registro clicado: a vaga é conceitualmente uma por campus, mas a decisão "este cargo
    participa do edital" é uma só. Por isso a asserção é sobre as **duas** linhas sumirem.
    """
    from remanejamento.models import VagaEdital

    vaga = VagaEdital.objects.get(edital=edital_com_inscricoes_abertas, campus__sigla='B0', cargo_emprego_area__isnull=True)
    cargo = vaga.cargo

    tela = Tela(logado_remanejamento('coordenador')).ir(EXCLUIR_VAGAS.format(edital_com_inscricoes_abertas.pk, vaga.pk))

    tela.sucesso('Vagas excluídas com sucesso')
    assert not VagaEdital.objects.filter(edital=edital_com_inscricoes_abertas, cargo=cargo, cargo_emprego_area__isnull=True).exists(), (
        'a UI disse que excluiu, mas as vagas do cargo continuam no edital'
    )
    assert VagaEdital.objects.filter(edital=edital_com_inscricoes_abertas, cargo_emprego_area__isnull=False).exists(), (
        'a exclusão levou junto o cargo com área, que não foi pedido'
    )
