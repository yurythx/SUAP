from behave import given

from demandas_externas.models import PublicoAlvo, TipoAcao
from edu.models import Cidade, Estado
from projetos.models import AreaTematica


@given('os dados básicos para a demanda externa')
def step_dados_basicos_demanda_externa(context):
    PublicoAlvo.objects.get_or_create(descricao='Associação')[0]
    PublicoAlvo.objects.get_or_create(descricao='Câmara de Vereadores')[0]
    PublicoAlvo.objects.get_or_create(descricao='Centro Comunitário')[0]
    PublicoAlvo.objects.get_or_create(descricao='Comunidade Rural')[0]
    PublicoAlvo.objects.get_or_create(descricao='Cooperativa')[0]
    PublicoAlvo.objects.get_or_create(descricao='Distrito')[0]
    PublicoAlvo.objects.get_or_create(descricao='Escola Estadual')[0]
    rn = Estado.objects.get_or_create(id=24, nome='Rio Grande do Norte')[0]
    Cidade.objects.get_or_create(nome='Natal Demandas', estado=rn)[0]
    Cidade.objects.get_or_create(nome='Parnamirim', estado=rn)[0]
    Cidade.objects.get_or_create(nome='Macaíba', estado=rn)[0]

    TipoAcao.objects.get_or_create(descricao='Curso')[0]
    TipoAcao.objects.get_or_create(descricao='Evento')[0]
    TipoAcao.objects.get_or_create(descricao='Projeto')[0]

    AreaTematica.objects.get_or_create(descricao='Multidisciplinar')[0]
    AreaTematica.objects.get_or_create(descricao='Cultura')[0]
    AreaTematica.objects.get_or_create(descricao='Educação')[0]
