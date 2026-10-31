from django.contrib import admin

from arquivo.forms import TipoArquivoForm
from arquivo.models import Arquivo, Funcao, Processo, TipoArquivo
from djtools.contrib.admin import ModelAdminPlus


class TipoArquivoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao', 'get_processo')
    search_fields = ('descricao',)
    form = TipoArquivoForm

    def get_processo(self, obj):
        return obj.processo

    get_processo.short_description = 'Processo'

    def save_model(self, request, obj, form, change):
        processo_id = request.POST.get('processo')
        processo = Processo.objects.get(id=processo_id)
        obj.save()
        processo.tipos_arquivos.add(obj)


admin.site.register(TipoArquivo, TipoArquivoAdmin)


class ProcessoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    search_fields = ('descricao',)


admin.site.register(Processo, ProcessoAdmin)


class FuncaoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    search_fields = ('descricao',)


admin.site.register(Funcao, FuncaoAdmin)


class ArquivoAdmin(ModelAdminPlus):
    list_display = ('id', 'nome', 'tipo_arquivo', 'processo_protocolo', 'status')
    list_filter = ('tipo_arquivo',)
    search_fields = ('nome',)


admin.site.register(Arquivo, ArquivoAdmin)
