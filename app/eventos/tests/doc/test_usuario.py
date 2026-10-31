"""Roteiro navegado das tarefas do ``eventos`` — a fonte de ``eventos/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções são as mesmas
dos e2e (título, botão, mensagem de sucesso) e existem para a rodada falhar alto quando a
tela mudou de forma: doc que descreve um passo que não existe mais é pior que doc velha.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/eventos/evento/'
AREA_PUBLICA = '/eventos/'
CPF_VISITANTE = '987.650.123-21'


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela para a redação da doc (não é asserção)."""
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    sys.stderr.write(
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}\n'
    )


def test_cadastrar_evento(logado_doc, capturar):
    """Tarefa 1 — o servidor cadastra o evento e abre o período de inscrições."""
    from eventos.models import Evento

    hoje = date.today()
    nome = f'E2E Evento {uuid4().hex[:8]}'

    tela = Tela(logado_doc('coordenador')).ir(LISTAGEM)
    tela.ver_titulo('Eventos')
    capturar(tela.pagina, 'evento-listagem')

    # Pelo botão e não por `ir(FORM)`: é o passo 1 da doc. A camada `Tela` não porta o
    # `acesso o menu` do behave (ver `djtools/e2e_ui.py:20-23`), então o caminho de menu
    # continua sendo o único tipo de passo que esta rodada não consegue executar.
    tela.ver_botao('Adicionar Evento')
    tela.clicar_botao('Adicionar Evento')
    tela.ver_titulo('Adicionar Evento')
    _anotar('form-evento', tela)
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
            ('Data de Início', 'data', (hoje + timedelta(days=30)).strftime('%d/%m/%Y')),
            ('Hora de Início', 'hora', '08:00'),
            ('Data de Fim', 'data', (hoje + timedelta(days=40)).strftime('%d/%m/%Y')),
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
    capturar(tela.pagina, 'evento-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Ação realizada com sucesso.')
    evento = Evento.objects.filter(nome=nome).first()
    assert evento is not None, 'a UI disse que salvou, mas não persistiu'
    tela.ver_titulo(nome)
    _anotar('evento-recem-criado', tela)
    capturar(tela.pagina, 'evento-criado')

    tela.clicar_aba('Detalhamento')
    capturar(tela.pagina, 'evento-detalhamento')
    tela.linha('Participante').clicar_icone('edição')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    _anotar('popup-tipo-participante', popup)
    capturar(tela.pagina, 'evento-inscricoes')
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


def test_avaliar_evento(logado_doc, evento_submetido, capturar):
    """Tarefa 2 — o avaliador da dimensão defere o evento submetido."""
    from eventos.models import Evento

    tela = Tela(logado_doc('avaliador')).ir(LISTAGEM)
    tela.clicar_aba('Aguardando minha aprovação')
    capturar(tela.pagina, 'avaliacao-aguardando')
    tela.linha(evento_submetido.nome).clicar_icone('exibição')

    tela.ver_titulo(evento_submetido.nome)
    tela.ver_botao('Avaliar')
    _anotar('evento-a-avaliar', tela)
    tela.clicar_botao('Avaliar')
    capturar(tela.pagina, 'avaliacao-parecer')
    tela.clicar_botao('Deferir')

    tela.sucesso('O evento foi deferido.')
    assert Evento.objects.get(pk=evento_submetido.pk).deferido, 'a UI disse que deferiu, mas não persistiu'


def test_gerenciar_participantes(logado_doc, evento_deferido, capturar):
    """Tarefa 3, etapa 1 — o coordenador inclui um participante pelo popup."""
    from eventos.models import Participante

    evento, tipo = evento_deferido
    nome = f'Participante {uuid4().hex[:8]}'

    tela = Tela(logado_doc('coordenador')).ir(f'/eventos/evento/{evento.pk}/')
    _anotar('evento-deferido', tela)
    capturar(tela.pagina, 'evento-pagina')
    tela.clicar_botao('Participantes')
    tela.ver_titulo(f'Participantes: {evento.nome}')
    tela.clicar_aba('Organizador')
    capturar(tela.pagina, 'participantes-lista')

    tela.aba('Organizador').clicar_botao('Adicionar')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    _anotar('popup-participante', popup)
    capturar(tela.pagina, 'participante-formulario')
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
    incluido = Participante.objects.filter(evento=evento, tipo=tipo, nome=nome).first()
    assert incluido is not None, 'a UI disse que salvou, mas não persistiu'
    # MEDIDO, e contraria o protótipo: quem o coordenador inclui pela tela já entra com a
    # inscrição confirmada (`Participante.inscricao_validada` tem `default=True`,
    # `eventos/models.py:2626`). "Confirmar inscrição" existe para as inscrições que chegam
    # PENDENTES da página pública (`eventos/forms.py:1210,1226` gravam `False`) — é lá que a
    # doc documenta o botão, e é lá que esta rodada o executa.
    assert incluido.inscricao_validada, 'inclusão manual deixou de já confirmar a inscrição; a doc afirma que confirma'


