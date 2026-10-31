import json

#
from .auth import Auth


class Entitlements:
    def __init__(self, auth: Auth) -> None:
        self.auth: Auth = auth

    @property
    def base_endpoint(self):
        return f'{self.auth.REST_API}/entitlements'

    def mount_url(self, endpoint: str, api_version: str = 'v1') -> str:
        return f'/entitlements/{api_version}/{endpoint}'

    def get_desktop_pool_entitlement(self, desktop_pool_id: str, version: str = 'v1') -> list:
        """
        Returns the IDs of users or groups entitled to a given desktop pool
        Requires desktop_pool_id
        """
        endpoint = f'desktop-pools/{desktop_pool_id}'
        url = self.mount_url(endpoint, version)
        return self.auth.request('GET', url)

    def get_desktop_pools_entitlements_by_page(self, page: int, maxpagesize: int = 100, filter: dict = '') -> list:
        endpoint = 'desktop-pools'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request_by_page(url, page, filter=filter, maxpagesize=maxpagesize)

    def get_desktop_pools_entitlements(self, maxpagesize: int = 100, filter: dict = '') -> list:
        """
        Lists the Global Application Entitlements in the environment.
        """
        endpoint = 'desktop-pools'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize)

    def new_desktop_pools_entitlements(self, desktop_pools_data: list, version='v1'):
        """
        Create the bulk entitlements for a set of desktop pools.
        Requires desktop_pools_data as a list
        """
        endpoint = 'desktop-pools'
        json_data = json.dumps(desktop_pools_data)
        url = self.mount_url(endpoint, version)
        return self.auth.request('POST', url, payload=json_data)

    def delete_desktop_pools_entitlements(self, desktop_pools_data: list, version='v1'):
        """
        Delete the bulk entitlements for a set of desktop pools.
        Requires desktop_pools_data as a list.
        """
        endpoint = 'desktop-pools'
        json_data = json.dumps(desktop_pools_data)
        url = self.mount_url(endpoint, version)
        return self.auth.request('DELETE', url, payload=json_data)

    def get_global_desktop_entitlements_by_page(self, page: int, maxpagesize: int = 100, filter: dict = '') -> list:
        endpoint = 'global-desktop-entitlements'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request_by_page(url, page, filter=filter, maxpagesize=maxpagesize)

    def get_global_desktop_entitlements(self, maxpagesize: int = 100, filter: dict = '') -> list:
        """
        Lists the Global Application Entitlements in the environment.
        """
        endpoint = 'global-desktop-entitlements'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize)

    def new_global_desktop_entitlements(self, desktop_pools_data: list, version='v1'):
        """
        Create the bulk entitlements for a set of Global Desktop Entitlements.
        Requires desktop_pools_data as a list
        """
        endpoint = 'global-desktop-entitlements'
        json_data = json.dumps(desktop_pools_data)
        url = self.mount_url(endpoint, version)
        return self.auth.request('POST', url, payload=json_data)

    def delete_global_desktop_pools_entitlements(self, desktop_pools_data: list, version='v1'):
        """
        Delete the bulk entitlements for a set of Global Desktop Entitlements.
        Requires desktop_pools_data as a list.
        """
        endpoint = 'global-desktop-entitlements'
        json_data = json.dumps(desktop_pools_data)
        url = self.mount_url(endpoint, version)
        return self.auth.request('DELETE', url, payload=json_data)
