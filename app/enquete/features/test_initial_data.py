def initial_data(verbosity=0):
    from comum.models import Publico

    # Criando Público Alvo
    Publico.objects.get_or_create(
        nome='Servidores', qs_filter='', modelo_base=Publico.BASE_SERVIDOR, filtro='{"ativo": true}', filtro_exclusao='{"ativo": false}'
    )
