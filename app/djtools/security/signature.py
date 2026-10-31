import base64
import hashlib
import hmac


def to_string_bytes(value) -> bytes:
    if isinstance(value, str):
        return value.encode('utf-8')

    if isinstance(value, bytes):
        return value
    #
    raise Exception('Data type not supported (Text only).')


def create_signature(secret_key, message):
    message_to_sign = to_string_bytes(message)
    signature = hmac.new(to_string_bytes(secret_key), message_to_sign, hashlib.sha512)
    return base64.b64encode(signature.digest())


def verify_signature(secret_key, hmac, message):
    return create_signature(secret_key, message) == hmac
