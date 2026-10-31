from behave import given

from avaliacao_integrada.models import EscalaLikert, NivelEscalaLikert, Segmento
from comum.models import Ano


@given('os dados básicos para avaliacao integrada')
def step_dados_basicos_aval_int(context):
    Ano.objects.get_or_create(ano=2020)

    Segmento.objects.get_or_create(descricao='CPA_CENTRAL', tipo=Segmento.TIPO_PUBLICO_INTERNO)
    Segmento.objects.get_or_create(descricao='CPA_CAMPUS', tipo=Segmento.TIPO_PUBLICO_INTERNO)
    Segmento.objects.get_or_create(descricao='GESTOR', tipo=Segmento.TIPO_PUBLICO_INTERNO)
    Segmento.objects.get_or_create(descricao='TECNICO', tipo=Segmento.TIPO_PUBLICO_INTERNO)
    Segmento.objects.get_or_create(descricao='ETEP', tipo=Segmento.TIPO_PUBLICO_INTERNO)
    Segmento.objects.get_or_create(descricao='DOCENTE', tipo=Segmento.TIPO_PUBLICO_INTERNO)
    Segmento.objects.get_or_create(descricao='ESTUDANTE', tipo=Segmento.TIPO_PUBLICO_INTERNO)
    Segmento.objects.get_or_create(descricao='DESLIGADO', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
    Segmento.objects.get_or_create(descricao='ALUNO_EGRESSO', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
    Segmento.objects.get_or_create(descricao='PAIS', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
    Segmento.objects.get_or_create(descricao='EMPRESA_PRESTADORA_SERVICO', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
    Segmento.objects.get_or_create(descricao='OUTRO_SOCIEDADE_CIVIL', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
    Segmento.objects.get_or_create(descricao='PROFISSIONAL_PRESTADOR_SERVICO', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)
    Segmento.objects.get_or_create(descricao='SUPERVISOR_ESTAGIO', tipo=Segmento.TIPO_SOCIEDADE_CIVIL)

    escala, _created = EscalaLikert.objects.get_or_create(nome='Escala Padrão', ativo=True)
    NivelEscalaLikert.objects.get_or_create(
        escala=escala, nivel=0, descricao='Desconheço', emoji='😶', tipo_criterio=NivelEscalaLikert.CRITERIO_DESCONHECO
    )
    NivelEscalaLikert.objects.get_or_create(
        escala=escala, nivel=1, descricao='Discordo', emoji='☹️', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO
    )
    NivelEscalaLikert.objects.get_or_create(
        escala=escala, nivel=2, descricao='Discordo parcialmente', emoji='😐', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE
    )
    NivelEscalaLikert.objects.get_or_create(
        escala=escala, nivel=3, descricao='Concordo parcialmente', emoji='🙂', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE
    )
    NivelEscalaLikert.objects.get_or_create(
        escala=escala, nivel=4, descricao='Concordo', emoji='😃', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO
    )
