from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from sica.models import Componente, Historico, Matriz


class MatrizAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('codigo', 'nome', 'carga_horaria', 'reconhecimento')
    search_fields = ('nome',)
    list_filter = ()
    fieldsets = (
        ('Dados gerais', {'fields': ('codigo', 'nome')}),
        ('Carga Horária', {'fields': (('carga_horaria', 'carga_horaria_estagio'))}),
        ('Reconhecimento', {'fields': ('reconhecimento',)}),
    )


admin.site.register(Matriz, MatrizAdmin)


class ComponenteAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('codigo', 'nome', 'sigla')
    search_fields = ('codigo', 'nome', 'sigla')


admin.site.register(Componente, ComponenteAdmin)


class HistoricoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_filter = ('aluno__situacao', 'aluno__curso_campus', 'matriz')
    list_display = ('aluno', 'matriz', 'aluno__situacao')
    search_fields = ('aluno__matricula', 'aluno__pessoa_fisica__nome')
    exclude = ('componentes_curriculares',)


admin.site.register(Historico, HistoricoAdmin)
