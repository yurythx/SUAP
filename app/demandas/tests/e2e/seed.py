"""Replay ORM do substrato que o behave do Demandas monta antes dos fluxos de tela.

A carga reproduz os servidores das quatro features (demandante, analista, desenvolvedor,
servidores comuns, o coordenador de TI e o recebedor de demandas), a área de atuação com a
tag relacionada e o cadastro de analistas/desenvolvedores. Todas as operações são idempotentes
porque os e2e não dão flush e o CI reaproveita o banco entre execuções.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import Group

if TYPE_CHECKING:
    from rh.models import Servidor

# O behave criava estes servidores na tabela `Dado os seguintes usuários` da feature 001.
# O desenvolvedor e o recebedor não estão na tabela, mas são os papéis que o produto exige nas
# telas de entrega e nos relatórios — sem eles, metade das rotas fica inalcançável.
PAPEIS: dict[str, dict[str, str]] = {
    '105001': {'nome': 'Demandante', 'grupo': 'Demandante', 'setor': 'DIAC/CEN'},
    '105002': {'nome': 'Analista', 'grupo': 'Analista', 'setor': 'DIAC/CZN'},
    '105003': {'nome': 'Desenvolvedor', 'grupo': 'Desenvolvedor', 'setor': 'DIAC/CZN'},
    '105004': {'nome': 'ServidorComum', 'grupo': 'Servidor', 'setor': 'DIAC/CZN'},
    '105005': {'nome': 'ServidorComum2', 'grupo': 'Servidor', 'setor': 'DIAC/CZN'},
    '105006': {'nome': 'CoordenadorTI', 'grupo': 'Coordenador de TI sistêmico', 'setor': 'DIAC/CZN'},
    '105007': {'nome': 'RecebedorDemandas', 'grupo': 'Recebedor de Demandas', 'setor': 'DIAC/CZN'},
    '105008': {'nome': 'VisualizadorDemandas', 'grupo': 'Visualizador de Demandas', 'setor': 'DIAC/CZN'},
}


def criar_servidor(matricula: str) -> Servidor:
    """Cria ou recompõe um servidor com setor, senha e grupo da feature (factories, #17486)."""
    from djtools.e2e_fixtures import campus, servidor_com_login, setor

    dados = PAPEIS[matricula]
    sigla = dados['setor']  # DIAC/CEN ou DIAC/CZN
    lotacao = setor(sigla, campus(sigla.split('/')[1]))
    servidor = servidor_com_login(matricula, lotacao, staff=True, pessoa_fisica__nome=dados['nome'])
    usuario = servidor.get_user()
    assert usuario is not None, f'o servidor {matricula} não possui usuário'
    usuario.first_name = dados['nome']
    usuario.save()
    usuario.groups.set([Group.objects.get(name=dados['grupo'])])
    return servidor


def criar_area_e_tag() -> None:
    """Reproduz os cadastros básicos do módulo (área de atuação, tag e seus vínculos)."""
    from comum.models import AreaAtuacao, User
    from demandas.models import AreaAtuacaoDemanda, Tag

    area, _ = AreaAtuacao.objects.get_or_create(nome='Tecnologia da Informação')
    tag, _ = Tag.objects.update_or_create(nome='Tag Especial', defaults={'ativa': True})

    demandante = User.objects.get(username='105001')
    area_atuacao, _ = AreaAtuacaoDemanda.objects.get_or_create(area=area)
    area_atuacao.demandante_responsavel = demandante
    area_atuacao.recebe_sugestoes_publico_aluno = True
    area_atuacao.recebe_sugestoes_publico_servidor = True
    area_atuacao.recebe_sugestoes_publico_prestador_servico = True
    area_atuacao.save()
    area_atuacao.demandantes.add(demandante)
    area_atuacao.tags_relacionadas.set([tag])


def criar_analistas_desenvolvedores() -> None:
    """Cadastra os analistas/desenvolvedores que o painel de força-trabalho lista."""
    from comum.models import User
    from demandas.models import AnalistaDesenvolvedor

    for matricula, eh_analista in (('105002', True), ('105003', False)):
        usuario = User.objects.get(username=matricula)
        AnalistaDesenvolvedor.objects.update_or_create(
            usuario=usuario,
            defaults={'username_gitlab': matricula, 'eh_analista': eh_analista, 'eh_desenvolvedor': True, 'ativo': True},
        )


def criar_ambiente_homologacao() -> None:
    """Cria um ambiente de homologação sem tocar na API do GitLab.

    `AmbienteHomologacao.save()` cria um pipeline de verdade quando `pipeline` é nulo; com o
    número já preenchido o cadastro é puramente local, que é o que a tela precisa para ter o
    que listar.
    """
    from datetime import date

    from demandas.models import AmbienteHomologacao, AnalistaDesenvolvedor

    analista = AnalistaDesenvolvedor.objects.get(usuario__username='105003')
    AmbienteHomologacao.objects.update_or_create(
        branch='demandas-e2e',
        defaults={
            'criador': analista,
            'data_criacao': date(2019, 1, 21),
            'data_expiracao': date(2019, 12, 31),
            'senha': 'abcd',
            'pipeline': 1234,
            'url_gitlab': 'http://gitlab.ifrn.edu.br/suap/-/pipelines/1234',
            'ativo': True,
        },
    )


def criar_atualizacao_do_sistema() -> None:
    """Cria a atualização que as telas de atualização do sistema listam.

    A atualização nasce da conclusão de uma demanda (``gerar_atualizacao_demanda``), que só
    produz registro quando a área tem changelog configurado — sem esta carga, as duas telas de
    atualização ficam sem conteúdo para exibir.
    """
    from datetime import date

    from django.contrib.auth.models import Group

    from demandas.models import Atualizacao, Tag

    atualizacao, _ = Atualizacao.objects.update_or_create(
        descricao='Atualização E2E',
        defaults={'tipo': Atualizacao.FUNCIONALIDADE, 'detalhamento': 'Detalhamento E2E', 'data': date.today()},
    )
    atualizacao.tags.set([Tag.objects.get(nome='Tag Especial')])
    atualizacao.grupos.set([Group.objects.get(name='Servidor')])


def limpar_execucao_anterior() -> None:
    """Remove a cadeia de demandas e sugestões deixada por uma execução e2e anterior.

    As demandas não têm sentinela natural (o título é único por execução), então a limpeza é
    pelo conjunto inteiro: o banco de e2e é dedicado ao módulo.
    """
    from demandas.models import AmbienteHomologacao, Demanda, SugestaoMelhoria

    Demanda.objects.all().delete()
    SugestaoMelhoria.objects.all().delete()
    AmbienteHomologacao.objects.all().delete()


def montar() -> None:
    """Monta o substrato completo na ordem exigida pelos vínculos."""
    limpar_execucao_anterior()
    for matricula in PAPEIS:
        criar_servidor(matricula)
    criar_area_e_tag()
    criar_analistas_desenvolvedores()
    criar_ambiente_homologacao()
    criar_atualizacao_do_sistema()


__all__ = ['PAPEIS', 'montar']
