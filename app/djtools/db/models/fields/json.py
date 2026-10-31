from django.db import models

from djtools.utils import get_file_information

from .file import FileFieldPlus


class FileInformationField(models.JSONField):
    """O conteúdo deste field é um dicionário com as informações do arquivo
    conforme saída do método djtools.utils.get_file_information.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default', dict)
        super().__init__(*args, **kwargs)

    @staticmethod
    def save_file_information(model_instance, file_field_name, file_information_field_name):
        file_field = getattr(model_instance, file_field_name)
        file_relative_path = file_field.name
        file_information = get_file_information(file_relative_path, FileFieldPlus.original_filename(file_field))
        setattr(model_instance, file_information_field_name, file_information)
        model_instance.save()
