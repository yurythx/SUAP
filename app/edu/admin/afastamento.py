from django.contrib import admin

from edu.models import AfastamentoSalaAula


class AfastamentoSalaAulaInline(admin.TabularInline):
    model = AfastamentoSalaAula
    extra = 1
