from .auth import Auth
from .config import Config
from .entitlements import Entitlements
from .external import Extenal
from .inventory import Inventory

"""
Breakdown of the Horizon Server REST API
API             Endpoint Description
Auth            APIs for authentication and authorization. Used to log in to or out of the Horizon Server REST API.
Config          APIs for managing configuration items such as environment properties, the Horizon Image Manage Service, Horizon
                Connection Server general settings and security settings, and listing VMware vCenter Server® instances associated
                with the environment.
Entitlements    APIs for managing user entitlements for application and desktop pools.
External        APIs for retrieving information external to the Horizon environment. These include information from Active Directory and vCenter Server.
Inventory       APIs for creating, updating, and deleting application and desktop pools; getting information on pools; adding machines to manual pools;
                getting information on RDSH server farms; and managing machines and sessions.
Monitor         APIs for monitoring. These are all GET endpoints for Horizon and related services.

"""


class VMwareHorizonAPI:
    def __init__(
        self, hostname: str, username: str, password: str, domain: str, url: str = 'rest', method: str = 'https', verify: bool = False
    ) -> None:
        self.auth = Auth(hostname, username, password, domain, url, method, verify)
        self.config = Config(auth=self.auth)
        self.inventory = Inventory(auth=self.auth)
        self.entitlements = Entitlements(auth=self.auth)
        self.external = Extenal(auth=self.auth)
        self.auth.connect()
