from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[ldap_backend] Sync LDAP Parcial',
        'sync_ldap_parcial',
        interval=[1, Intervalo.HOURS],
        expire_seconds=3000,
    )
    carregar_call_command(
        '[ldap_backend] Sync LDAP Full',
        'sync_ldap_full',
        crontab={'hour': 0, 'minute': 23},
    )
    carregar_call_command(
        '[ldap_backend] Sync LDAP Expirados',
        'sync_ldap_expirados',
        crontab={'hour': 6, 'minute': 0},
    )
    carregar_call_command(
        '[ldap_backend] Sync LDAP Excluidos com AD ativo',
        'sync_ldap_excluidos_ad_ativos',
        crontab={'hour': 7, 'minute': 0},
    )
