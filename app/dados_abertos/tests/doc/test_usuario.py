"""Roteiro navegado das tarefas do ``dados_abertos`` — a fonte de ``dados_abertos/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções existem para a
rodada falhar alto quando a tela mudou de forma: doc que descreve um passo que não existe
mais é pior que doc velha.

**É uma cadeia, e por natureza do domínio.** O PDA percorre cinco etapas em sequência e cada
uma só libera a seguinte: não há como capturar a Deliberação LAI sem uma base com recurso,
nem a aba CKAN sem a liberação do LAI. Os testes leem o registro que o anterior criou pela
chave fixa declarada no ``conftest``, e cada criador apaga o registro homônimo antes — assim
o ``--reruns 2`` do CI é seguro. Rodar um teste isolado falha com a mensagem dizendo qual
precisa vir antes.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest

from dados_abertos.tests.doc.conftest import (
    BASE_SLUG,
    BASE_TITULO,
    ORGANIZACAO_SLUG,
    ORGANIZACAO_TITULO,
    PDA_TITULO,
    RECURSO_NOME,
    TOPICO_TITULO,
)
from djtools.e2e_fixtures import abrir_popup
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ORGANIZACOES = '/admin/dados_abertos/organizacao/'
PDAS = '/admin/dados_abertos/planodadosabertos/'
BASES = '/admin/dados_abertos/basedados/'
VINCULOS = '/admin/dados_abertos/pdabasedados/'
GRUPOS = '/admin/dados_abertos/grupotrabalho/'
RESPONSAVEIS = '/admin/dados_abertos/responsavelgrupotrabalho/'
RECURSOS = '/admin/dados_abertos/recursodados/'
MARCACOES = '/admin/dados_abertos/marcacaopda/'
TOPICOS = '/admin/dados_abertos/topicodocumentopda/'
MATRIZ = '/dados_abertos/matriz_priorizacao/'
DELIBERACAO = '/dados_abertos/deliberacao_lai/'
AREA_PUBLICA = '/dados_abertos/publico/'


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela para a redação da doc (não é asserção)."""
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    sys.stderr.write(
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}\n'
    )


def _dashboard(pda) -> str:
    return f'/dados_abertos/{pda.pk}/dashboard/'


def _pda():
    from dados_abertos.models import PlanoDadosAbertos

    pda = PlanoDadosAbertos.objects.filter(titulo=PDA_TITULO).first()
    assert pda, f'PDA {PDA_TITULO!r} não existe — a cadeia começa em test_criar_o_pda_e_abrir_o_dashboard'
    return pda


def _base():
    from dados_abertos.models import BaseDados

    base = BaseDados.objects.filter(nome=BASE_SLUG).first()
    assert base, f'base {BASE_SLUG!r} não existe — rode test_cadastrar_a_base_e_vincular_ao_pda antes'
    return base


def _relacao():
    from dados_abertos.models import PDABaseDados

    relacao = PDABaseDados.objects.filter(pda=_pda(), base_dados=_base()).first()
    assert relacao, 'a base não está vinculada ao PDA — rode test_cadastrar_a_base_e_vincular_ao_pda antes'
    return relacao


def _acao(pda, titulo: str):
    """A ``PDAAcao`` do checklist deste PDA cujo título começa por ``titulo``."""
    from dados_abertos.models import PDAAcao

    acao = PDAAcao.objects.filter(pda=pda, acao__titulo__startswith=titulo).select_related('acao').first()
    assert acao, f'ação {titulo!r} não existe no checklist do PDA'
    return acao


