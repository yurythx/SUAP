from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus
from edu.models import HistoricoEscolarParcial


class HistoricoEscolarParcialAdmin(ModelAdminPlus):
    list_display_icons = True
    fields = ('aluno',)
    search_fields = ('aluno__matricula',)
    list_display = 'aluno', 'emissor', 'data_emissao', 'id_rap', 'status_rap', 'revogado', 'download'

    def download(self, obj):
        html = []
        url_xml = obj.get_url_xml()
        url_pdf = obj.get_url_pdf()
        if url_xml or url_pdf:
            html.append('<ul class="action-bar">')
            if url_xml:
                html.append(
                    f'<li><a target="_blank" href="/edu/baixar_xml_historico_escolar_parcial/{obj.pk}/{obj.get_token_download()}/" class="btn">Baixar XML</a></li>'
                )
            if url_pdf:
                html.append(f'<li><a target="_blank" href="{url_pdf}" class="btn">Baixar PDF</a></li>')
            html.append('</ul>')
        return mark_safe(''.join(html))


admin.site.register(HistoricoEscolarParcial, HistoricoEscolarParcialAdmin)
