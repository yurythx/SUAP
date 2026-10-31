"""Factories factory_boy de modelos do app ``ponto``.

Reutilizáveis por testes de qualquer app (o dono do modelo provê a factory).
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from ponto.models import Maquina


class MaquinaFactory(DjangoModelFactory):
    """Terminal registrado, já aceito pelo administrador.

    ``ativo`` é ``None`` no model (máquina ainda não aceita); aqui vai ``True``, porque é o
    que os webservices exigem (``Maquina.objects.get(ip=..., ativo=True)``). O ``ip`` é
    ``unique``, então a factory usa ``django_get_or_create`` para ser idempotente.
    """

    class Meta:
        model = Maquina
        django_get_or_create = ('ip',)

    descricao = factory.Sequence(lambda n: f'Terminal {n}')
    # Faixa 10.77.x: fora do 127.0.0.1 (padrão do client de teste) e fora do 10.99.x que os
    # testes do webservice do ``comum`` reservam para IPs declarados à mão.
    ip = factory.Sequence(lambda n: f'10.77.{n // 250}.{n % 250 + 1}')
    ativo = True
