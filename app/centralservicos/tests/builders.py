from dataclasses import dataclass

from django.apps.registry import apps
from django.utils import timezone

from rh.tests.factories import ServidorFactory


Group = apps.get_model('auth', 'Group')
AreaAtuacao = apps.get_model('comum', 'AreaAtuacao')
CategoriaServico = apps.get_model('centralservicos', 'CategoriaServico')
GrupoServico = apps.get_model('centralservicos', 'GrupoServico')
Servico = apps.get_model('centralservicos', 'Servico')
CentroAtendimento = apps.get_model('centralservicos', 'CentroAtendimento')
GrupoAtendimento = apps.get_model('centralservicos', 'GrupoAtendimento')
Chamado = apps.get_model('centralservicos', 'Chamado')
BaseConhecimento = apps.get_model('centralservicos', 'BaseConhecimento')


@dataclass
class CentralServicosContext:
    client: object
    servidor_atendente: object
    servidor_solicitante: object
    campus_referencia: object
    area: object
    servico: object
    centro_atendimento: object
    chamado: object
    base_conhecimento: object


def criar_contexto_centralservicos(client) -> CentralServicosContext:
    # Os dois atores no mesmo campus: o grupo de atendimento e o chamado são por campus,
    # e o `campus_referencia` é o deles.
    servidor_atendente = ServidorFactory()
    servidor_solicitante = ServidorFactory(setor=servidor_atendente.setor)
    campus_referencia = servidor_atendente.setor.uo

    atendente = servidor_atendente.get_user()
    solicitante = servidor_solicitante.get_user()
    atendente.groups.add(Group.objects.get(name='Atendente da Central de Serviços'))
    atendente.groups.add(Group.objects.get(name='Publicador da Base de Conhecimento'))
    solicitante.groups.add(Group.objects.get(name='Aluno'))

    area = AreaAtuacao.objects.create(nome='Area Teste')
    categoria = CategoriaServico.objects.create(nome='Categoria Servico 01', area=area)
    grupo_servico = GrupoServico.objects.create(
        nome='Grupo Servico 01', detalhamento='Bibendum ducimus reiciendis quod similique, ipsa recusandae condimentum elementum?'
    )
    grupo_servico.categorias.add(categoria)

    centro_atendimento = CentroAtendimento.objects.create(nome='Centro de Atendimento 01', eh_local=True, area=area)
    servico = Servico.objects.create(nome='Servico 01', tipo=Servico.TIPO_REQUISICAO, area=area, grupo_servico=grupo_servico)
    servico.centros_atendimento.add(centro_atendimento)

    grupo_atendimento = GrupoAtendimento.objects.create(nome='Grupo Atendimento 01', campus=campus_referencia, centro_atendimento=centro_atendimento)
    grupo_atendimento.responsaveis.add(atendente)
    grupo_atendimento.atendentes.add(atendente)

    chamado = Chamado(
        descricao='Abertura de chamado padrao. Testes iniciais.',
        servico=servico,
        aberto_em=timezone.now(),
        aberto_por=solicitante,
        interessado=solicitante,
        requisitante=solicitante,
        campus=campus_referencia,
        meio_abertura=Chamado.MEIO_ABERTURA_TELEFONE,
    )
    chamado.centro_atendimento = centro_atendimento
    chamado.save()

    base_conhecimento = BaseConhecimento.objects.create(
        titulo='Esse, voluptatibus omnis illum autem aut illum.',
        resumo='Class unde in architecto eum nostrud neque nisi sem',
        area=area,
        atualizado_por=atendente,
    )
    base_conhecimento.grupos_atendimento.add(grupo_atendimento)
    base_conhecimento.servicos.add(servico)

    return CentralServicosContext(
        client=client,
        servidor_atendente=servidor_atendente,
        servidor_solicitante=servidor_solicitante,
        campus_referencia=campus_referencia,
        area=area,
        servico=servico,
        centro_atendimento=centro_atendimento,
        chamado=chamado,
        base_conhecimento=base_conhecimento,
    )