def test_cadastrar_e_sincronizar_a_organizacao(logado_da, capturar, ckan_falso):
    """Tarefa 1 — o gestor cadastra a organização publicadora e a envia ao CKAN."""
    from dados_abertos.models import Organizacao

    Organizacao.objects.filter(nome=ORGANIZACAO_SLUG).delete()

    tela = Tela(logado_da('gestor')).ir(ORGANIZACOES)
    tela.ver_titulo('Organizações')
    _anotar('organizacao-listagem', tela)
    capturar(tela.pagina, 'organizacao-listagem')

    tela.clicar_botao('Adicionar Organização')
    _anotar('organizacao-formulario', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', ORGANIZACAO_TITULO),
            ('Descrição', 'textarea', 'Unidade responsável pela publicação dos dados abertos da instituição.'),
        ]
    )
    capturar(tela.pagina, 'organizacao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    organizacao = Organizacao.objects.filter(nome=ORGANIZACAO_SLUG).first()
    # O identificador é readonly no formulário (`OrganizacaoForm`): se ele existe com o slug
    # do título, foi o JS de auto-slug que o preencheu — é o que a doc afirma.
    assert organizacao is not None, f'a UI disse que salvou, mas não há organização com identificador {ORGANIZACAO_SLUG!r}'
    assert not organizacao.id_remoto, 'organização recém-cadastrada já veio com ID remoto'

    # Ícone de sincronizar da listagem. Clicado pelo href porque o `icon()` desta coluna é
    # montado sem título (`dados_abertos/admin/organizacao.py:74`) — o `title` sai "Remover",
    # e nenhum localizador por texto da camada `Tela` acha o alvo certo.
    tela.pagina.click(f'a[href="{ORGANIZACOES}{organizacao.pk}/sync/"]')
    tela.esperar()
    tela.sucesso('Organização sincronizada com sucesso.')
    capturar(tela.pagina, 'organizacao-sincronizada')

    organizacao.refresh_from_db()
    assert organizacao.id_remoto, 'a UI disse que sincronizou, mas o ID remoto continua vazio'
    assert organizacao.sincronizado_em, 'a UI disse que sincronizou, mas não gravou a data'
    assert 'organization_create' in ckan_falso.acoes(), f'o SUAP não criou a organização no CKAN: {ckan_falso.acoes()}'


def test_criar_o_pda_e_abrir_o_dashboard(logado_da, capturar):
    """Tarefa 2 — o gestor abre o Plano de Dados Abertos e vê o checklist nascer."""
    from dados_abertos.models import PDAAcao, PlanoDadosAbertos

    PlanoDadosAbertos.objects.filter(titulo=PDA_TITULO).delete()
    hoje = date.today()

    tela = Tela(logado_da('gestor')).ir(PDAS)
    tela.ver_titulo('Planos de Dados Abertos (PDA)')
    _anotar('pda-listagem', tela)
    tela.clicar_botao('Adicionar Plano de Dados Abertos (PDA)')
    _anotar('pda-formulario', tela)
    tela.preencher_formulario(
        [
            ('Título do PDA', 'texto', PDA_TITULO),
            ('Situação', 'lista', 'Rascunho'),
            ('Vigência - início', 'data', hoje.strftime('%d/%m/%Y')),
            ('Vigência - fim', 'data', (hoje + timedelta(days=730)).strftime('%d/%m/%Y')),
        ]
    )
    capturar(tela.pagina, 'pda-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    pda = PlanoDadosAbertos.objects.filter(titulo=PDA_TITULO).first()
    assert pda is not None, 'a UI disse que salvou, mas o PDA não persistiu'
    assert pda.versao_atual == '1.0.0', f'PDA novo nasceu na versão {pda.versao_atual}'
    assert not PDAAcao.objects.filter(pda=pda).exists(), 'o checklist foi criado antes da primeira visita ao dashboard'
    capturar(tela.pagina, 'pda-listagem')

    tela.ir(_dashboard(pda))
    tela.ver_titulo('Dashboard do Dados Abertos')
    _anotar('dashboard-etapas', tela)
    capturar(tela.pagina, 'dashboard-etapas')

    # O checklist é montado na PRIMEIRA visita ao dashboard, não no cadastro do PDA.
    assert PDAAcao.objects.filter(pda=pda).count() == 11, 'o dashboard não montou as 11 ações do checklist'
    pda.refresh_from_db()
    assert pda.etapa_atual is not None, 'o PDA ficou sem etapa atual'
    assert pda.etapa_atual.ordem == 1, f'o PDA não começou na etapa 1: {pda.etapa_atual}'


def test_definir_o_grupo_de_trabalho(logado_da, capturar):
    """Tarefa 3 — cadastro do grupo e do seu responsável; a etapa 1 fecha sozinha."""
    from dados_abertos.models import GrupoTrabalho

    pda = _pda()
    GrupoTrabalho.objects.filter(pda=pda).delete()

    tela = Tela(logado_da('gestor')).ir(GRUPOS)
    tela.ver_titulo('Grupos de Trabalho')
    tela.clicar_botao('Adicionar Grupo de Trabalho')
    _anotar('grupo-trabalho-formulario', tela)
    tela.preencher_formulario(
        [
            ('PDA', 'autocomplete', PDA_TITULO),
            ('Descrição', 'texto', 'Grupo de Trabalho de Dados Abertos'),
            ('Situação', 'lista', 'Ativo'),
        ]
    )
    capturar(tela.pagina, 'grupo-trabalho-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    grupo = GrupoTrabalho.objects.filter(pda=pda).first()
    assert grupo is not None, 'a UI disse que salvou, mas o grupo de trabalho não persistiu'

    # Grupo sem gente não fecha a etapa: a condição automática exige grupo ATIVO **com**
    # responsável ativo (`services/acoes_automaticas_service.py:_grupo_trabalho_definido`).
    tela.ir(_dashboard(pda))
    assert not _acao(pda, 'Definir grupo de trabalho').concluida, 'a etapa 1 fechou com grupo sem responsável'

    tela.ir(RESPONSAVEIS)
    tela.clicar_botao('Adicionar Responsável')
    _anotar('responsavel-formulario', tela)
    # `Grupo de Trabalho` é um `<select>` comum (o model não declara `SEARCH_FIELDS`, então o
    # admin não o rende como select2 com busca), ao contrário de PDA/Organização/Base.
    tela.preencher_formulario(
        [
            ('Grupo de Trabalho', 'lista', 'Grupo de Trabalho de Dados Abertos'),
            ('Responsável', 'autocomplete', 'Gestor Dados Abertos'),
        ]
    )
    capturar(tela.pagina, 'responsavel-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(_dashboard(pda))
    capturar(tela.pagina, 'dashboard-etapa-1-concluida')
    assert _acao(pda, 'Definir grupo de trabalho').concluida, 'a ação automática da etapa 1 não fechou'


def test_cadastrar_a_base_e_vincular_ao_pda(logado_da, capturar):
    """Tarefa 4 — cadastro do conjunto de dados e o vínculo com o PDA (com cronograma)."""
    from dados_abertos.models import BaseDados, PDABaseDados

    pda = _pda()
    PDABaseDados.objects.filter(base_dados__nome=BASE_SLUG).delete()
    BaseDados.objects.filter(nome=BASE_SLUG).delete()

    tela = Tela(logado_da('gestor')).ir(BASES)
    tela.ver_titulo('Bases de Dados')
    capturar(tela.pagina, 'base-listagem')
    tela.clicar_botao('Adicionar Base de Dados')
    _anotar('base-formulario', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', BASE_TITULO),
            ('Notas', 'textarea', 'Relação dos contratos administrativos vigentes, com objeto, valor e vigência.'),
            ('Organização', 'autocomplete', ORGANIZACAO_TITULO),
            ('Licença', 'autocomplete', 'Creative Commons'),
            ('Tema', 'autocomplete', 'Governo e Política'),
        ]
    )
    capturar(tela.pagina, 'base-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    base = BaseDados.objects.filter(nome=BASE_SLUG).first()
    assert base is not None, f'a UI disse que salvou, mas não há base com identificador {BASE_SLUG!r}'
    # A coluna Situação da listagem é o termômetro que a doc descreve.
    tela.ver_texto('Não vinculada a PDA')
    capturar(tela.pagina, 'base-listagem-nao-vinculada')

    tela.ir(VINCULOS)
    tela.ver_titulo('Bases de Dados no PDA')
    tela.clicar_botao('Adicionar Base de Dados no PDA')
    _anotar('vinculo-formulario', tela)
    tela.preencher_formulario(
        [
            ('PDA', 'autocomplete', PDA_TITULO),
            ('Base de Dados', 'autocomplete', BASE_TITULO),
            ('Meta/Prazo de Abertura', 'data', (date.today() + timedelta(days=90)).strftime('%d/%m/%Y')),
            ('Frequência de Atualização', 'lista', 'Mensal'),
        ]
    )
    capturar(tela.pagina, 'vinculo-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    assert PDABaseDados.objects.filter(pda=pda, base_dados=base).exists(), 'a UI disse que salvou, mas o vínculo não persistiu'

    tela.ir(_dashboard(pda))
    assert _acao(pda, 'Vincular os conjuntos de dados').concluida, 'a ação automática da etapa 2 não fechou'
    tela.clicar_aba('Plano de Ação')
    capturar(tela.pagina, 'dashboard-plano-de-acao')


def test_dispensar_a_consulta_publica(logado_da, capturar):
    """Tarefa 5 — a única etapa dispensável do fluxo, com justificativa auditável."""
    from dados_abertos.models import PDAEtapa

    pda = _pda()
    PDAEtapa.objects.filter(pda=pda).delete()

    tela = Tela(logado_da('gestor')).ir(_dashboard(pda))
    tela.clicar_botao('Pular etapa')
    tela.pagina.fill('textarea[id^="just-"]', 'Não houve consulta pública neste ciclo: as bases foram indicadas pelo grupo de trabalho.')
    capturar(tela.pagina, 'dashboard-pular-etapa')
    tela.clicar_botao('Confirmar dispensa')
    # A dispensa vai por `fetch` e recarrega a página no `.then` — `esperar()` (que observa o
    # jQuery) não a alcança. O que marca o fim é a tarja na tela recarregada.
    tela.ver_texto('Etapa dispensada')

    dispensa = PDAEtapa.objects.filter(pda=pda).select_related('etapa').first()
    assert dispensa is not None, 'a UI disse que dispensou, mas a dispensa não persistiu'
    assert dispensa.etapa.ordem == 3, f'a etapa dispensada não foi a 3: {dispensa.etapa}'
    auditoria = (dispensa.justificativa, dispensa.ip, dispensa.user_agent)
    assert all(auditoria), f'a dispensa não registrou a auditoria (justificativa, IP, navegador): {auditoria}'

    tela.ver_botao('Reativar etapa')
    capturar(tela.pagina, 'dashboard-etapa-dispensada')


def test_priorizar_as_bases_na_matriz(logado_da, capturar):
    """Tarefa 6 — preencher e finalizar a matriz de priorização."""
    from dados_abertos.models import AvaliacaoBaseDados, CriterioMatriz

    pda = _pda()
    base = _base()
    AvaliacaoBaseDados.objects.filter(base_dados=base).delete()
    criterios = list(CriterioMatriz.objects.filter(ativo=True))
    assert criterios, 'nenhum critério ativo: a matriz sairia sem colunas'

    tela = Tela(logado_da('gestor')).ir(f'{MATRIZ}?pda={pda.pk}')
    tela.ver_titulo('Matriz de Priorização de PDAs')
    _anotar('matriz', tela)
    capturar(tela.pagina, 'matriz-vazia')

    # Os selects da matriz não têm `label` (o nome é `nota_<base>_<criterio>`), então a camada
    # `Tela`, que endereça por rótulo, não os alcança — vão pelo `name`.
    for criterio in criterios:
        tela.pagina.select_option(f'select[name="nota_{base.pk}_{criterio.pk}"]', label='Alto' if criterio.pk % 2 else 'Médio')
    capturar(tela.pagina, 'matriz-preenchida')
    tela.clicar_botao('Salvar')
    tela.sucesso('Notas salvas com sucesso.')
    assert AvaliacaoBaseDados.objects.filter(base_dados=base).count() == len(criterios), 'a UI disse que salvou, mas as notas não persistiram'

    tela.clicar_botao('Finalizar')
    tela.sucesso('Avaliações finalizadas com sucesso.')
    assert not AvaliacaoBaseDados.objects.filter(base_dados=base, finalizado=False).exists(), 'a UI disse que finalizou, mas há avaliação em aberto'
    tela.ver_texto('foram avaliadas')
    capturar(tela.pagina, 'matriz-finalizada')

    tela.ir(_dashboard(pda))
    assert _acao(pda, 'Finalizar a matriz').concluida, 'a ação automática da etapa 4 não fechou'


def test_cadastrar_o_recurso_e_enviar_ao_lai(logado_da, capturar, arquivo_csv):
    """Tarefa 7 — anexar o arquivo que vai ao ar; a etapa 5 manda a base para o LAI."""
    from dados_abertos.enums import SituacaoLAI
    from dados_abertos.models import RecursoDados

    pda = _pda()
    base = _base()
    RecursoDados.objects.filter(dataset=base).delete()

    tela = Tela(logado_da('gestor')).ir(RECURSOS)
    tela.ver_titulo('Recursos')
    tela.clicar_botao('Adicionar Recurso')
    _anotar('recurso-formulario', tela)
    tela.preencher_formulario(
        [
            ('Base de Dados', 'autocomplete', BASE_TITULO),
            ('Nome', 'texto', RECURSO_NOME),
            ('Descrição', 'textarea', 'Extração mensal dos contratos vigentes.'),
            ('Formato', 'lista', 'CSV'),
        ]
    )
    # `set_input_files` direto: os arquivos de upload da camada `Tela` são pdf/docx/png/jpg, e
    # a prévia da Deliberação LAI precisa de um CSV de verdade para ter o que mostrar.
    tela.campo('Arquivo', 'arquivo').first.set_input_files(arquivo_csv)
    capturar(tela.pagina, 'recurso-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    recurso = RecursoDados.objects.filter(dataset=base, nome=RECURSO_NOME).first()
    assert recurso is not None, 'a UI disse que salvou, mas o recurso não persistiu'
    assert recurso.arquivo, 'o recurso ficou sem arquivo anexado'

    tela.ir(_dashboard(pda))
    capturar(tela.pagina, 'dashboard-etapa-5')
    assert _acao(pda, 'Cadastrar recurso').concluida, 'a ação automática de recurso não fechou'
    pda.refresh_from_db()
    assert pda.etapa_atual is not None, 'o PDA ficou sem etapa atual'
    assert pda.etapa_atual.ordem == 5, f'o fluxo não chegou à etapa 5: {pda.etapa_atual}'
    # A etapa 5 dispara a análise: a visita ao dashboard move para EM_ANALISE as bases
    # pendentes que já têm recurso.
    assert _relacao().situacao_lai == SituacaoLAI.EM_ANALISE, 'a base não foi enviada à análise do LAI ao chegar na etapa 5'


def test_deliberar_sobre_a_base(logado_da, capturar):
    """Tarefa 8 — o Responsável LAI libera a base; editar a base depois anula a liberação."""
    from dados_abertos.enums import SituacaoLAI, TipoEventoLAI
    from dados_abertos.models import DeliberacaoLAI

    pda = _pda()
    relacao = _relacao()

    tela = Tela(logado_da('lai')).ir(f'{DELIBERACAO}?pda={pda.pk}')
    tela.ver_titulo('Deliberação LAI')
    _anotar('deliberacao-lai', tela)
    # A prévia é lida do arquivo anexado: sem ela o LAI não teria o que avaliar.
    tela.ver_texto('prévia dos primeiros 5 registros')
    capturar(tela.pagina, 'deliberacao-lai')

    tela.pagina.fill(f'#parecer_{relacao.pk}', 'Conteúdo conferido: não há dado pessoal nem informação sigilosa.')
    tela.clicar_botao('Liberar')
    tela.sucesso('Deliberação registrada.')
    capturar(tela.pagina, 'deliberacao-lai-liberada')

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.LIBERADO, 'a UI disse que liberou, mas a situação não mudou'
    assert DeliberacaoLAI.objects.filter(pda_base_dados=relacao, tipo=TipoEventoLAI.LIBERACAO).exists(), 'a deliberação não virou registro'

    # A liberação é anulada por edição — executado, não deduzido: o gestor muda as notas da
    # base e a relação volta para análise, com o motivo escrito na tela do LAI.
    gestor = Tela(logado_da('gestor')).ir(f'{BASES}{_base().pk}/change/')
    gestor.preencher('Notas', 'textarea', 'Relação dos contratos vigentes, atualizada com o campo de vigência.')
    gestor.clicar_botao('Salvar')
    gestor.sucesso('Atualização realizada com sucesso.')

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE, 'editar o conteúdo da base não anulou a liberação do LAI'
    assert relacao.motivo_reabertura.startswith('Reaberto por edição'), f'motivo inesperado: {relacao.motivo_reabertura!r}'

    tela.ir(f'{DELIBERACAO}?pda={pda.pk}')
    tela.ver_texto('Reaberto por edição do conteúdo')
    capturar(tela.pagina, 'deliberacao-lai-reaberta')
    tela.pagina.fill(f'#parecer_{relacao.pk}', 'Reanálise após ajuste na descrição: liberado.')
    tela.clicar_botao('Liberar')
    tela.sucesso('Deliberação registrada.')
    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.LIBERADO, 'a base não voltou a ficar liberada'


def test_sincronizar_a_base_com_o_ckan(logado_da, capturar, ckan_falso):
    """Tarefa 9 — o envio ao CKAN pela aba do dashboard, e o checklist chegando a 100%."""
    from dados_abertos.enums import SituacaoLAI

    pda = _pda()
    base = _base()

    tela = Tela(logado_da('gestor')).ir(_dashboard(pda))
    tela.clicar_aba('CKAN')
    tela.ver_texto('Aguardando primeira sincronização')
    _anotar('dashboard-ckan', tela)
    capturar(tela.pagina, 'dashboard-ckan-antes')

    tela.clicar_botao('Sincronizar')
    tela.esperar()
    tela.sucesso('Sincronização com o CKAN concluída.')

    base.refresh_from_db()
    assert base.id_remoto, 'a UI disse que sincronizou, mas a base não guardou o ID remoto'
    assert base.sincronizado_em, 'a UI disse que sincronizou, mas a base não guardou a data'
    recurso = base.recursos.first()
    assert recurso is not None, 'a base perdeu o recurso'
    assert recurso.id_remoto, 'os recursos da base não foram enviados junto'

    # O conjunto sobe ao CKAN com o DONO preenchido a partir do ID remoto da organização —
    # afirmação da doc, aqui medida no payload que o SUAP enviou.
    criacoes = [dados for acao, dados in ckan_falso.chamadas if acao == 'package_create']
    assert criacoes, f'o SUAP não criou o conjunto no CKAN: {ckan_falso.acoes()}'
    assert criacoes[0]['owner_org'] == base.organizacao.id_remoto, f'o conjunto foi ao CKAN sem o dono certo: {criacoes[0]["owner_org"]!r}'

    tela.ir(_dashboard(pda))
    tela.clicar_aba('CKAN')
    tela.ver_texto('Dataset e recursos sincronizados')
    capturar(tela.pagina, 'dashboard-ckan-sincronizado')
    assert _acao(pda, 'Sincronização').concluida, 'a última ação obrigatória não fechou'

    # MEDIDO nesta rodada: sincronizar NÃO reabre a análise do LAI. Gravar `id_remoto` e
    # `sincronizado_em` é registro da publicação, não alteração do dado publicado — então a
    # liberação continua valendo e o checklist fecha direto. (Antes o `RecursoDados.save()`
    # reabria em todo save, e o plano só chegava a 100% com uma reanálise sem objeto.)
    relacao = _relacao()
    assert relacao.situacao_lai == SituacaoLAI.LIBERADO, 'sincronizar reabriu a análise do LAI sem o conteúdo ter mudado'
    pendentes = list(
        _pda()
        .acoes.filter(acao__obrigatoria=True, concluida=False)
        .exclude(acao__etapa_id__in=_pda().etapas_puladas_ids())
        .values_list('acao__titulo', flat=True)
    )
    assert pendentes == [], f'obrigatórias pendentes inesperadas depois do envio: {pendentes}'

    tela.ir(_dashboard(pda))
    assert _pda().get_progresso_geral() == 100, f'o progresso geral não chegou a 100%: {_pda().get_progresso_geral()}'
    tela.ver_texto('Concluído')
    capturar(tela.pagina, 'dashboard-concluido')


def test_montar_o_documento_do_pda(logado_da, capturar):
    """Tarefa 10, etapa 1 — tópicos do documento e a marcação que vira conteúdo vivo."""
    from dados_abertos.models import MarcacaoPDA, TopicoDocumentoPDA

    pda = _pda()
    marcacao = '[matriz_priorizacao]'
    MarcacaoPDA.objects.filter(marcacao=marcacao).delete()
    TopicoDocumentoPDA.objects.filter(pda=pda, titulo=TOPICO_TITULO).delete()

    tela = Tela(logado_da('gestor')).ir(MARCACOES)
    tela.ver_titulo('Marcações do PDA')
    tela.clicar_botao('Adicionar Marcação do PDA')
    _anotar('marcacao-formulario', tela)
    tela.preencher_formulario([('Marcação', 'texto', marcacao), ('Template Base', 'texto', 'matriz_priorizacao_marcacao')])
    capturar(tela.pagina, 'marcacao-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(TOPICOS)
    tela.clicar_botao('Adicionar Tópico do documento do PDA')
    _anotar('topico-formulario', tela)
    tela.preencher_formulario(
        [
            ('PDA', 'autocomplete', PDA_TITULO),
            ('Título do tópico', 'texto', TOPICO_TITULO),
            ('Conteúdo', 'texto rico', f'As bases priorizadas neste plano são as da matriz abaixo. {marcacao}'),
            ('Ordem no documento', 'número', '1'),
        ]
    )
    capturar(tela.pagina, 'topico-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    topico = TopicoDocumentoPDA.objects.filter(pda=pda, titulo=TOPICO_TITULO).first()
    assert topico is not None, 'a UI disse que salvou, mas o tópico não persistiu'
    formatado = topico.get_conteudo_formatado()
    assert marcacao not in formatado, 'a marcação saiu literal no documento — o template base não casou'
    assert BASE_TITULO in formatado or BASE_SLUG in formatado, 'a marcação não trouxe a matriz do plano'


def test_gerar_a_versao_e_conferir_a_area_publica(page, logado_da, capturar):
    """Tarefa 10, etapa 2 — gerar a versão do documento e conferir a área pública."""
    from dados_abertos.models import VersaoPDA

    pda = _pda()
    versoes_antes = VersaoPDA.objects.filter(pda=pda).count()

    tela = Tela(logado_da('gestor')).ir(PDAS)
    popup = Tela(tela.pagina, abrir_popup(tela.pagina, 'Nova versão').locator('body'))
    _anotar('nova-versao', popup)
    popup.preencher_formulario(
        [
            ('Tipo de versão', 'lista', 'Minor - Adição/remoção relevante'),
            ('Justificativa da versão', 'textarea', 'Inclusão das bases priorizadas e do cronograma de abertura.'),
        ]
    )
    capturar(tela.pagina, 'pda-nova-versao')
    # "Enviar" e não "Salvar": o botão vem do `render_form`, e `CriarVersaoPDAForm` não é
    # ModelForm — sem `SUBMIT_LABEL`, o template cai no rótulo padrão.
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Versão do PDA criada com sucesso.')

    assert VersaoPDA.objects.filter(pda=pda).count() == versoes_antes + 1, 'a UI disse que versionou, mas a versão não persistiu'
    pda.refresh_from_db()
    assert pda.versao_atual == '1.1.0', f'a versão Minor não avançou como a doc afirma: {pda.versao_atual}'

    publica = Tela(page).ir(AREA_PUBLICA)
    publica.ver_texto(PDA_TITULO)
    _anotar('area-publica', publica)
    capturar(page, 'area-publica')