def test_confirmar_presenca_e_certificado(logado_doc, evento_realizado_com_organizador, capturar):
    """Tarefa 3, etapas 2 e 3 — confirmar presença, finalizar o evento e emitir certificado."""
    from eventos.models import Evento, Participante

    evento, _tipo, participante = evento_realizado_com_organizador
    participantes = f'/eventos/participantes/{evento.pk}/'

    tela = Tela(logado_doc('coordenador')).ir(participantes)
    tela.clicar_aba('Organizador')
    _anotar('participantes-acoes', tela.aba('Organizador'))
    tela.aba('Organizador').selecionar_cartao(participante.nome)
    capturar(tela.pagina, 'participante-selecionado')
    tela.aba('Organizador').clicar_botao('Confirmar presença')
    tela.sucesso('1 presença(s) confirmada(s) com sucesso.')

    tela.ir(f'/eventos/evento/{evento.pk}/')
    tela.ver_botao('Finalizar')
    tela.clicar_botao('Finalizar')
    tela.sucesso('O evento foi finalizado com sucesso.')
    assert Evento.objects.get(pk=evento.pk).finalizado, 'a UI disse que finalizou, mas não persistiu'

    tela.ir(participantes).clicar_aba('Organizador')
    tela.aba('Organizador').selecionar_cartao(participante.nome)
    tela.aba('Organizador').clicar_botao('Enviar certificado')
    tela.sucesso('1 E-mail(s) enviado(s) com sucesso.')
    capturar(tela.pagina, 'certificado-enviado')
    assert Participante.objects.get(pk=participante.pk).certificado_enviado, 'a UI disse que enviou, mas não persistiu'


def test_inscricao_publica_e_confirmacao(page, logado_doc, evento_com_inscricoes_abertas, capturar):
    """Tarefa pública + a confirmação que ela exige do coordenador, no mesmo teste.

    Os dois lados são um encadeamento só e não existem separados: a inscrição pública é a
    ÚNICA que nasce pendente (`eventos/forms.py:1210,1226`), então é a única que dá o que
    confirmar. Executar "Confirmar inscrição" sobre um participante incluído à mão devolve
    "Nenhuma inscrição confirmada." — medido nesta rodada.
    """
    from eventos.models import Participante

    evento = evento_com_inscricoes_abertas

    tela = Tela(page).ir(AREA_PUBLICA)
    tela.ver_titulo('Eventos')
    capturar(page, 'publico-listagem')
    tela.clicar_link(evento.nome)
    tela.esperar()
    _anotar('publico-passo-1', tela)
    capturar(page, 'publico-identificacao')

    tela.preencher_formulario([('Nacionalidade', 'lista', 'Brasileiro Nato'), ('CPF', 'texto', CPF_VISITANTE)])
    tela.clicar_botao('Continuar')
    _anotar('publico-passo-2', tela)
    tela.preencher_formulario(
        [
            ('Nome', 'texto', 'Usuário Teste'),
            ('E-mail', 'texto', 'teste@teste.com'),
            ('Telefone', 'texto', '(84) 99999-9999'),
        ]
    )
    capturar(page, 'publico-dados')
    tela.clicar_botao('Continuar')

    _anotar('publico-passo-3', tela)
    tela.preencher('Tipo de participação', 'lista', 'Participante')
    tela.clicar_botao('Confirmar inscrição')

    tela.ver_texto('Inscrição realizada com sucesso.')
    capturar(page, 'publico-confirmacao')
    inscrito = Participante.objects.filter(evento=evento, cpf=CPF_VISITANTE).first()
    assert inscrito is not None, 'a UI disse que inscreveu, mas não persistiu'
    assert not inscrito.inscricao_validada, 'a inscrição pública deixou de nascer pendente; a doc afirma que nasce'

    # Do outro lado do balcão: o coordenador confirma a inscrição que acabou de chegar.
    gestao = Tela(logado_doc('coordenador')).ir(f'/eventos/participantes/{evento.pk}/')
    gestao.clicar_aba('Participante')
    gestao.aba('Participante').selecionar_cartao(inscrito.nome)
    capturar(gestao.pagina, 'inscricao-pendente')
    gestao.aba('Participante').clicar_botao('Confirmar inscrição')
    gestao.sucesso('1 inscrição(ões) confirmada(s) com sucesso.')
    assert Participante.objects.get(pk=inscrito.pk).inscricao_validada, 'a UI disse que confirmou, mas não persistiu'


