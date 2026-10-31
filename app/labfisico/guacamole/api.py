#!/usr/bin/env python
import base64
import hashlib
import hmac
import json
import logging
import re
import struct
import time

from django.conf import settings

from djtools.utils import requests

logger = logging.getLogger(__name__)


def get_hotp_token(secret, intervals_no):
    key = base64.b32decode(secret, True)
    msg = struct.pack('>Q', intervals_no)
    h = bytes(hmac.new(key, msg, hashlib.sha1).digest())
    o = h[19] & 15
    h = (struct.unpack('>I', h[o : o + 4])[0] & 0x7FFFFFFF) % 1000000
    return h


def get_totp_token(secret):
    return get_hotp_token(secret, intervals_no=int(time.time()) // 30)


class GuacamoleException(Exception):
    """Still an exception raised when uncommon things happen"""

    def __init__(self, message, payload=None):
        self.message = message
        self.payload = payload  # you could add more args

    def __str__(self):
        return str(self.message)


class GuacamoleNotFoundException(GuacamoleException):
    pass


class GuacamoleAPI:
    def __init__(self, hostname, username, password, secret=None, method='https', url_path='', default_datasource=None, cookies=False, verify=True):
        #
        if method.lower() not in ['https', 'http']:
            raise ValueError('Only http and https methods are valid.')
        #
        self.REST_API = f'{method}://{hostname}{url_path}/api'
        self.username = username
        self.password = password
        self.secret = secret
        self.verify = verify
        resp = self.__authenticate()
        auth = resp.json()
        assert 'authToken' in auth, 'Failed to retrieve auth token'
        assert 'dataSource' in auth, 'Failed to retrieve primaray data source'
        assert 'availableDataSources' in auth, 'Failed to retrieve data sources'
        self.datasources = auth['availableDataSources']
        self.cookies = resp.cookies if cookies else None
        self.token = auth['authToken']
        if default_datasource:
            error_msg = f'Datasource {default_datasource} does not exist. Possible values: {self.datasources}'
            assert default_datasource in self.datasources, error_msg
            self.primary_datasource = default_datasource
        else:
            self.primary_datasource = auth['dataSource']

    def delete_token(self):
        url = f'{self.REST_API}/tokens/{self.token}'
        response = requests.post(url=url, verify=self.verify, allow_redirects=True, timeout=settings.REQUESTS_TIMEOUT)
        response.raise_for_status()
        return response

    def get_connections(self, datasource=None):
        datasource = datasource or self.primary_datasource
        params = [('permission', 'UPDATE'), ('permission', 'DELETE')]
        url = f'{self.REST_API}/session/data/{datasource}/connectionGroups/ROOT/tree'
        return self.__auth_request(method='GET', url=url, url_params=params)

    def get_connection_group_connections(self, connection_group_id, datasource=None):
        """
        Get a list of connections linked to an organizational or balancing
        connection group
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connectionGroups/{connection_group_id}/tree'
        return self.__auth_request(method='GET', url=url)

    def get_active_connections(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/activeConnections'
        return self.__auth_request(method='GET', url=url)

    def kill_active_connections(self, active_connection_id, datasource=None):
        """
        Kill connections by connection identifier.

        """
        datasource = datasource or self.primary_datasource
        payload = [{'op': 'remove', 'path': f'/{active_connection_id}'}]
        url = f'{self.REST_API}/session/data/{datasource}/activeConnections'
        return self.__auth_request(method='PATCH', url=url, payload=payload, json_response=False)

    def kill_active_connections_by_connection_group(self, connections_group_id, datasource=None):
        connections = self.get_connection_group_connections(connections_group_id)
        active_connections = self.get_active_connections().values()
        response = {}
        for connection in connections.get('childConnections') if connections else ():
            response = self.kill_active_connections_by_connection(connection['identifier'], datasource, active_connections)
        return response

    #
    def kill_active_connections_by_connection(self, connection_id, datasource=None, active_connections=None):
        active_connections = active_connections or self.get_active_connections().values()
        response = {}
        for connection in active_connections:
            if connection['connectionIdentifier'] == str(connection_id):
                response = self.kill_active_connections(connection['identifier'], datasource)
        return response

    def get_connection(self, connection_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connections/{connection_id}'
        return self.__auth_request(method='GET', url=url)

    def get_connection_parameters(self, connection_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connections/{connection_id}/parameters'
        return self.__auth_request(method='GET', url=url)

    def get_connection_full(self, connection_id, datasource=None):
        connection = self.get_connection(connection_id, datasource)
        connection['parameters'] = self.get_connection_parameters(connection_id, datasource)
        return connection

    def get_connection_by_name(self, name, regex=False, datasource=None):
        """
        Get a connection by its name
        """
        connections = self.get_connections(datasource)
        response = self.__get_connection_by_name(connections, name, regex)
        if not response:
            logger.error(f'Could not find connection named {name}')
        return response

    def add_connection(self, payload, datasource=None):
        """
        Add a new connection

        Example payload:
        {"name":"iaas-067-mgt01 (Admin)",
        "parentIdentifier":"4",
        "protocol":"rdp",
        "attributes":{"max-connections":"","max-connections-per-user":""},
        "activeConnections":0,
        "parameters":{
            "port":"3389",
            "enable-menu-animations":"true",
            "enable-desktop-composition":"true",
            "hostname":"iaas-067-mgt01.vcloud",
            "color-depth":"32",
            "enable-font-smoothing":"true",
            "ignore-cert":"true",
            "enable-drive":"true",
            "enable-full-window-drag":"true",
            "security":"any",
            "password":"XXX",
            "enable-wallpaper":"true",
            "create-drive-path":"true",
            "enable-theming":"true",
            "username":"Administrator",
            "console":"true",
            "disable-audio":"true",
            "domain":"iaas-067-mgt01.vcloud",
            "drive-path":"/var/tmp",
            "disable-auth":"",
            "server-layout":"",
            "width":"",
            "height":"",
            "dpi":"",
            "console-audio":"",
            "enable-printing":"",
            "preconnection-id":"",
            "enable-sftp":"",
            "sftp-port":""}}
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connections'
        return self.__auth_request(method='POST', url=url, payload=payload)

    def edit_connection(self, connection_id, payload, datasource=None):
        """
        Edit an existing connection

        Example payload:
        {"name":"test",
        "identifier":"7",
        "parentIdentifier":"ROOT",
        "protocol":"rdp",
        "attributes":{"max-connections":"","max-connections-per-user":""},
        "activeConnections":0,
        "parameters":{
            "disable-audio":"true",
            "server-layout":"fr-fr-azerty",
            "domain":"dt",
            "hostname":"127.0.0.1",
            "enable-font-smoothing":"true",
            "security":"rdp",
            "port":"3389",
            "disable-auth":"",
            "ignore-cert":"",
            "console":"",
            "width":"",
            "height":"",
            "dpi":"",
            "color-depth":"",
            "console-audio":"",
            "enable-printing":"",
            "enable-drive":"",
            "create-drive-path":"",
            "enable-wallpaper":"",
            "enable-theming":"",
            "enable-full-window-drag":"",
            "enable-desktop-composition":"",
            "enable-menu-animations":"",
            "preconnection-id":"",
            "enable-sftp":"",
            "sftp-port":""}}
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connections/{connection_id}'
        return self.__auth_request(method='PUT', url=url, payload=payload, json_response=False)

    def delete_connection(self, connection_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connections/{connection_id}'
        return self.__auth_request(method='DELETE', url=url, json_response=False)

    def get_connections_history(self, urls_parameters=None, datasource=None):
        """
        Query Parameters

        token (string, required) - Auth Token
        contains (string, optional) - Contains
        order (string, optional) - Property name to order

        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/history/connections'
        return self.__auth_request(method='GET', url=url, url_params=urls_parameters)

    def get_users_history(self, url_parameters=None, datasource=None):
        """
        Query Parameters

        token (string, required) - Auth Token
        order (string, optional) - Property name to order

        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/history/users'
        return self.__auth_request(method='GET', url=url, url_params=url_parameters)

    def get_connection_group_by_name(self, name, regex=False, datasource=None):
        """
        Get a connection group by its name
        """
        datasource = datasource or self.primary_datasource
        connection = self.get_connections(datasource)
        return self.__get_connection_group_by_name(connection, name, regex)

    def get_connection_group(self, connectiongroup_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connectionGroups/{connectiongroup_id}'
        return self.__auth_request(method='GET', url=url)

    def add_connection_group(self, payload, datasource=None):
        """
        Create a new connection group

        Example payload:
        {
            "parentIdentifier":"ROOT",
            "name":"iaas-099 (Test)",
            "type":"ORGANIZATIONAL",
            "attributes":{"max-connections":"", "max-connections-per-user":""}
        }
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connectionGroups'
        return self.__auth_request(method='POST', url=url, payload=payload)

    def edit_connection_group(self, connection_group_id, payload, datasource=None):
        """
        Edit an exiting connection group

        Example payload:
        {
            "parentIdentifier":"ROOT",
            "name":"iaas-099 (Test)",
            "type":"ORGANIZATIONAL",
            "attributes":{"max-connections":"", "max-connections-per-user":""}
        }
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connectionGroups/{connection_group_id}'
        return self.__auth_request(method='PUT', url=url, payload=payload)

    def delete_connection_group(self, connection_group_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/connectionGroups/{connection_group_id}'
        return self.__auth_request(method='DELETE', url=url)

    def get_users(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users'
        return self.__auth_request(method='GET', url=url)

    def add_user(self, payload, datasource=None):
        """
        Add/enable a user

        Example payload:
        {
            "username":"test"
            "password":"testpwd",
            "attributes": {
                "disabled":"",
                "expired":"",
                "access-window-start":"",
                "access-window-end":"",
                "valid-from":"",
                "valid-until":"",
                "timezone":null
            }
        }
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users'
        return self.__auth_request(
            method='POST',
            url=url,
            payload=payload,
        )

    def edit_user(self, username, payload, datasource=None):
        """
        Edit a user

        Example payload:
        {
            "username": "username",
            "attributes": {
                "guac-email-address": null,
                "guac-organizational-role": null,
                "guac-full-name": null,
                "expired": "",
                "timezone": null,
                "access-window-start": "",
                "guac-organization": null,
                "access-window-end": "",
                "disabled": "",
                "valid-until": "",
                "valid-from": ""
            },
            "lastActive": 1588030687251,
            "password": "password"
        }
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users/{username}'
        return self.__auth_request(method='PUT', url=url, payload=payload, json_response=False)

    def get_user(self, username, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users/{username}'
        return self.__auth_request(method='GET', url=url)

    def delete_user(self, username, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users/{username}'
        return self.__auth_request(method='DELETE', url=url)

    def get_permissions(self, username, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users/{username}/permissions'
        return self.__auth_request(method='GET', url=url)

    def grant_permission(self, username, payload, datasource=None):
        """
        Example payload:
        [
            {"op":"add", "path":"/systemPermissions", "value":"ADMINISTER"}
        ]
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users/{username}/permissions'
        return self.__auth_request(method='PATCH', url=url, payload=payload, json_response=False)

    def get_sharing_profile_parameters(self, sharing_profile_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/sharingProfiles/{sharing_profile_id}/parameters'
        return self.__auth_request(method='GET', url=url)

    def get_sharing_profile_full(self, sharing_profile_id, datasource=None):
        sharing_profile = self.get_sharing_profile(sharing_profile_id, datasource)
        sharing_profile['parameters'] = self.get_sharing_profile_parameters(sharing_profile_id, datasource)
        return sharing_profile

    def get_sharing_profile(self, sharing_profile_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/sharingProfiles/{sharing_profile_id}'
        return self.__auth_request(method='GET', url=url)

    def add_sharing_profile(self, payload, datasource=None):
        """
        Add/enable a sharing profile

        Example payload:
        {
            "primaryConnectionIdentifier": "8",
            "name": "share",
            "parameters": {"read-only": ""},
            "attributes": {}
        }
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/sharingProfiles'
        return self.__auth_request(method='POST', url=url, payload=payload)

    def delete_sharing_profile(self, sharing_profile_id, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/sharingProfiles/{sharing_profile_id}'
        return self.__auth_request(method='DELETE', url=url)

    ######################################################################################
    #   USER GROUPS                                                                      #
    ######################################################################################
    def get_groups(self, datasource=None):
        """
        List User Groups
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups'
        return self.__auth_request(method='GET', url=url)

    def add_group(self, payload, datasource=None):
        """
        Add/enable a user group

        Example payload:
            {"identifier":"test", "attributes":{"disabled":""}}
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups'
        return self.__auth_request(method='POST', url=url, payload=payload)

    def delete_group(self, usergroup, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{usergroup}'
        return self.__auth_request(method='DELETE', url=url, json_response=False)

    def get_group(self, usergroup, datasource=None):
        """
        Details of User Group
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{usergroup}'
        return self.__auth_request(method='GET', url=url)

    def get_group_members(self, usergroup, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{usergroup}/memberUsers'
        return self.__auth_request(method='GET', url=url)

    def edit_group_members_user(self, user_group, payload, datasource=None):
        """
        Add Members to User Group

        user_group (string, required) - User group identifier
        data_source (string, required) - Data source

        Example add payload:
            [{"op":"add","path":"/","value":"username"}]

        Example remove payload:
            [{"op":"remove","path":"/","value":"username"}]
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{user_group}/memberUsers'
        return self.__auth_request(method='PATCH', url=url, payload=payload, json_response=False)

    def add_group_members_user(self, user_group, username, datasource=None):
        payload = [{'op': 'add', 'path': '/', 'value': username}]
        return self.edit_group_members_user(user_group, payload, datasource)

    def remove_group_members_user(self, user_group, username, datasource=None):
        payload = [{'op': 'remove', 'path': '/', 'value': username}]
        return self.edit_group_members_user(user_group, payload, datasource)

    def edit_group_members_group(self, usergroup, payload, datasource=None):
        """
        Add Member Groups to User Group

        user_group (string, required) - User group identifier
        data_source (string, required) - Data source

        Example add payload:
            [{"op":"add","path":"/","value":"userGroupIdentifier"}]
        Example remove payload:
            [{"op":"remove","path":"/","value":"userGroupIdentifier"}]
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{usergroup}/memberUserGroups'
        return self.__auth_request(method='PATCH', url=url, payload=payload, json_response=False)

    ######################################################################################
    #   Permissions                                                                      #
    ######################################################################################

    def grant_group_permission(self, groupname, payload, datasource=None):
        """
        Example payload:
            [{"op":"add","path":"/systemPermissions","value":"ADMINISTER"}]
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{groupname}/permissions'
        return self.__auth_request(method='PATCH', url=url, payload=payload, json_response=False)

    def get_group_permissions(self, groupname, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{groupname}/permissions'
        return self.__auth_request(method='GET', url=url)

    def grant_system_permission(self, username, payload, datasource=None):
        """
        Assign system permissions to an user.

        Example payload:
        [
            {"op": "add", "path": "/userPermissions/test1", "value": "UPDATE"},
            {"op": "add", "path": "/systemPermissions", "value": "CREATE_USER"},
            {"op": "add", "path": "/systemPermissions", "value": "CREATE_USER_GROUP"},
            {"op": "add", "path": "/systemPermissions", "value": "CREATE_CONNECTION"},
            {"op": "add", "path": "/systemPermissions", "value": "CREATE_CONNECTION_GROUP"},
            {"op": "add", "path": "/systemPermissions", "value": "CREATE_SHARING_PROFILE"},
            {"op": "add", "path": "/systemPermissions", "value": "ADMINISTER"}
        ]
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users/{username}/permissions'
        return self.__auth_request(method='PATCH', url=url, payload=payload)

    def edit_connection_groups_to_user(self, username, payload, datasource=None):
        """
        Assign/remove connection groups to an user.
        Example payload:
            [{"op": "add", "path": "/connectionGroupPermissions/{{connection_group}}", "value": "READ"}]
        [{"op": "remove", "path": "/connectionGroupPermissions/{{connection_group}}", "value": "READ"}]
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/users/{username}/permissions'
        return self.__auth_request(method='PATCH', url=url, payload=payload, json_response=False)

    def assign_connection_groups_to_user(self, username, connection_group, datasource=None):
        payload = [{'op': 'add', 'path': f'/connectionGroupPermissions/{connection_group}', 'value': 'READ'}]
        return self.edit_connection_groups_to_user(username, payload, datasource)

    def revoke_connection_groups_from_user(self, username, connection_group, datasource=None):
        payload = [{'op': 'remove', 'path': f'/connectionGroupPermissions/{connection_group}', 'value': 'READ'}]
        return self.edit_connection_groups_to_user(username, payload, datasource)

    def edit_connection_groups_to_group(self, user_group, payload, datasource=None):
        """
        Assign/Remove connection groups to an user group.

        Example payload:
            [{ "op": "add", "path": "/connectionGroupPermissions/{{connection_group}}", "value": "READ"}]
        """
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/userGroups/{user_group}/permissions'
        return self.__auth_request(method='PATCH', url=url, payload=payload, json_response=False)

    def assign_connection_groups_to_group(self, user_group, connection_group, datasource=None):
        payload = [{'op': 'add', 'path': f'/connectionGroupPermissions/{connection_group}', 'value': 'READ'}]
        return self.edit_connection_groups_to_group(user_group=user_group, payload=payload, datasource=datasource)

    def revoke_connection_groups_from_group(self, user_group, connection_group, datasource=None):
        payload = [{'op': 'remove', 'path': f'/connectionGroupPermissions/{connection_group}', 'value': 'READ'}]
        return self.edit_connection_groups_to_group(user_group=user_group, payload=payload, datasource=datasource)

    def __authenticate(self):
        parameters = {'username': self.username, 'password': self.password}
        if self.secret is not None:
            parameters['guac-totp'] = get_totp_token(self.secret)
        #
        url = f'{self.REST_API}/tokens'
        response = requests.post(
            url=url,
            data=parameters,
            verify=self.verify,
            allow_redirects=True,
            timeout=settings.REQUESTS_TIMEOUT,
        )
        return response

    def __auth_request(self, method, url, payload=None, url_params=None, json_response=True):
        params = [('token', self.token)]
        if url_params:
            params += url_params
        #
        logger.debug(f'{method} {url} - Params: {params} - Payload: {payload}')
        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=payload,
            verify=self.verify,
            allow_redirects=True,
            cookies=self.cookies,
            timeout=settings.REQUESTS_TIMEOUT,
        )
        if not response.ok:
            logger.error(response.content)
        #
        if response.status_code == 404:
            raise GuacamoleNotFoundException(f'Request for {url} not found')
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            error_msg = json.loads(e.response.text)
            payload = error_msg
            raise GuacamoleException(error_msg['message'], payload=payload)
        #
        if json_response:
            try:
                return response.json()
            except json.JSONDecodeError:
                logger.error('Could not decode JSON response')
                return response
        else:
            return response

    def __process_child_connection_groups(self, connection, name, regex, func):
        for child_connection_group in connection.get('childConnectionGroups', []):
            connections = func(child_connection_group, name, regex)
            if connections:
                return connections
        return None

    def __match_connection(self, connection, name, regex):
        if regex:
            return [x for x in connection if re.search(name, x['name'])]
        else:
            return [x for x in connection if x['name'] == name]

    def __get_child_connections(self, connection, name, regex):
        children_connections = connection.get('childConnections', [])
        if children_connections:
            return self.__match_connection(children_connections, name, regex)
        else:
            return None

    def __get_child_connections_group(self, connection_group, name, regex):
        children_connection_groups = connection_group.get('childConnectionGroups')
        if children_connection_groups:
            return self.__match_connection(children_connection_groups, name, regex)
        else:
            return None

    def __get_connection_by_name(self, connections, name, regex=False):
        if 'childConnections' not in connections:
            return self.__process_child_connection_groups(connections, name, regex, self.__get_connection_by_name)
        else:
            child_connections = self.__get_child_connections(connections, name, regex)
            if child_connections:
                return child_connections[0]
            else:
                return self.__process_child_connection_groups(connections, name, regex, self.__get_connection_by_name)

    def __get_connection_group_by_name(self, connection_group, name, regex=False):
        if (regex and re.search(name, connection_group['name'])) or (not regex and connection_group['name'] == name):
            return connection_group
        #
        else:
            child_connections = self.__get_child_connections_group(connection_group, name, regex)
            if child_connections:
                return child_connections[0]
            else:
                return self.__process_child_connection_groups(connection_group, name, regex, self.__get_connection_group_by_name)

    ######################################################################################
    #   Schemas                                                                          #
    ######################################################################################
    def connection_attributes_schema(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/schema/connectionAttributes'
        return self.__auth_request(method='GET', url=url)

    def connection_group_attributes_schema(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/schema/connectionGroupAttributes'
        return self.__auth_request(method='GET', url=url)

    def sharing_profile_attributes_schema(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/schema/sharingProfileAttributes'
        return self.__auth_request(method='GET', url=url)

    def protocols_schema(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/schema/protocols'
        return self.__auth_request(method='GET', url=url)

    def user_attributes_schema(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/schema/userAttributes'
        return self.__auth_request(method='GET', url=url)

    def user_group_attributes_schema(self, datasource=None):
        datasource = datasource or self.primary_datasource
        url = f'{self.REST_API}/session/data/{datasource}/schema/userGroupAttributes'
        return self.__auth_request(method='GET', url=url)
