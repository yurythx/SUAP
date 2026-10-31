from django.conf import settings

from .guacamole.api import GuacamoleAPI, GuacamoleNotFoundException
from .guacamole.templates import BALACING_CONNECTION_GROUP, LDAP_GROUP, ORG_CONNECTION_GROUP, RDP_CONNECTION, USER


class GuacamoleService:
    def __init__(self, hostname, username, password, method='http', default_datasource='postgresql'):
        self.api = GuacamoleAPI(
            hostname=hostname,
            username=username,
            password=password,
            method=method,
            default_datasource=default_datasource,
        )

    @classmethod
    def from_dict(cls, dict):
        return GuacamoleService(**dict)

    @classmethod
    def from_settings(cls, name='default'):
        guacamole_server = settings.GUACAMOLE_SERVERS[name]
        creds = {'hostname': guacamole_server['HOST'], 'username': guacamole_server['USER'], 'password': guacamole_server['PASSWORD']}
        return GuacamoleService(**creds)

    ######################################################
    # USER
    ######################################################
    def add_user(self, username):
        payload = make_guacamole_user(username)
        return self.api.add_user(payload)

    def remove_user(self, username):
        return self.api.delete_user(username)

    def get_user(self, username):
        return self.api.get_user(username)

    def get_or_create_user(self, username):
        user = self.has_username(username)
        if user is None:
            return self.add_user(username)
        return user

    #

    def has_username(self, username):
        try:
            return self.api.get_user(username)
        except GuacamoleNotFoundException:
            return None

    ######################################################
    # GROUP
    ######################################################
    def get_group(self, group_name):
        try:
            return self.api.get_group(group_name)
        except GuacamoleNotFoundException:
            return None

    #
    def has_group(self, group_name):
        return self.get_group(group_name) is not None

    #
    def add_group(self, group_name):
        if not self.has_group(group_name):
            payload = dict(LDAP_GROUP)
            payload['identifier'] = group_name
            self.api.add_group(payload)
        #

    def remove_group(self, group_name):
        try:
            self.api.delete_group(group_name)
        except GuacamoleNotFoundException:
            pass

    def add_member_to_group(self, group, username):
        return self.api.add_group_members_user(group, username)

    def remove_member_from_group(self, group, username):
        return self.api.remove_group_members_user(group, username)

    ######################################################
    # Group Permissions
    ######################################################

    def assign_connection_groups_to_group(self, user_group, connection_group):
        return self.api.assign_connection_groups_to_group(user_group, connection_group)

    def revoke_connection_groups_from_group(self, user_group, connection_group):
        return self.api.revoke_connection_groups_from_group(user_group, connection_group)

    ######################################################
    # Connection Groups
    ######################################################
    def connection_group_by_name(self, name):
        connection = self.api.get_connection_group_by_name(name)
        if connection:
            return connection['identifier']
        return None

    def add_connection_group(self, payload):
        response = self.api.add_connection_group(payload)
        return int(response['identifier'])

    def update_connection_group(self, connection_group_id, payload):
        self.api.edit_connection_group(connection_group_id, payload)
        return connection_group_id

    #
    def sync_connection_group(self, connection_group_id, payload):
        #
        if connection_group_id is None:
            return self.add_connection_group(payload)
        else:
            return self.update_connection_group(connection_group_id, payload)

    #
    def remove_connection_group(self, connection_group_id):
        self.api.delete_connection_group(connection_group_id)

    ######################################################
    # Connection
    ######################################################

    def add_connection(self, payload):
        response = self.api.add_connection(payload)
        return int(response['identifier'])

    def update_connection(self, connection_id, payload):
        self.api.edit_connection(connection_id, payload)
        return connection_id

    #

    def sync_connection(self, connection_id, payload):
        #
        if connection_id is None:
            return self.add_connection(payload)
        else:
            return self.update_connection(connection_id, payload)

    #
    def remove_connection(self, connection_id):
        self.api.delete_connection(connection_id)

    ######################################################
    # Killing connection
    ######################################################

    def kill_active_session(self, connection_id):
        self.api.kill_active_connections_by_connection(connection_id)

    def kill_active_session_by_group(self, connection_group_id):
        self.api.kill_active_connections_by_connection_group(connection_group_id)

    ######################################################
    # SCHEMA
    ######################################################
    def get_connection_attributes_schema(self):
        return self.api.connection_attributes_schema()

    def get_connection_group_attributes_schema(self):
        return self.api.connection_group_attributes_schema()

    def get_sharing_profile_attributes_schema(self):
        return self.api.sharing_profile_attributes_schema()

    def get_protocols_schema(self):
        return self.api.protocols_schema()

    def get_user_attributes_schema(self):
        return self.api.user_attributes_schema()

    def get_user_group_attributes_schema(self):
        return self.api.user_group_attributes_schema()


def make_guacamole_org_connection_group_payload(name, location='ROOT'):
    #
    payload = dict(ORG_CONNECTION_GROUP)
    payload['name'] = name
    payload['parentIdentifier'] = location
    return payload


def make_guacamole_connection_group_payload(
    connection_group_name, max_connections, max_connections_per_user, enable_session_affinity, location='ROOT'
):
    #
    payload = dict(BALACING_CONNECTION_GROUP)
    payload['name'] = connection_group_name
    payload['parentIdentifier'] = location
    payload['attributes']['max-connections'] = max_connections
    payload['attributes']['max-connections-per-user'] = max_connections_per_user
    payload['attributes']['enable-session-affinity'] = enable_session_affinity
    return payload


def make_guacamole_connection_payload(**kwargs):
    #
    payload = dict(RDP_CONNECTION)
    payload['name'] = kwargs['connection_name']
    payload['parentIdentifier'] = kwargs['location']
    payload['attributes'] = kwargs['attrs']
    payload['parameters'] = kwargs['parameters']

    # payload["attributes"]["max-connections"] = kwargs['max_connections']
    # payload["attributes"]["max-connections-per-user"] = kwargs['max_connections_per_user']
    # payload["parameters"]['hostname'] = kwargs['hostname']
    # payload["parameters"]['domain'] = kwargs['domain']
    # payload["parameters"]['username'] = kwargs['username']
    # payload["parameters"]['password'] = kwargs['password']
    # payload["parameters"]['server-layout'] = kwargs['server_layout']
    #

    return payload


def make_guacamole_user(username, password=''):
    payload = dict(USER)
    payload['username'] = username
    payload['password'] = password
    return payload
