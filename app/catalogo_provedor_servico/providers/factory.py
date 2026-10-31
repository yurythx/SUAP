from django.conf import settings

try:
    SERVICE_PROVIDER_FACTORY_MODULE_NAME, SERVICE_PROVIDER_FACTORY_CLASS_NAME = settings.SERVICE_PROVIDER_FACTORY.rsplit('.', 1)
except Exception:
    raise Exception(
        "catalogo_provedor_servico: Defina a variavel SERVICE_PROVIDER_FACTORY no settings.py. \nExemplo para o IFRN: SERVICE_PROVIDER_FACTORY = 'catalogo_provedor_servico.providers.impl.ifrn.factory.IfrnServiceProviderFactory'"
    )

_SERVICE_PROVIDER_FACTORY_SINGLETON_INSTANCE = None


def get_service_provider_factory():
    global _SERVICE_PROVIDER_FACTORY_SINGLETON_INSTANCE
    if not _SERVICE_PROVIDER_FACTORY_SINGLETON_INSTANCE:
        module = __import__(
            SERVICE_PROVIDER_FACTORY_MODULE_NAME,
            fromlist=[SERVICE_PROVIDER_FACTORY_CLASS_NAME],
        )
        clazz = getattr(module, SERVICE_PROVIDER_FACTORY_CLASS_NAME)
        _SERVICE_PROVIDER_FACTORY_SINGLETON_INSTANCE = clazz()

    return _SERVICE_PROVIDER_FACTORY_SINGLETON_INSTANCE
