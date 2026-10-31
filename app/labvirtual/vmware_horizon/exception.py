import logging

from djtools.utils import requests

logger = logging.getLogger(__name__)


class HorizonException(Exception):
    def __init__(self, message, payload=None):
        self.message = message
        self.payload = payload  # you could add more args

    def __str__(self):
        return str(self.message)


def vmware_horizon_check_error(response, expected_codes=None):
    if expected_codes is None:
        expected_codes = [200]
    if not response.ok:
        logger.error(response.content)
    #
    if response.status_code in [400, 404]:
        json_reponse = response.json()
        error_message = json_reponse.get('error_message', 'unknown')
        raise HorizonException(f'Error {response.status_code}: {error_message}')
    elif response.status_code in [401, 403, 409] or response.status_code not in expected_codes:
        raise Exception(f'Error {response.status_code}: {response.reason}')
    else:
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise HorizonException('Error: ' + str(e))
    return response.status_code
