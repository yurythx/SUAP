from django.conf import settings

from .vmware_horizon import VMwareHorizonAPI


def make_horizon_from_settings(name='default') -> VMwareHorizonAPI:
    vdi_server = settings.VDI_SERVERS[name]
    creds = {'hostname': vdi_server['HOSTNAME'], 'username': vdi_server['USER'], 'password': vdi_server['PASSWORD'], 'domain': vdi_server['DOMAIN']}
    return VMwareHorizonAPI(**creds)


class DesktopPool:
    def __init__(self, *args, **kwargs) -> None:
        pass


class VMWareHorizonService:
    def __init__(self, hostname, username, password, domain) -> None:
        self.api: VMwareHorizonAPI = VMwareHorizonAPI(hostname=hostname, username=username, password=password, domain=domain)
        self.domain = domain

    @classmethod
    def from_dict(cls, dict):
        return VMWareHorizonService(**dict)

    @classmethod
    def from_settings(cls, name='default'):
        vdi_server = settings.VDI_SERVERS[name]
        creds = {
            'hostname': vdi_server['HOSTNAME'],
            'username': vdi_server['USER'],
            'password': vdi_server['PASSWORD'],
            'domain': vdi_server['DOMAIN'],
        }
        return VMWareHorizonService(**creds)

    ######################################################
    # AD Domain
    ######################################################
    def get_ad_users_or_groups(self, users_or_groups, group_only=None, only_ids=True):
        results = []
        for user_or_group in users_or_groups:
            ad_user_or_group = self.get_ad_user_or_group(user_or_group, group_only)
            if ad_user_or_group:
                results.append(ad_user_or_group['id'] if only_ids else ad_user_or_group)
        #
        return results

    def get_ad_user_or_group(self, user_or_group, group_only=None):
        horizon_filter = {
            'type': 'And',
            'filters': [{'type': 'Equals', 'name': 'domain', 'value': self.domain}, {'type': 'Equals', 'name': 'name', 'value': user_or_group}],
        }
        ad_user_or_group = self.api.external.get_ad_users_or_groups(group_only=group_only, filter=horizon_filter, maxpagesize=1)
        return ad_user_or_group[0] if ad_user_or_group else None

    ######################################################
    # Desktop Pool
    ######################################################
    def number_max_of_machines(self, desktop_pool_id) -> int:
        desktop_pool = self.api.inventory.get_desktop_pool(desktop_pool_id=desktop_pool_id)
        return desktop_pool['pattern_naming_settings']['max_number_of_machines']

    def get_desktop_pool(self, desktop_pool_id) -> dict:
        desktop_pool = self.api.inventory.get_desktop_pool(desktop_pool_id=desktop_pool_id)
        return desktop_pool

    def get_desktop_pools(self):
        desktop_pools = self.api.inventory.get_desktop_pools()
        return desktop_pools

    def get_machines_from_desktop_pool(self, desktop_pool_id):
        filter = {'type': 'Equals', 'name': 'desktop_pool_id', 'value': desktop_pool_id}
        machines = self.api.inventory.get_machines(filter=filter)
        return machines

    def get_ad_groups_from_desktop_pool(self, desktop_pool_id):
        entitlement = self.api.entitlements.get_desktop_pool_entitlement(desktop_pool_id=desktop_pool_id)
        groups = entitlement['ad_user_or_group_ids']
        filters = [{'type': 'Equals', 'name': 'id', 'value': id} for id in groups]
        filter = {'type': 'Or', 'filters': filters}
        ad_groups = self.api.external.get_ad_users_or_groups(filter=filter, group_only=True)
        return ad_groups

    def assign_user_or_group_ids_to_desktop_pool(self, ad_user_or_group_ids, desktop_pool_id):
        desktop_pool_data = [{'ad_user_or_group_ids': ad_user_or_group_ids, 'id': desktop_pool_id}]
        self.api.entitlements.new_desktop_pools_entitlements(desktop_pool_data)

    def assign_users_or_groups_to_desktop_pool(self, ad_users_or_groups, desktop_pool_id):
        ad_user_or_group_ids = [ad_user_or_group['id'] for ad_user_or_group in ad_users_or_groups]
        self.assign_user_or_group_ids_to_desktop_pool(ad_user_or_group_ids, desktop_pool_id)

    def remove_user_or_group_ids_from_desktop_pool(self, ad_user_or_group_ids, desktop_pool_id):
        desktop_pool_data = [{'ad_user_or_group_ids': ad_user_or_group_ids, 'id': desktop_pool_id}]
        return self.api.entitlements.delete_desktop_pools_entitlements(desktop_pool_data)

    def remove_users_or_groups_from_desktop_pool(self, ad_users_or_groups, desktop_pool_id):
        ad_user_or_group_ids = [ad_user_or_group['id'] for ad_user_or_group in ad_users_or_groups]
        return self.remove_user_or_group_ids_from_desktop_pool(ad_user_or_group_ids, desktop_pool_id)

    def get_sessions_from_desktop_pool(self, desktop_pool_id):
        filter = {'type': 'Equals', 'name': 'desktop_pool_id', 'value': desktop_pool_id}
        sessions = self.api.inventory.get_sessions(filter=filter)
        return sessions

    def disconnect_sessions_from_desktop_pool(self, desktop_pool_id):
        sessions = self.get_sessions_from_desktop_pool(desktop_pool_id)
        sessions_id = [session['id'] for session in sessions]
        if sessions_id:
            self.api.inventory.disconnect_sessions(session_ids=sessions_id)

    def send_message_to_desktop_pool(self, desktop_pool_id, message):
        sessions = self.get_sessions_from_desktop_pool(desktop_pool_id)
        sessions_id = [session['id'] for session in sessions]
        if sessions_id:
            self.api.inventory.send_message_sessions(session_ids=sessions_id, message=message)

    def get_ids_users_or_groups_from_desktop_pool(self, desktop_pool_id, group_only=None):
        ad_user_or_group_ids = self.api.entitlements.get_desktop_pool_entitlement(desktop_pool_id=desktop_pool_id)
        return self.get_ad_users_or_groups(ad_user_or_group_ids, group_only=group_only)
