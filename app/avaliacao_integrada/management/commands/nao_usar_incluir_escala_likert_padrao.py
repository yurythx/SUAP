from avaliacao_integrada.models import EscalaLikert, NivelEscalaLikert
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, **options):
        # GRAU_SATISFACAO = 9 - Grau de Satisfação
        escala, _created = EscalaLikert.objects.get_or_create(nome='Escala Grau Satisfação', ativo=True)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=0, descricao='Desconheço', tipo_criterio=NivelEscalaLikert.CRITERIO_DESCONHECO)
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=1, descricao='Muito insatisfeito', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO
        )
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=2, descricao='Insatisfeito', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE
        )
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=3, descricao='Neutro', tipo_criterio=NivelEscalaLikert.CRITERIO_NAO_SE_APLICA)
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=4, descricao='Satisfeito', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE
        )
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=5, descricao='Muito satisfeito', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO
        )
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=9, descricao='Não se aplica', tipo_criterio=NivelEscalaLikert.CRITERIO_NAO_SE_APLICA
        )

        # FAIXA_NUMERICA = 8 - Escala Padrão (Faixa Numérica)
        escala, _created = EscalaLikert.objects.get_or_create(nome='Escala Faixa Númerica', ativo=True)
        # Desconheço, 1 - Muito insatisfeito, 2 - Insatisfeito, 3 - Neutro, 4 - Satisfeito, 5 - Muito satisfeito, Não se aplica.
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=0, descricao='Desconheço', tipo_criterio=NivelEscalaLikert.CRITERIO_DESCONHECO)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=1, descricao='1', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=2, descricao='2', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=3, descricao='3', tipo_criterio=NivelEscalaLikert.CRITERIO_NAO_SE_APLICA)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=4, descricao='4', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=5, descricao='5', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO)
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=9, descricao='Não se aplica', tipo_criterio=NivelEscalaLikert.CRITERIO_NAO_SE_APLICA
        )

        escala, _created = EscalaLikert.objects.get_or_create(nome='Grau Satisfação 2022', ativo=True)
        # Desconheço, 1 - NÃO EXISTE (embora devesse existir), 2 - INSUFICIENTE , 3 - SUFICIENTE/REGULAR, 4 - muito bom, 5 - excelente, Não se aplica
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=0, descricao='Desconheço', tipo_criterio=NivelEscalaLikert.CRITERIO_DESCONHECO)
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=1, descricao='Não Existe', tipo_criterio=NivelEscalaLikert.CRITERIO_NAO_SE_APLICA
        )
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=2, descricao='Discordo', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO)
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=3, descricao='Discordo parcialmente', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE
        )
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=4, descricao='Concordo parcialmente', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE
        )
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=5, descricao='Concordo', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO)
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=9, descricao='Não se aplica', tipo_criterio=NivelEscalaLikert.CRITERIO_NAO_SE_APLICA
        )

        escala, _created = EscalaLikert.objects.get_or_create(nome='Escala 2019', ativo=True)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=0, descricao='Desconheço', tipo_criterio=NivelEscalaLikert.CRITERIO_DESCONHECO)
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=1, descricao='Discordo', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO)
        NivelEscalaLikert.objects.get_or_create(
            escala=escala, nivel=3, descricao='Concordo parcialmente', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE
        )
        NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=4, descricao='Concordo', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO)

        # escala, _created = EscalaLikert.objects.get_or_create(nome='Escala 2021', ativo=True)
        # NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=0, descricao='Desconheço', tipo_criterio=NivelEscalaLikert.CRITERIO_DESCONHECO)
        # NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=1, descricao='Discordo', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO)
        # NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=2, descricao='Discordo parcialmente', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE)
        # NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=3, descricao='Concordo parcialmente', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE)
        # NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=4, descricao='Concordo', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO)

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

        # escala, _created = EscalaLikert.objects.get_or_create(nome='82151aa969aed2080504a952299a3b6b26daaaf277a259423d51dcb0753943ec', ativo=False)
        # nivel1, _ = NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=1, descricao='Desconheço', tipo_criterio=NivelEscalaLikert.CRITERIO_DESCONHECO)
        # nivel2, _ = NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=2, descricao='Discordo',  tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO)
        # nivel3, _ = NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=3, descricao='Discordo parcialmente', tipo_criterio=NivelEscalaLikert.CRITERIO_DISCORDO_PARCIALMENTE)
        # nivel4, _ = NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=4, descricao='Concordo parcialmente', tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO_PARCIALMENTE)
        # nivel5, _ = NivelEscalaLikert.objects.get_or_create(escala=escala, nivel=5, descricao='Concordo',  tipo_criterio=NivelEscalaLikert.CRITERIO_CONCORDO)
        #


# , , ,  e
# "0 - Desconheço", "1 - Discordo", "2 - Discordo parcialmente", "3 - Concordo parcialmente" e "4 - Concordo"
