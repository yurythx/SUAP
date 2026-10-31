import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from comum.models import User
from comum.tests.factories import UserFactory
from demandas.models import Demanda
from demandas.services import DemandaMarkdownExportService
from demandas.tests.factories import DoDFactory, EspecificacaoFactory, RevisaoEspecificacaoFactory
from demandas.views import exportar_markdown


@pytest.mark.django_db(databases='__all__')
def test_gera_markdown_com_dados_basicos_consolidacao_e_especificacoes(demanda: Demanda) -> None:
    dod = DoDFactory(
        demanda=demanda,
        descricao='<p>Consolidação <strong>principal</strong></p>',
        detalhamento='<p>Detalhe<br>importante</p>',
        envolvidos='Gestores\nOperadores',
    )
    EspecificacaoFactory(dod=dod, nome='Exportar contexto', atividades='<p>Permitir copiar</p><ul><li>Markdown</li></ul>', ordem=1)

    markdown = DemandaMarkdownExportService.gerar(demanda)

    assert f'# Demanda {demanda.pk}: Melhorar o relatório X' in markdown
    assert '<p>Consolidação' not in markdown
    assert '- **ID:**' in markdown
    assert '- **Título:** Melhorar o relatório X' in markdown
    assert '- **Tipo:** Funcionalidade' in markdown
    assert '## Descrição da Demanda' not in markdown
    assert demanda.descricao not in markdown
    assert '## Consolidação' in markdown
    assert 'Consolidação principal' in markdown
    assert '### Detalhamento' in markdown
    assert 'Detalhe\nimportante' in markdown
    assert '### Grupos de Usuários Envolvidos' not in markdown
    assert 'Gestores' not in markdown
    assert '## Especificações da Consolidação' in markdown
    assert '### Especificação 1: Exportar contexto' in markdown
    assert 'Permitir copiar\n- Markdown' in markdown
    assert '## Comentários' not in markdown


@pytest.mark.django_db(databases='__all__')
def test_texto_rico_preserva_links_e_listas(demanda: Demanda) -> None:
    dod = DoDFactory(demanda=demanda, descricao='<p>Veja <a href="https://suap.ifrn.edu.br">SUAP</a></p>')
    EspecificacaoFactory(
        dod=dod,
        nome='Fluxo',
        atividades='<ol><li>Primeiro passo</li><li>Abrir <a href="https://gitlab.ifrn.edu.br">GitLab</a></li></ol>',
        ordem=1,
    )

    markdown = DemandaMarkdownExportService.gerar(demanda)

    assert '[SUAP](https://suap.ifrn.edu.br)' in markdown
    assert '1. Primeiro passo' in markdown
    assert '2. Abrir [GitLab](https://gitlab.ifrn.edu.br)' in markdown


@pytest.mark.django_db(databases='__all__')
def test_exportar_markdown_bloqueia_usuario_sem_permissao(demanda: Demanda) -> None:
    usuario_sem_permissao = UserFactory(username='sem_permissao')
    request = RequestFactory().get('/')
    request.user = usuario_sem_permissao

    with pytest.raises(PermissionDenied):
        exportar_markdown(request, demanda.pk)


@pytest.mark.django_db(databases='__all__')
def test_exportar_markdown_oculta_consolidacao_quando_usuario_nao_tem_visibilidade(demanda: Demanda) -> None:
    usuario = UserFactory(username='visualizador')
    content_type = ContentType.objects.get_for_model(Demanda)
    usuario.user_permissions.add(Permission.objects.get(content_type=content_type, codename='view_demanda'))
    DoDFactory(demanda=demanda, descricao='Consolidação restrita')
    request = RequestFactory().get('/')
    request.user = usuario

    response = exportar_markdown(request, demanda.pk)

    assert response.status_code == 200
    markdown = response.content.decode()
    assert '## Consolidação' not in markdown
    assert '## Especificações da Consolidação' not in markdown
    assert 'Consolidação restrita' not in markdown


