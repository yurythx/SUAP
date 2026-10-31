import base64
import json

from djtools.utils import get_client_ip
from ponto.models import Maquina


def get_maquina(request, eh_ponto=True, ativo=True):
    ip = get_client_ip(request)

    return Maquina.objects.filter(ip=ip, cliente_ponto=eh_ponto, ativo=ativo).first()


def bytes2str(byte_in: bytes) -> str:
    return base64.b64encode(byte_in).decode('utf-8')


def str2bytes(str_in: str) -> bytes:
    return base64.b64decode(str_in.encode('utf-8'))


class TemplateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, memoryview | bytes):
            return bytes2str(obj)
        return json.JSONEncoder.default(self, obj)
