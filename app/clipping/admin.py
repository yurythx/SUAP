from django.contrib import admin
from django.utils.safestring import mark_safe

from clipping.forms import FonteForm, PublicacaoDigitalForm, PublicacaoEletronicaForm, PublicacaoImpressaForm
from clipping.models import Classificacao, Editorial, Fonte, PalavraChave, PublicacaoDigital, PublicacaoEletronica, PublicacaoImpressa, Veiculo
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import format_


class VeiculoAdmin(ModelAdminPlus):
    ordering = ('nome',)


admin.site.register(Veiculo, VeiculoAdmin)


class EditorialAdmin(ModelAdminPlus):
    ordering = ('nome',)


admin.site.register(Editorial, EditorialAdmin)


class PalavraChaveAdmin(ModelAdminPlus):
    ordering = ('descricao',)


admin.site.register(PalavraChave, PalavraChaveAdmin)


class ClassificacaoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'visivel')


admin.site.register(Classificacao, ClassificacaoAdmin)


class FonteAdmin(ModelAdminPlus):
    list_display = ('nome', 'editorial', 'link', 'ativo')
    search_fields = ('nome', 'editorial', 'link')
    list_filter = ('ativo',)
    ordering = ('nome',)
    form = FonteForm


admin.site.register(Fonte, FonteAdmin)


class PublicacaoDigitalAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('get_texto', 'get_uos', 'get_classificador')
    search_fields = ('titulo', 'subtitulo')
    list_filter = ('classificacao', 'veiculo')
    date_hierarchy = 'data'
    form = PublicacaoDigitalForm

    def get_texto(self, obj):
        html = []
        palavras = ''
        for palavra_chave in obj.palavras_chaves.all():
            palavras += f'{palavra_chave.descricao}, '
        html.append(
            f"""
            <p><strong>{format_(obj.data)} - {obj.veiculo} -{obj.titulo}</strong><p>
            <p>{obj.texto}</p>
            <dl>
                <dt>Palavras-Chaves:</dt>
                <dd>{palavras}</dd>
            </dl>
            <a target="_blank" href="{obj.link}" class="btn float-end">Acessar Notícia</a>
        """
        )
        return mark_safe(' '.join(html))

    get_texto.short_description = 'Notícia'

    def get_uos(self, obj):
        html = ['<ul>']
        for uo in obj.uos.all():
            html.append(f'<li>{uo.sigla}</li>')
        html.append('</ul>')
        return mark_safe(' '.join(html))

    get_uos.short_description = 'Campus'

    def get_classificador(self, obj):
        html = [f"<select onchange=\"jQuery.ajax('/clipping/classificar/{obj.pk}/'+this.options[selectedIndex].value+'/')\">"]
        if not obj.classificacao:
            html.append('<option value="0">-------</option>')
        for classificacao in Classificacao.objects.all():
            if obj.classificacao and obj.classificacao.id == classificacao.id:
                html.append(f'<option value="{classificacao.id}" selected >{classificacao.descricao}</option>')
            else:
                html.append(f'<option value="{classificacao.id}">{classificacao.descricao}</option>')
        html.append('</select>')
        r = ' '.join(html)
        return mark_safe(r)

    get_classificador.short_description = 'Classificador'


admin.site.register(PublicacaoDigital, PublicacaoDigitalAdmin)


class PublicacaoImpressaAdmin(ModelAdminPlus):
    list_display = ('id', 'data', 'veiculo', 'editorial', 'titulo', 'get_link', 'get_uos', 'classificacao', 'pagina', 'colunista')
    search_fields = ('titulo', 'subtitulo')
    list_filter = ('classificacao', 'veiculo')
    date_hierarchy = 'data'
    form = PublicacaoImpressaForm

    def get_link(self, obj):
        if obj.arquivo:
            return mark_safe('<a target="_blank" href="{}">{}</a>'.format(obj.get_link(), obj.arquivo.name.split('/')[-1]))
        return '-'

    get_link.short_description = 'Arquivo'

    def get_uos(self, obj):
        html = ['<ul>']
        for uo in obj.uos.all():
            html.append(f'<li>{uo.sigla}</li>')
        html.append('</ul>')
        return mark_safe(' '.join(html))

    get_uos.short_description = 'Campus'


admin.site.register(PublicacaoImpressa, PublicacaoImpressaAdmin)


class PublicacaoEletronicaAdmin(ModelAdminPlus):
    list_display = ('data', 'veiculo', 'programa', 'titulo', 'get_link', 'get_uos', 'classificacao')
    search_fields = ('titulo', 'programa')
    list_filter = ('classificacao', 'veiculo')
    date_hierarchy = 'data'
    list_display_icons = True
    form = PublicacaoEletronicaForm

    def get_link(self, obj):
        return mark_safe('<a target="_blank" href="{}" class="btn">{}</a>'.format(obj.get_link(), 'Acessar Publicação'))

    get_link.short_description = 'Arquivo'

    def get_uos(self, obj):
        html = ['<ul>']
        for uo in obj.uos.all():
            html.append(f'<li>{uo.sigla}</li>')
        html.append('</ul>')
        return mark_safe(' '.join(html))

    get_uos.short_description = 'Campus'


admin.site.register(PublicacaoEletronica, PublicacaoEletronicaAdmin)