@pytest.mark.django_db(databases='__all__')
def test_exportar_markdown_inclui_especificacao_tecnica_mesmo_sem_consolidacao_visivel(demanda: Demanda) -> None:
    usuario = UserFactory(username='atendente')
    content_type = ContentType.objects.get_for_model(Demanda)
    usuario.user_permissions.add(Permission.objects.get(content_type=content_type, codename='view_demanda'))
    usuario.user_permissions.add(Permission.objects.get(content_type=content_type, codename='atende_demanda'))
    DoDFactory(demanda=demanda, descricao='Consolidação')
    demanda.especificacao_tecnica = '<p>Detalhes técnicos internos</p>'
    demanda.save()
    request = RequestFactory().get('/')
    request.user = usuario

    response = exportar_markdown(request, demanda.pk)

    markdown = response.content.decode()
    assert '## Consolidação' not in markdown
    assert '## Especificação Técnica' in markdown
    assert 'Detalhes técnicos internos' in markdown


@pytest.mark.django_db(databases='__all__')
def test_exportar_markdown_download_define_content_disposition(demanda: Demanda) -> None:
    usuario = UserFactory(username='visualizador_download')
    content_type = ContentType.objects.get_for_model(Demanda)
    usuario.user_permissions.add(Permission.objects.get(content_type=content_type, codename='view_demanda'))
    request = RequestFactory().get('/?download=1')
    request.user = usuario

    response = exportar_markdown(request, demanda.pk)

    assert response['Content-Disposition'].startswith(f'attachment; filename=demanda-{demanda.pk}-')
    assert response['Content-Disposition'].endswith('.md')


@pytest.mark.django_db(databases='__all__')
def test_analista_da_demanda_pode_exportar_contexto_independente_da_etapa(demanda: Demanda, usuario: User) -> None:
    demanda.analistas.add(usuario)

    assert demanda.eh_analista(usuario)
    assert not demanda.pode_revisar_consolidacao(usuario)


@pytest.mark.django_db(databases='__all__')
def test_gera_markdown_com_revisao_de_especificacao_existente_quando_visivel_para_analista(demanda: Demanda) -> None:
    dod = DoDFactory(demanda=demanda, descricao='Consolidação')
    especificacao = EspecificacaoFactory(dod=dod, nome='Título atual', atividades='Texto atual', ordem=1)
    RevisaoEspecificacaoFactory(dod=dod, especificacao=especificacao, nome='Título revisado', atividades='Texto revisado')

    markdown = DemandaMarkdownExportService.gerar(demanda, exibir_revisoes_de_especificacoes=True)

    assert 'Novo título: Título revisado' in markdown
    assert 'Texto revisado' in markdown


@pytest.mark.django_db(databases='__all__')
def test_gera_markdown_oculta_revisao_sem_especificacao_quando_nao_esta_visivel(demanda: Demanda) -> None:
    dod = DoDFactory(demanda=demanda, descricao='Consolidação')
    RevisaoEspecificacaoFactory(dod=dod, nome='Nova revisão restrita', atividades='Texto restrito')

    markdown = DemandaMarkdownExportService.gerar(demanda, exibir_revisoes_sem_especificacao=False)

    assert 'Nova especificação: Nova revisão restrita' not in markdown
    assert 'Texto restrito' not in markdown


@pytest.mark.django_db(databases='__all__')
def test_gera_markdown_com_revisao_sem_especificacao_quando_visivel_para_analista_da_demanda(demanda: Demanda) -> None:
    dod = DoDFactory(demanda=demanda, descricao='Consolidação')
    RevisaoEspecificacaoFactory(dod=dod, nome='Nova revisão visível', atividades='Texto visível')

    markdown = DemandaMarkdownExportService.gerar(demanda, exibir_revisoes_sem_especificacao=True)

    assert '### Nova especificação: Nova revisão visível' in markdown
    assert 'Texto visível' in markdown
