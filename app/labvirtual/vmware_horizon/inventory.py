import json

from .auth import Auth


class Inventory:
    def __init__(self, auth: Auth) -> None:
        self.auth: Auth = auth

    @property
    def base_endpoint(self):
        return f'{self.auth.REST_API}/inventory'

    def mount_url(self, endpoint: str, api_version: str = 'v1') -> str:
        return f'/inventory/{api_version}/{endpoint}'

    ###################################################################################
    # DESKTOP POOLS
    ###################################################################################
    def get_desktop_pools(self, version='v4') -> list:
        """
        Returns a list of dictionaries with all available Desktop Pools.
        """
        endpoint = 'desktop-pools'
        url = self.mount_url(endpoint, version)
        return self.auth.request('GET', url)

    def get_desktop_pool(self, desktop_pool_id: str, version='v4') -> dict:
        """
        Gets the Desktop Pool information. Requires id of a desktop pool
        """
        endpoint = f'desktop-pools/{desktop_pool_id}'
        url = self.mount_url(endpoint, version)
        return self.auth.request('GET', url)

    def check_desktop_pool_name_availability(self, desktop_pool_name: str, version='v1') -> dict:
        """
        Checks if the given name is available for desktop pool creation.
        Requires the name of the desktop pool to test as string
        """
        data = {}
        data['name'] = desktop_pool_name
        json_data = json.dumps(data)
        endpoint = 'desktop-pools/action/check-name-availability'
        url = self.mount_url(endpoint, version)
        return self.auth.request('POST', url, payload=json_data)

    def get_desktop_pool_installed_applications(self, desktop_pool_id: str) -> list:
        """
        Lists the installed applications on the given desktop pool.
        Requires id of a desktop pool
        """
        endpoint = f'desktop-pools/{desktop_pool_id}/installed-applications'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def desktop_pool_push_image(
        self,
        desktop_pool_id: str,
        start_time: str,
        add_virtual_tpm: bool = False,
        im_stream_id: str = '',
        im_tag_id: str = '',
        logoff_policy: str = 'WAIT_FOR_LOGOFF',
        parent_vm_id: str = '',
        snapshot_id: str = '',
        stop_on_first_error: bool = True,
    ):
        """
        Schedule/reschedule a request to update the image in an instant clone desktop pool
        Requires start_time in epoch, desktop_pool_id as string and either im_stream_id and im_tag_id OR parent_vm_id and snapshit_id as string.
        Optional: stop_on_first_error as bool, add_virtual_tpm as bool, logoff_policy as string with these options: FORCE_LOGOFF or WAIT_FOR_LOGOFF
        """
        data = {}
        #
        if add_virtual_tpm is not False:
            data['add_virtual_tpm'] = add_virtual_tpm
        #
        if im_stream_id != '' and im_tag_id != '':
            data['im_stream_id'] = im_stream_id
            data['im_tag_id'] = im_tag_id
        data['logoff_policy'] = logoff_policy
        #
        if parent_vm_id != '' and snapshot_id != '':
            data['parent_vm_id'] = parent_vm_id
            data['snapshot_id'] = snapshot_id
        #
        data['start_time'] = start_time
        data['stop_on_first_error'] = stop_on_first_error
        json_data = json.dumps(data)
        endpoint = f'desktop-pools/{desktop_pool_id}/action/schedule-push-image'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def cancel_desktop_pool_push_image(self, desktop_pool_id: str):
        """
        Lists Local Application Pools which are assigned to Global Application Entitlement.
        """
        endpoint = f'desktop-pools/{desktop_pool_id}/action/cancel-scheduled-push-image'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def get_desktop_pool_tasks(self, desktop_pool_id: str) -> list:
        """
        Lists the tasks on the desktop pool.
        """
        endpoint = f'desktop-pools/{desktop_pool_id}/tasks'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def get_desktop_pool_task(self, desktop_pool_id: str, task_id: str) -> dict:
        """
        Gets the task information on the desktop pool.
        """
        endpoint = f'desktop-pools/{desktop_pool_id}/tasks/{task_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def cancel_desktop_pool_task(self, desktop_pool_id: str, task_id: str) -> dict:
        """
        Cancels the instant clone desktop pool push image task.
        """
        endpoint = f'desktop-pools/{desktop_pool_id}/tasks/{task_id}/action/cancel'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url)

    ###################################################################################
    # Application Pools
    ###################################################################################
    def get_application_pools_by_page(self, page: int, maxpagesize: int, filter: list = '', version='v3') -> list:
        endpoint = 'application-pools'
        url = self.mount_url(endpoint, version)
        return self.auth.paginated_request_by_page(url, page, maxpagesize=maxpagesize, filter=filter)

    def get_application_pools(self, maxpagesize: int = 100, filter: dict = '', version='v3') -> list:
        """
        Lists the application pools in the environment.
        """
        endpoint = 'application-pools'
        url = self.mount_url(endpoint, version)
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize)

    def get_application_pool(self, application_pool_id: str, version='v3') -> dict:
        """
        Gets a single Application pool
        Requires Application_pool_id
        Available for Horizon 8 2006 and later.
        """
        endpoint = f'application-pools/{application_pool_id}'
        url = self.mount_url(endpoint, version)
        return self.auth.request('GET', url)

    def check_application_name_availability(self, application_name: str) -> dict:
        """
        Checks if the given name is available for application pool creation.

        Requires the name of the application to test as string
        """
        data = {}
        data['name'] = application_name
        json_data = json.dumps(data)
        endpoint = 'application-pools/action/check-name-availability'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def new_application_pool(self, application_pool_data: dict):
        """
        Creates an application pool.
        Requires application_pool_data as a dict
        """
        json_data = json.dumps(application_pool_data)
        endpoint = 'application-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def update_application_pool(self, application_pool_id: str, application_pool_data: dict):
        """
        Updates an application pool.
        The following keys are required to be present in the json: multi_session_mode, executable_path and enable_pre_launch
        Requires ad_domain_id, username and password in plain text.
        """
        json_data = json.dumps(application_pool_data)
        endpoint = f'application-pools/{application_pool_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('PUT', url, payload=json_data)

    def delete_application_pool(self, application_pool_id: str):
        """
        Deletes an application pool.
        Requires application_pool_id as a str
        """
        endpoint = f'application-pools/{application_pool_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url)

    ###################################################################################
    # FARMS
    ###################################################################################

    def get_farms(self, version='v2') -> list:
        """
        Lists the Farms in the environment.
        """
        endpoint = 'farms'
        url = self.mount_url(endpoint, version)
        return self.auth.request('GET', url)

    def get_farm(self, farm_id: str, version='v2') -> dict:
        """
        Gets the Farm information.
        Requires id of a RDS Farm
        """
        endpoint = f'farms/{farm_id}'
        url = self.mount_url(endpoint, version)
        return self.auth.request('GET', url)

    def get_farm_installed_applications(self, farm_id: str) -> list:
        """
        Lists the installed applications on the given farm.
        Requires id of a RDS Farm
        """
        endpoint = f'farms/{farm_id}/installed-applications'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def new_farm(self, farm_data: dict):
        """
        Creates a farm. Requires farm_data as a dict
        Available for Horizon 8 2103 and later.
        """
        json_data = json.dumps(farm_data)
        endpoint = 'farms'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def update_farm(self, farm_data: dict, farm_id: str):
        """
        Updates a farm.
        Requires farm_data as a dict
        """
        json_data = json.dumps(farm_data)
        endpoint = f'farms/{farm_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('PUT', url, payload=json_data)

    def delete_farm(self, farm_id: str) -> list:
        """
        Deletes a farm.
        Requires id of a RDS Farm
        """
        endpoint = f'farms/{farm_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url)

    def check_farm_name_availability(self, farm_name: str) -> dict:
        """
        Checks if the given name is available for farm creation.
        Requires the name of the RDS farm to test as string
        """
        data = {}
        data['name'] = farm_name
        json_data = json.dumps(data)
        endpoint = 'farms/action/check-name-availability'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    ###################################################################################
    # Machines
    ###################################################################################
    def get_machine(self, machine_id: str) -> dict:
        """
        Gets the Machine information.
        Requires id of a machine
        """
        endpoint = f'machines/{machine_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def get_machines_by_page(self, page: int, maxpagesize: int, filter: dict | None = None, version='v2') -> list:
        endpoint = 'machines'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request_by_page(url, page=page, filter=filter, maxpagesize=maxpagesize)

    def get_machines(self, maxpagesize: int = 100, filter: dict | None = None, version='v2') -> list:
        """
        Lists the Machines in the environment.
        """
        endpoint = 'machines'
        url = self.mount_url(endpoint, version)
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize)

    def add_machines(self, desktop_pool_id: str, machine_ids: list):
        """
        Adds machines to the given manual desktop pool.
        Requires list of machine_ids and desktop_pool_id to add them to
        """
        json_data = json.dumps(machine_ids)
        endpoint = f'desktop-pools/{desktop_pool_id}/action/add-machines'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def remove_machines(self, desktop_pool_id: str, machine_ids: list):
        """
        Removes machines from the given manual desktop pool.
        Requires list of machine_ids and desktop_pool_id to remove them from
        """
        json_data = json.dumps(machine_ids)
        endpoint = f'desktop-pools/{desktop_pool_id}/action/remove-machines'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def add_machines_by_name(self, desktop_pool_id: str, machine_data: list):
        """
        Adds machines to the given manual desktop pool.
        Requires requires desktop_pool_id and list of of dicts where each dict has name and user_id.
        """
        json_data = json.dumps(machine_data)
        endpoint = f'desktop-pools/{desktop_pool_id}/action/add-machines-by-name'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def delete_machine(self, machine_id: str, delete_from_multiple_pools: bool = False, force_logoff: bool = False, delete_from_disk: bool = False):
        """
        Deletes a machine.
        Requires id of the machine to delete machine
        Optional arguments (all default to False): delete_from_multiple_pools, force_logoff and delete_from_disk
        """
        data = {}
        data['allow_delete_from_multi_desktop_pools'] = delete_from_multiple_pools
        data['archive_persistent_disk'] = False
        data['delete_from_disk'] = delete_from_disk
        data['force_logoff_session'] = force_logoff
        json_data = json.dumps(data)
        endpoint = f'machines/{machine_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url, payload=json_data)

    def delete_machines(
        self, machine_ids: list, delete_from_multiple_pools: bool = False, force_logoff: bool = False, delete_from_disk: bool = False
    ):
        """
        deletes the specified machines

        Requires list of ids of the machines to remove
        Optional arguments (all default to False): delete_from_multiple_pools, force_logoff and delete_from_disk
        """
        data = {}
        machine_delete_data = {}
        machine_delete_data['allow_delete_from_multi_desktop_pools'] = delete_from_multiple_pools
        machine_delete_data['archive_persistent_disk'] = False
        machine_delete_data['delete_from_disk'] = delete_from_disk
        machine_delete_data['force_logoff_session'] = force_logoff
        data['machine_delete_data'] = machine_delete_data
        data['machine_ids'] = machine_ids
        json_data = json.dumps(data)
        endpoint = 'machines/'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url, payload=json_data)

    def machines_enable_maintenance_mode(self, machine_ids: list):
        """
        Puts a machine in maintenance mode.
        Requires a List of Machine Ids representing the machines to be put into maintenance mode.
        Available for Horizon 8 2006 and later.
        """
        json_data = json.dumps(machine_ids)
        endpoint = 'machines/action/enter-maintenance'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def machines_exit_maintenance_mode(self, machine_ids: list):
        """Takes a machine out of maintenance mode.

        Requires a List of Machine Ids representing the machines to be taken out of maintenance mode.
        Available for Horizon 8 2006 and later."""
        json_data = json.dumps(machine_ids)
        endpoint = 'machines/action/exit-maintenance'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def rebuild_machines(self, machine_ids: list):
        """
        Rebuilds the specified machines.
        Requires a List of Machine Ids representing the machines to be rebuild.
        """
        json_data = json.dumps(machine_ids)
        endpoint = 'machines/action/rebuild'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def recover_machines(self, machine_ids: list):
        """
        Recovers the specified machines.
        Requires a List of Machine Ids representing the machines to be recovered.
        """
        json_data = json.dumps(machine_ids)
        endpoint = 'machines/action/recover'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def reset_machines(self, machine_ids: list):
        """
        Resets the specified machines.
        Requires a List of Machine Ids representing the machines to be reset.
        Available for Horizon 8 2006 and later.
        """
        json_data = json.dumps(machine_ids)
        endpoint = 'machines/action/reset'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def restart_machines(self, machine_ids: list):
        """
        Restarts the specified machines.
        Requires a List of Machine Ids representing the machines to be restarted.
        """
        json_data = json.dumps(machine_ids)
        endpoint = 'machines/action/restart'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def check_machine_name_availability(self, machine_name: str) -> dict:
        """
        Checks if the given name is available for machine creation.
        Requires the name of the application to test as string
        """
        data = {}
        data['name'] = machine_name
        json_data = json.dumps(data)
        endpoint = 'machines/action/check-name-availability'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    ###################################################################################
    # SESSIONS
    ###################################################################################
    def get_sessions_by_page(self, page: int, maxpagesize: int, filter: dict = '') -> list:
        endpoint = 'sessions'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request_by_page(url, page, maxpagesize=maxpagesize, filter=filter)

    def get_sessions(self, filter: dict = '', maxpagesize: int = 100) -> list:
        endpoint = 'sessions'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize)

    def get_session(self, session_id: str) -> dict:
        """
        Gets the Session information. Requires session_id.
        """
        endpoint = f'sessions/{session_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def disconnect_sessions(self, session_ids: list):
        """
        Disconnects user sessions. Requires list of session ids
        """
        json_data = json.dumps(session_ids)
        endpoint = 'sessions/action/disconnect'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def logoff_sessions(self, session_ids: list, forced_logoff: bool = False):
        """
        Logs user sessions off.
        Requires list of session ids optional to set forced to True to force a log off (defaults to False)
        """
        json_data = json.dumps(session_ids)
        endpoint = f'sessions/action/logoff?forced={forced_logoff}'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def send_message_sessions(self, session_ids: list, message: str, message_type: str = 'INFO'):
        """
        Sends the message to user sessions
        Requires list of session ids, message type (INFO,WARNING,ERROR) and a message
        """
        data = {'message': message, 'message_type': message_type, 'session_ids': session_ids}
        json_data = json.dumps(data)
        endpoint = 'sessions/action/send-message'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def reset_session_machines(self, session_ids: list):
        """
        Resets machine of user sessions. The machine must be managed by Virtual Center and
        the session cannot be an application or an RDS desktop session.
        Requires list of session ids
        """
        json_data = json.dumps(session_ids)
        endpoint = 'sessions/action/reset'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url=url, payload=json_data)

    def restart_session_machines(self, session_ids: list):
        """
        Restarts machine of user sessions. The machine must be managed by Virtual Center and
        the session cannot be an application or an RDS desktop session.
        Requires list of session ids
        """
        json_data = json.dumps(session_ids)
        endpoint = 'sessions/action/reset'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url=url, payload=json_data)

    ###################################################################################
    # USER PERMISSIONS
    ###################################################################################
    def assign_user_to_machine(self, machine_id: str, user_ids: list):
        """
        Assigns the specified users to the machine.
        Requires machine_id of the machine and list of user_ids.
        """
        json_data = json.dumps(user_ids)
        endpoint = f'machines/{machine_id}/action/assign-users'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url=url, payload=json_data)

    def unassign_user_to_machine(self, machine_id: str, user_ids: list):
        """
        Unassigns the specified users to the machine.
        Requires machine_id of the machine and list of user_ids.
        """
        json_data = json.dumps(user_ids)
        endpoint = f'machines/{machine_id}/action/unassign-users'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url=url, payload=json_data)

    ###################################################################################
    # Entitlements
    ###################################################################################

    def get_global_desktop_entitlement(self, global_desktop_entitlement_id: str) -> dict:
        """
        Gets the Global Desktop Entitlement in the environment.
        """
        endpoint = f'global-desktop-entitlements/{global_desktop_entitlement_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

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

    def add_global_desktop_entitlement(self, global_desktop_entitlement_data: dict):
        """
        Creates a Global Desktop Entitlement.
        Requires global_desktop_entitlement_data as a dict
        """
        json_data = json.dumps(global_desktop_entitlement_data)
        endpoint = 'global-desktop-entitlements'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url=url, payload=json_data)

    def get_global_desktop_entitlement_compatible_desktop_pools(self, global_desktop_entitlement_id: str) -> list:
        """
        Lists Local Application Pools which are compatible with Global Application Entitlement.
        """
        endpoint = f'global-desktop-entitlements/{global_desktop_entitlement_id}/compatible-local-desktop-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def add_global_desktop_entitlement_local_desktop_pools(self, global_desktop_entitlement_id: str, desktop_pool_ids: list):
        """Adds a local desktop pool to a GLobal desktop Entitlement

        Requires global_desktop_entitlement_id as a string and desktop_pool_ids as a list
        Available for Horizon 8 2012 and later."""
        json_data = json.dumps(desktop_pool_ids)
        endpoint = f'global-desktop-entitlements/{global_desktop_entitlement_id}/local-desktop-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url=url, payload=json_data)

    def get_global_desktop_entitlement_local_desktop_pools(self, global_desktop_entitlement_id: str) -> list:
        """
        Lists Local Desktop Pools which are assigned to Global Desktop Entitlement.
        Available for Horizon 8 2012 and later.
        """
        endpoint = f'global-desktop-entitlements/{global_desktop_entitlement_id}/local-desktop-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def remove_global_desktop_entitlement_local_desktop_pools(self, global_desktop_entitlement_id: str, desktop_pool_ids: list):
        """
        Removes Local Desktop Pools from Global Desktop Entitlement.
        Requires global_desktop_entitlement_id as a string and desktop_pool_ids as a list
        """
        json_data = json.dumps(desktop_pool_ids)
        endpoint = f'global-desktop-entitlements/{global_desktop_entitlement_id}/local-desktop-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url=url, payload=json_data)

    def get_global_application_entitlement(self, global_application_entitlement_id: str) -> dict:
        """
        Gets the Global Application Entitlement in the environment.
        """
        endpoint = f'global-application-entitlements/{global_application_entitlement_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def get_global_application_entitlements_by_page(self, page: int = 0, maxpagesize: int = 100, filter: dict = '') -> list:
        endpoint = 'global-application-entitlements'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request_by_page(url, page, maxpagesize=maxpagesize, filter=filter)

    def get_global_application_entitlements(self, maxpagesize: int = 100, filter: dict = '') -> list:
        """
        Lists the Global Application Entitlements in the environment.
        """
        endpoint = 'global-application-entitlements'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize)

    def get_global_application_entitlement_compatible_application_pools(self, global_application_entitlement_id: str) -> list:
        """
        Lists Local Application Pools which are compatible with Global Application Entitlement.
        """
        endpoint = f'global-application-entitlements/{global_application_entitlement_id}/compatible-local-application-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def add_global_application_entitlement_local_application_pools(self, global_application_entitlement_id: str, application_pool_ids: list):
        """
        Adds a local Application pool to a GLobal Application Entitlement
        Requires global_application_entitlement_id as a string and application_pool_ids as a list
        """
        json_data = json.dumps(application_pool_ids)
        endpoint = f'global-application-entitlements/{global_application_entitlement_id}/local-application-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def get_global_application_entitlement_local_Application_pools(self, global_application_entitlement_id: str) -> list:
        """
        Lists Local Application Pools which are assigned to Global Application Entitlement.
        """
        endpoint = f'global-application-entitlements/{global_application_entitlement_id}/local-application-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def remove_global_application_entitlement_local_application_pools(self, global_application_entitlement_id: str, application_pool_ids: list):
        """
        Removes Local Application Pools from Global Application Entitlement.
        Requires global_application_entitlement_id as a string and application_pool_ids as a list
        """
        json_data = json.dumps(application_pool_ids)
        endpoint = f'global-application-entitlements/{global_application_entitlement_id}/local-application-pools'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url, payload=json_data)

    ###################################################################################
    # RDS
    ###################################################################################
    def get_rds_servers_by_page(self, page: int, maxpagesize: int, filter: list = '') -> list:
        endpoint = 'rds-servers'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request_by_page(url, page, maxpagesize=maxpagesize, filte=filter)

    def get_rds_servers(self, maxpagesize: int = 100, filter: dict = '') -> list:
        """
        Lists the RDS Servers in the environment.
        """
        endpoint = 'rds-servers'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request(url, filter=filter, maxpagesize=maxpagesize)

    def get_rds_server(self, rds_server_id: str) -> dict:
        """
        Gets the RDS Server information.
        """
        endpoint = f'rds-servers/{rds_server_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def delete_rds_server(self, rds_server_id: str) -> dict:
        """
        Deletes the RDS Server.
        """
        endpoint = f'rds-servers/{rds_server_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url)

    def recover_rds_servers(self, rds_server_ids: list) -> list:
        """
        Recovers the specified RDS Servers.
        """
        data = rds_server_ids
        json_data = json.dumps(data)
        endpoint = 'rds-servers/action/recover'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)

    def update_rds_server(self, rds_server_id: str, max_sessions_count_configured: int, max_sessions_type_configured: str, enabled: bool = True):
        """
        Schedule/reschedule a request to update the image in an instant clone desktop pool
        Requires the rds_server_id as string, enabled as booleanm max_sessions_count_configured as int and max_sessions_type_configured as string
        enabled defaults to True, the options for max_sessions_type_configured are: UNLIMITED, LIMITED, UNCONFIGURED
        """
        data = {}
        data['enabled'] = enabled
        data['max_sessions_count_configured'] = max_sessions_count_configured
        data['max_sessions_type_configured'] = max_sessions_type_configured
        json_data = json.dumps(data)
        endpoint = f'rds-servers/{rds_server_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('PUT', url, payload=json_data)

    def add_rds_server(self, description: str, dns_name: str, operating_system: str, farm_id: str):
        """
        Registers the RDS Server.
        Requires description, dns_name, operating_system and farm_id as string
        """
        data = {}
        data['description'] = description
        data['dns_name'] = dns_name
        data['farm_id'] = farm_id
        data['operating_system'] = operating_system
        json_data = json.dumps(data)
        endpoint = 'rds-servers/action/register'
        url = self.mount_url(endpoint)
        return self.auth.request('PUT', url, payload=json_data)

    def check_rds_server_name_availability(self, machine_name: str) -> dict:
        """
        Checks if the given prefix is available for RDS Server creation.
        Requires the name of the RDS Server to test as string
        """
        data = {'name': machine_name}
        json_data = json.dumps(data)
        endpoint = 'rds-servers/action/check-name-availability'
        url = self.mount_url(endpoint)
        return self.auth.request('PUT', url, payload=json_data)

    ###################################################################################
    # Physical Machines
    ###################################################################################
    def get_physical_machines_by_page(self, page: int, maxpagesize: int, filter: list = '') -> list:
        endpoint = 'physical-machines'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request_by_page(url, page, maxpagesize=maxpagesize, filter=filter)

    def get_physical_machines(self, maxpagesize: int = 100, filter: dict = '') -> list:
        """
        Lists the Physical Machines in the environment.
        """
        endpoint = 'physical-machines'
        url = self.mount_url(endpoint)
        return self.auth.paginated_request(url, maxpagesize=maxpagesize, filter=filter)

    def get_physical_machine(self, physical_machine_id: str) -> dict:
        """
        Gets the Physical Machine information.
        """
        endpoint = f'physical-machines/{physical_machine_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('GET', url)

    def delete_physical_machine(self, physical_machine_id: str):
        """
        Deletes the Physical Machine.
        """
        endpoint = f'physical-machines/{physical_machine_id}'
        url = self.mount_url(endpoint)
        return self.auth.request('DELETE', url)

    def add_physical_machine(self, description: str, dns_name: str, operating_system: str):
        """
        Registers the Physical Machine.
        Requires ad_domain_id, username and password in plain text.
        """
        data = {}
        data['description'] = description
        data['dns_name'] = dns_name
        data['operating_system'] = operating_system
        json_data = json.dumps(data)
        endpoint = 'physical-machines/action/register'
        url = self.mount_url(endpoint)
        return self.auth.request('POST', url, payload=json_data)
