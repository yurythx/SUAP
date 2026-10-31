from .auth import Auth


class Extenal:
    def __init__(self, auth: Auth) -> None:
        self.auth: Auth = auth

    @property
    def base_endpoint(self):
        return f'{self.auth.REST_API}/external'

    def mount_url(self, endpoint: str, api_version: str = 'v1') -> str:
        return f'/external/{api_version}/{endpoint}'

    def get_ad_users_or_groups_by_page(
        self, page: int = 1, maxpagesize: int = 100, ad_filter: dict | None = None, group_only: bool = True, version: str = 'v1'
    ) -> list:
        """
        group_only:
            Presence of this query param indicates to filter only groups or only users.
            If passed as "true", then only groups are returned.
            If passed as "false", then only users are returned.
            If not passed passed at all, then both types are returned.
        """
        if ad_filter is None:
            ad_filter = {}
        endpoint = 'ad-users-or-groups'
        url = self.mount_url(endpoint, version)
        extra_filter = f'group_only={group_only}' if group_only is not None else None
        return self.auth.paginated_request_by_page(url, page, maxpagesize=maxpagesize, filter=ad_filter, extra_filter=extra_filter)

    def get_ad_users_or_groups(self, maxpagesize: int = 100, filter: dict | None = None, group_only: bool | None = None, version: str = 'v1') -> list:
        """
        Lists the application pools in the environment.
        group_only:
            Presence of this query param indicates to filter only groups or only users.
            If passed as "true", then only groups are returned.
            If passed as "false", then only users are returned.
            If not passed passed at all, then both types are returned.
        """
        if filter is None:
            filter = {}
        endpoint = 'ad-users-or-groups'
        url = self.mount_url(endpoint, version)
        extra_filter = f'group_only={group_only}' if group_only is not None else None
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize, extra_filter=extra_filter)

    def get_ad_users_or_group(self, id: str, version: str = 'v1') -> dict:
        """
        Get information related to AD User or Group.
        """
        endpoint = f'ad-users-or-groups/{id}'
        url = self.mount_url(endpoint, version)
        return self.auth.request('GET', url)
