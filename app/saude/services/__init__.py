# APIExterna.get_service() resolve o service_path assumindo o formato "app.modulo.Classe" (3
# segmentos: rsplit('.', 2)[0] vira o app_name checado contra settings.INSTALLED_APPS). Como
# saude.services é um pacote (com rnvacina.py, importacao_rnvacina.py), o service_path cadastrado
# na APIExterna aponta para "saude.services.ApiRNMaisVacinaService" — por isso o reexport abaixo é
# necessário, e não apenas um atalho de import.
from .rnvacina import ApiRNMaisVacinaService  # noqa: F401
