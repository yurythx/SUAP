"""Fluxo: o ciclo do chamado visto pelo solicitante (modo 2) — abrir, acompanhar, comentar, anexar,
adicionar/remover interessados e arquivar o próprio comentário.

Por que importa: é a metade do módulo que o usuário final enxerga. A regressão que dói aqui é a
silenciosa de permissão: um comentário que só aparece para o atendente, um anexo que o solicitante
não consegue ver, um interessado que nunca recebe cópia. O fluxo de abertura guarda a validação do
formulário de abertura — a única prova de que o "Descrição é obrigatória" continua de pé.

O chamado dos testes de acompanhamento nasce por ORM (a abertura em si é o primeiro teste): o
interesse é o que se faz com um chamado que já existe, e a cadeia do behave não pode ser
reproduzida em testes independentes (armadilha 8).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, arquivo_de_teste

from .conftest import PAPEIS, popup_em, postar, usuario, ver_campos

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ABRIR = '/centralservicos/listar_area_servico/'
MEUS_CHAMADOS = '/centralservicos/meus_chamados/?tab=ativos'
REMOVER_OUTROS = '/centralservicos/remover_outros_interessados/{}/{}/'
ARQUIVAR = '/centralservicos/arquivar_comentario/{}/'
DESARQUIVAR = '/centralservicos/desarquivar_comentario/{}/'


def test_servidor_abre_chamado(logado_central, contexto):
    """O servidor escolhe a área, o serviço, vê o erro de obrigatório e abre o chamado.

    O serviço do contexto não tem artigo de Base de Conhecimento, então o link do catálogo leva
    direto ao formulário — o caminho do serviço que ainda não tem FAQ.
    """
    from centralservicos.models import Chamado, StatusChamado

    descricao = f'Impressora da sala dos servidores com problema. (e2e {uuid4().hex[:8]})'

    tela = Tela(logado_central('servidor')).ir(ABRIR)
    tela.ver_titulo('Listar Áreas de serviço')
    tela.clicar_link(contexto.area.nome)
    tela.ver_titulo(f'Abrir chamado para {contexto.area.nome}')
    tela.clicar_link(contexto.servico.nome)

    # O serviço não tem artigo público, então `visualizar_solucoes` redireciona para a abertura.
    tela.ver_titulo(contexto.servico.nome)
    ver_campos(tela, ['Descrição', 'Campus', 'Centro de Atendimento'])
    tela.ver_botao('Abrir chamado')

    tela.clicar_botao('Abrir chamado')
    tela.erro('Por favor, corrija os erros abaixo.')
    tela.erro('Este campo é obrigatório')

    tela.preencher_formulario([('Descrição', 'textarea', descricao)])
    tela.clicar_botao('Abrir chamado')
    tela.sucesso('Chamado aberto com sucesso.')

    chamado = Chamado.objects.filter(descricao=descricao).first()
    assert chamado is not None, 'a UI disse que abriu, mas o chamado não persistiu'
    assert chamado.interessado.username == PAPEIS['servidor'], 'o interessado deveria ser quem abriu'
    assert chamado.requisitante.username == PAPEIS['servidor'], 'o requisitante deveria ser quem abriu'
    assert chamado.status == StatusChamado.get_status_aberto(), 'o chamado não nasceu aberto'
    assert chamado.get_atendimento_atribuicao_atual().grupo_atendimento_id == contexto.grupo_atendimento.pk, (
        'o chamado deveria rotear para o grupo de primeiro nível do centro escolhido'
    )


def test_servidor_abre_chamado_com_anexo(logado_central, contexto_com_anexos):
    """Abertura com anexo: o arquivo entra no mesmo POST do formulário (``_salvar_anexos_do_chamado``).

    É o único caminho de **escrita** que nenhuma suíte exercitava — o behave também não cobria (o
    serviço dele não permitia anexo). O campo vive no formset, sem ``<label>`` associado (a tabela
    rotula no ``<th>``), então o ``preencher(..., 'arquivo')`` — que ancora por label — não o
    encontra; o locator sai pelo ``name`` do formset, como o TreeWidget da edição de grupo.
    """
    from centralservicos.models import Chamado, ChamadoAnexo

    contexto = contexto_com_anexos
    descricao = f'Impressora com anexo na abertura. (e2e {uuid4().hex[:8]})'

    tela = Tela(logado_central('servidor')).ir(ABRIR)
    tela.ver_titulo('Listar Áreas de serviço')
    tela.clicar_link(contexto.area.nome)
    tela.ver_titulo(f'Abrir chamado para {contexto.area.nome}')
    tela.clicar_link(contexto.servico.nome)
    tela.ver_titulo(contexto.servico.nome)

    tela.preencher_formulario([('Descrição', 'textarea', descricao)])
    tela.preencher_linha(0, 'descricao', 'texto', 'Foto do painel da impressora')
    tela.loc('//input[@type="file" and contains(@name, "chamadoanexo_set-0-anexo")]').first.set_input_files(arquivo_de_teste('arquivo.pdf'))
    tela.clicar_botao('Abrir chamado')
    tela.sucesso('Chamado aberto com sucesso.')

    chamado = Chamado.objects.filter(descricao=descricao).first()
    assert chamado is not None, 'a UI disse que abriu, mas o chamado não persistiu'
    anexo = ChamadoAnexo.objects.filter(chamado=chamado).first()
    assert anexo is not None, 'o chamado abriu, mas o anexo do formulário não foi salvo'
    assert anexo.descricao == 'Foto do painel da impressora', 'a descrição do anexo não foi gravada'
    assert anexo.anexado_por == usuario(PAPEIS['servidor']), 'o anexo deveria ser de quem abriu o chamado'
    nome_arquivo = anexo.anexo.name.rsplit('/', 1)[-1]
    # O storage do SUAP carimba o nome com um hash (`arquivo-<hash>.pdf`), então o que se afirma é
    # a extensão e o radical do arquivo enviado.
    assert nome_arquivo.startswith('arquivo'), f'o radical do arquivo enviado não é o esperado: {nome_arquivo!r}'
    assert nome_arquivo.endswith('.pdf'), f'a extensão do arquivo enviado não é a esperada: {nome_arquivo!r}'


def test_solicitante_acompanha_comenta_e_anexa(logado_central, contexto_com_artigos, chamado_em_atendimento):
    """O solicitante vê o próprio chamado em "Meus chamados", comenta e anexa um arquivo.

    O comentário só é liberado em Em Atendimento/Suspenso (``Chamado.get_permissoes``), por isso o
    chamado da fixture já está nesse estado.
    """
    from centralservicos.models import ChamadoAnexo, Comunicacao

    chamado = chamado_em_atendimento
    texto = f'A impressora voltou a apresentar o mesmo erro hoje. (e2e {uuid4().hex[:8]})'

    tela = Tela(logado_central('servidor')).ir(MEUS_CHAMADOS)
    tela.ver_titulo('Meus chamados')
    tela.clicar_link(f'INC #{chamado.pk}')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.ver_texto('Em atendimento')

    tela.preencher_textarea('Adicionar comentário', texto)
    tela.clicar_botao('Adicionar Comentário')
    tela.sucesso('Comentário adicionado com sucesso.')
    assert Comunicacao.objects.filter(chamado=chamado, remetente=usuario(PAPEIS['servidor']), texto=texto).exists(), (
        'a UI disse que comentou, mas a comunicação não persistiu'
    )

    tela.clicar_aba('Anexos')
    tela.clicar_link('Adicionar Anexo')
    tela.ver_titulo('Adicionar Anexo')
    tela.preencher_formulario([('Descrição', 'texto', 'Foto do painel da impressora'), ('Anexo', 'arquivo', 'arquivo.pdf')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Anexo adicionado com sucesso.')
    assert ChamadoAnexo.objects.filter(chamado=chamado, descricao='Foto do painel da impressora').exists(), (
        'a UI disse que anexou, mas o ChamadoAnexo não persistiu'
    )


def test_solicitante_adiciona_e_remove_outros_interessados(logado_central, chamado_em_atendimento):
    """Outros interessados entram pelo popup "Adicionar outros interessados" e saem pela rota de remoção.

    A remoção é POST-only e o botão vive num menu que só abre por hover; o teste chama a URL
    pela sessão do browser (mesmos cookies e CSRF) e confere a mensagem na página de volta — o que
    importa é que o vínculo sai do chamado.
    """
    chamado = chamado_em_atendimento
    interessado = usuario(PAPEIS['supervisor'])

    tela = Tela(logado_central('servidor')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_botao('Ações')
    tela.clicar_link('Adicionar outros interessados')
    popup = popup_em(tela, 'adicionar_outros_interessados')
    popup.preencher('Outros Interessados', 'autocomplete multiplo', PAPEIS['supervisor'])
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Adição de outros interessados realizada com sucesso.')
    assert chamado.outros_interessados.filter(pk=interessado.pk).exists(), 'o outro interessado não foi vinculado'

    resposta = postar(tela.pagina, REMOVER_OUTROS.format(chamado.pk, interessado.pk))
    assert resposta.status == 302, f'a remoção de interessado deveria redirecionar, respondeu HTTP {resposta.status}'
    tela = tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.sucesso('Interessado removido com sucesso.')
    assert not chamado.outros_interessados.filter(pk=interessado.pk).exists(), 'a UI disse que removeu, mas o vínculo continua'


def test_atendente_adiciona_nota_interna_e_grupo_de_interessados(logado_central, contexto_com_artigos, chamado_em_atendimento):
    """Nota interna (só para a equipe) e grupo de interessados (cópia para um conjunto de pessoas).

    O campo "Grupos de Interessado" só oferece os grupos vinculados ao grupo de atendimento do
    chamado — é por isso que o ``GrupoInteressado`` da fixture nasce apontando para ele.
    """
    from centralservicos.models import Comunicacao, GrupoInteressado

    chamado = chamado_em_atendimento
    grupo_interessados = GrupoInteressado.objects.create(
        titulo=f'E2E Central Grupo de Interessados {uuid4().hex[:8]}',
        grupo_atendimento=contexto_com_artigos.grupo_atendimento,
    )
    grupo_interessados.interessados.add(usuario(PAPEIS['supervisor']))
    texto = f'Equipamento reiniciado; seguindo com o diagnóstico. (e2e {uuid4().hex[:8]})'

    tela = Tela(logado_central('atendente')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')
    tela.clicar_aba('Notas Internas')
    tela.preencher_textarea('Adicionar Nota interna', texto)
    tela.clicar_botao('Adicionar Nota interna')
    tela.sucesso('Nota Interna adicionada com sucesso.')
    assert Comunicacao.objects.filter(chamado=chamado, remetente=usuario(PAPEIS['atendente']), tipo=Comunicacao.TIPO_NOTA_INTERNA).exists(), (
        'a UI disse que adicionou a nota, mas a comunicação não persistiu'
    )

    tela.clicar_botao('Ações')
    tela.clicar_link('Adicionar grupo de interessados')
    popup = popup_em(tela, 'adicionar_grupo_de_interessados')
    popup.preencher('Grupos de Interessado', 'checkbox multiplo', grupo_interessados.titulo)
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Adição de grupo de interessados realizada com sucesso.')
    assert chamado.outros_interessados.filter(pk=usuario(PAPEIS['supervisor']).pk).exists(), (
        'os membros do grupo de interessados deveriam entrar como outros interessados do chamado'
    )


def test_solicitante_arquiva_e_desarquiva_comentario(logado_central, chamado_em_atendimento):
    """Arquivar esconde o comentário na linha do tempo sem apagá-lo; desarquivar o traz de volta.

    Só o autor arquiva o próprio comentário (``arquivar_comentario``), e o botão de desarquivar só
    aparece para ele — o que o teste confere depois de cada POST.
    """
    from centralservicos.models import Comunicacao

    chamado = chamado_em_atendimento
    comentario = Comunicacao.objects.create(
        chamado=chamado,
        remetente=usuario(PAPEIS['servidor']),
        tipo=Comunicacao.TIPO_COMENTARIO,
        texto=f'Comentário que será arquivado. (e2e {uuid4().hex[:8]})',
    )

    tela = Tela(logado_central('servidor')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.ver_titulo(f'Chamado {chamado.pk}')

    resposta = postar(tela.pagina, ARQUIVAR.format(comentario.pk))
    assert resposta.status == 302, f'arquivar comentário deveria redirecionar, respondeu HTTP {resposta.status}'
    tela = tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.sucesso('Comentário arquivado com sucesso.')
    comentario.refresh_from_db()
    assert comentario.escondida_em is not None, 'a UI disse que arquivou, mas o comentário não ficou escondido'
    # O item arquivado nasce com `d-none` (`tab_linha_tempo.html:64`): o botão de desarquivar só
    # aparece depois de "Exibir comentários arquivados".
    tela.clicar_botao('Exibir comentários arquivados')
    assert tela.botao('Desarquivar comentário').is_visible(), 'o botão de desarquivar deveria aparecer para o autor'

    resposta = postar(tela.pagina, DESARQUIVAR.format(comentario.pk))
    assert resposta.status == 302, f'desarquivar comentário deveria redirecionar, respondeu HTTP {resposta.status}'
    tela = tela.ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.sucesso('Comentário desarquivado com sucesso.')
    comentario.refresh_from_db()
    assert comentario.escondida_em is None, 'a UI disse que desarquivou, mas o comentário continua escondido'


def test_listagem_de_chamados_a_fechar_mostra_o_resolvido(logado_central, chamado_resolvido):
    """A listagem "a fechar" é a porta do solicitante para concluir o chamado resolvido.

    Sem ela o chamado fica preso em Resolvido (o fechamento exige o solicitante), e é por isso que
    esta listagem existe: ela reúne os chamados que **este** usuário pode fechar.
    """
    tela = Tela(logado_central('servidor')).ir('/centralservicos/listar_chamados_a_fechar/')
    tela.ver_texto('Você poderá fechar os chamados desta listagem')
    tela.ver_texto(f'INC #{chamado_resolvido.pk}')
