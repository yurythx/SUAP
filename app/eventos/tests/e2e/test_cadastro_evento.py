"""Cadastro de um evento pelo servidor (modo 2).

É a porta de entrada do módulo: sem ela nenhum outro fluxo existe. O formulário do evento
concentra quase todos os tipos de campo do SUAP (checkbox múltiplo, rádio renderizado por
template próprio, autocomplete múltiplo, arquivo, data, hora), então este teste é o que
pega regressão de renderização do `EventoForm` — e, na segunda metade, a criação automática
dos tipos de participante que o `EventoAdmin.save_related` faz depois de gravar
(`eventos/admin.py:420-434`), sem a qual o evento nasce sem nenhuma inscrição possível.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

FORM = '/admin/eventos/evento/add/'


def test_cadastra_evento_e_configura_tipo_participante(logado_eventos):
    """Cadastra o evento e, na sequência, ajusta o tipo de participante "Participante".

    Os dois blocos eram um cenário do behave e continuam um teste só aqui: o segundo edita
    a linha que o `save_related` acabou de criar, e não teria como existir sozinho.

    As datas são relativas a hoje (ver decisão 3 no conftest) e não os 01/02/2020 literais da
    behave; o que o teste exercita é a ordem início < fim, que `EventoForm.clean`
    (`eventos/forms.py:887-895`) valida.
    """
    from eventos.models import Evento

    hoje = date.today()
    inicio, fim = hoje + timedelta(days=30), hoje + timedelta(days=40)
    # Nome único: a suíte não dá flush e o CI usa --reuse-db (armadilha 8), então um nome
    # fixo faria a segunda execução gravar um homônimo e a busca do ORM ficar ambígua.
    nome = f'E2E Evento {uuid4().hex[:8]}'

    tela = Tela(logado_eventos('coordenador')).ir(FORM)
    tela.ver_titulo('Adicionar Evento')
    tela.preencher_formulario(
        [
            ('Título do Evento', 'texto', nome),
            ('Dimensões', 'checkbox multiplo', 'Ensino, Pesquisa'),
            ('Apresentação', 'textarea', 'Descrição do evento'),
            ('Imagem', 'arquivo', 'arquivo.png'),
            ('Site', 'texto', 'http://site.url'),
            ('Recursos Envolvidos', 'texto', '5.000,00'),
            ('Organizadores', 'autocomplete multiplo', 'Coord Evento'),
            ('Local', 'texto', 'Local do Evento'),
            ('Data de Início', 'data', inicio.strftime('%d/%m/%Y')),
            ('Hora de Início', 'hora', '08:00'),
            ('Data de Fim', 'data', fim.strftime('%d/%m/%Y')),
            ('Hora de Fim', 'hora', '18:00'),
            ('Inscrição Online', 'checkbox', 'marcar'),
            ('Gera Certificado?', 'checkbox', 'marcar'),
            ('Carga Horária do Evento', 'texto', '10:00'),
            ('Localização', 'radio', 'Local'),
            ('Espacialidades', 'checkbox multiplo', 'Ambiente Virtual'),
            ('Porte', 'radio', 'Pequeno Porte'),
            ('Tipo', 'radio', 'Científico/tecnológico'),
            ('Subtipo', 'radio', 'Palestras'),
            ('Público Alvo', 'checkbox multiplo', 'Público Externo'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Ação realizada com sucesso.')
    evento = Evento.objects.filter(nome=nome).first()
    assert evento is not None, 'a UI disse que salvou, mas não persistiu'
    assert evento.tipos_participante.filter(tipo_participacao__descricao='Participante').exists(), (
        'o evento gravou sem o tipo de participante "Participante" que o save_related deveria criar'
    )

    tela.ver_titulo(nome)
    tela.clicar_aba('Detalhamento')
    tela.linha('Participante').clicar_icone('edição')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Limite de Inscrições', 'número', '50'),
            ('Permite Inscrição Direta', 'checkbox', 'marcar'),
            ('Início das Inscrições', 'data', hoje.strftime('%d/%m/%Y')),
            ('Fim das Inscrições', 'data', (hoje + timedelta(days=20)).strftime('%d/%m/%Y')),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Tipo de participante alterado com sucesso.')
    tipo = evento.tipos_participante.get(tipo_participacao__descricao='Participante')
    assert (tipo.limite_inscricoes, tipo.permite_inscricao_direta) == (50, True), 'a UI disse que alterou, mas não persistiu'