@pytest.mark.parametrize(
    ('rota', 'slug'),
    [
        ('/eventos/calendario_eventos/', 'calendario'),
        ('/eventos/relatorio/', 'relatorio-eventos'),
        ('/eventos/relatorio_participantes/', 'relatorio-participantes'),
    ],
)
def test_emitir_consultas(logado_doc, capturar, rota, slug):
    """Tarefas 4 e 5 — as três telas de consulta de `Comunicação Social::Relatórios`.

    Nenhuma `.feature` as cobre e o protótipo nem as menciona. Submeter o filtro é o passo
    que a doc descreve, então ele é EXECUTADO aqui: sem isto, "clique em Enviar" seria um
    passo escrito sem nunca ter sido rodado.
    """
    tela = Tela(logado_doc('coordenador')).ir(rota)
    # Sem este guard a rodada "documenta" a página de traceback do Django como se fosse a
    # tela — foi o que aconteceu com o calendário antes de o seed ganhar o `Ano` corrente.
    assert 'at /' not in tela.pagina.title(), f'{rota} respondeu página de erro: {tela.pagina.title()}'
    _anotar(f'{slug}-listagem', tela)

    tela.clicar_botao('Enviar')
    tela.esperar()
    _anotar(f'{slug}-resultado', tela)
    capturar(tela.pagina, f'{slug}-resultado')


def test_registrar_atendimento_ao_publico(logado_doc, capturar):
    """Tarefa 6 — o Comunicador Social registra um atendimento prestado no campus.

    O protótipo classificou esta tela como "de apoio" com a ressalva de que podia estar
    errado (``docs/agents/PROTOTIPO-doc-usuario-eventos.md:124``). Está: o registro grava um
    fato do dia a dia, tem formulário próprio de seis campos e um grupo dedicado — e é ele
    que consome as cinco tabelas de `Cadastros::Atendimentos`, essas sim de apoio.
    """
    from eventos.models import AtendimentoPublico

    antes = AtendimentoPublico.objects.count()

    tela = Tela(logado_doc('comunicacao')).ir('/admin/eventos/atendimentopublico/')
    tela.ver_titulo('Atendimentos ao Público')
    _anotar('atendimento-listagem', tela)
    tela.clicar_botao('Adicionar Atendimento ao Público')
    tela.ver_titulo('Adicionar Atendimento ao Público')
    _anotar('atendimento-formulario', tela)
    # `autocomplete` e não `lista`: as seis chaves estrangeiras deste formulário são select2
    # com busca por ajax (`class="js-example-data-ajax select2-hidden-accessible"`), então o
    # `<select>` nasce vazio e `select_option` nunca acha a opção.
    tela.preencher_formulario(
        [
            # `opcao=''` aceita o primeiro resultado: o rótulo do campus no select2 não é
            # nem a sigla nem o nome completo, e fixá-lo aqui só criaria um acoplamento frágil.
            ('Campus', 'autocomplete', 'CZN', ''),
            ('Tipo', 'autocomplete', 'Presencial'),
            ('Motivo', 'autocomplete', 'Informação'),
            ('Assunto', 'autocomplete', 'Processo Seletivo'),
            ('Público', 'autocomplete', 'Público Externo'),
            ('Situação', 'autocomplete', 'Concluído'),
        ]
    )
    capturar(tela.pagina, 'atendimento-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert AtendimentoPublico.objects.count() == antes + 1, 'a UI disse que salvou, mas não persistiu'
    capturar(tela.pagina, 'atendimento-listagem')


def test_publicar_banner(logado_doc, capturar):
    """Tarefa 7 — o Coordenador de Comunicação Sistêmico publica um banner com período.

    Mesma correção do protótipo que a tarefa 6. As datas vão como texto ISO porque o widget
    é um ``input[type=datetime-local]`` (``djtools/forms/widgets/datetimeplus.py:63``), e não
    o ``data`` dd/mm/aaaa que a camada `Tela` conhece — nada é acrescentado à camada por isso.
    """
    from eventos.models import Banner

    titulo = f'Banner {uuid4().hex[:8]}'
    inicio = date.today() + timedelta(days=1)
    # `BannerForm.clean` (`eventos/forms.py:1659-1667`) recusa um segundo banner no mesmo
    # período, e a suíte não dá flush: sem esta limpeza uma execução em banco reusado
    # (depuração local) falharia na validação em vez de no que a doc afirma.
    Banner.objects.all().delete()

    tela = Tela(logado_doc('comunicacao')).ir('/admin/eventos/banner/')
    tela.ver_titulo('Banners')
    _anotar('banner-listagem', tela)
    tela.clicar_botao('Adicionar Banner')
    tela.ver_titulo('Adicionar Banner')
    _anotar('banner-formulario', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', titulo),
            ('Imagem', 'arquivo', 'arquivo.png'),
            ('Tipo', 'lista', 'Início'),
            ('Link', 'texto', 'http://site.url'),
            # Sem os segundos: o `fill` do Playwright num `input[type=datetime-local]` recusa
            # `...T08:00:00` com "Malformed value" (medido), porque o Chromium normaliza o valor.
            ('Início da Publicação', 'texto', f'{inicio.isoformat()}T08:00'),
            ('Término da Publicação', 'texto', f'{(inicio + timedelta(days=7)).isoformat()}T18:00'),
        ]
    )
    capturar(tela.pagina, 'banner-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert Banner.objects.filter(titulo=titulo).exists(), 'a UI disse que salvou, mas não persistiu'
    capturar(tela.pagina, 'banner-listagem')
