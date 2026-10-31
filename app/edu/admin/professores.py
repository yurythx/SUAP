from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_
from djtools.utils import httprr
from edu.admin.afastamento import AfastamentoSalaAulaInline
from edu.forms import ProfessorExternoForm
from edu.models import ParticipacaoGrupoAtuacao, Professor


class ParticipacaoGrupoAtuacaoInline(admin.TabularInline):
    model = ParticipacaoGrupoAtuacao
    extra = 1


class ProfessorAdmin(ModelAdminPlus):
    form = ProfessorExternoForm
    list_display_icons = True
    list_display = ('get_foto', 'get_dados_gerais', 'display_matricula', 'display_uo')
    list_per_page = 15
    search_fields = Professor.SEARCH_FIELDS
    list_filter = (CustomTabListFilter, 'vinculo__setor__uo', 'vinculo__setor__diretoria', 'vinculo__ativo')
    ordering = ('vinculo__pessoa__nome',)
    export_to_xls = True
    inlines = ParticipacaoGrupoAtuacaoInline, AfastamentoSalaAulaInline

    def get_queryset(self, request, manager=None, *args, **kwargs):
        return super().get_queryset(request, manager, *args, **kwargs).select_related('vinculo__pessoa')

    def has_add_permission(self, request):
        return False

    def get_fieldsets(self, request, obj=None):
        fieldsets = ProfessorExternoForm.fieldsets
        if obj and obj.vinculo.eh_servidor():
            itens_remocao = ['Dados Pessoais', 'RG', 'Endereço']
            fieldsets = [fs for fs in fieldsets if fs[0] not in itens_remocao]
        return fieldsets

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        items.append({'url': '/edu/cadastrar_professor_nao_servidor/', 'label': 'Adicionar Professor Prestador de Serviço'})
        return items

    def get_tabs(self, request):
        return ['tab_servidor_docente', 'tab_servidor_tecnico', 'tab_nao_servidor']

    def tab_servidor_docente(self, request, queryset):
        return queryset.servidores_docentes()

    tab_servidor_docente.short_description = 'Docentes'

    def tab_servidor_tecnico(self, request, queryset):
        return queryset.servidores_tecnicos()

    tab_servidor_tecnico.short_description = 'Técnicos Administrativos'

    def tab_nao_servidor(self, request, queryset):
        return queryset.nao_servidores()

    tab_nao_servidor.short_description = 'Prestadores de Serviço'

    def display_uo(self, obj):
        return obj.get_uo()

    display_uo.short_description = 'Campus'

    def display_nome(self, obj):
        return obj.get_nome()

    display_nome.short_description = 'Nome'

    def response_change(self, request, obj):
        return httprr('..', 'Professor alterado com sucesso.')

    def get_dados_gerais(self, obj):
        show_telefones = ''
        if obj.vinculo.setor and obj.vinculo.setor.setortelefone_set.exists():
            show_telefones = '<dt>Telefones:</dt><dd>{}</dd>'.format(', '.join(obj.vinculo.setor.setortelefone_set.values_list('numero', flat=True)))
        obj_user = obj.vinculo.user
        show_email = obj.vinculo.email_notificacao or obj_user and obj_user.email
        show_cpf = ''
        if self.request.user.has_perm('edu.pode_ver_cpf_professor'):
            show_cpf = f'<dt>CPF:</dt><dd>{obj.vinculo.pessoa.get_cpf_ou_cnpj()}</dd>'
        if obj.vinculo.setor:
            show_setor = obj.vinculo.setor.__str__().format('/')
        else:
            show_setor = '-'
        if show_email:
            show_email = f'<a href="mailto:{show_email}">{show_email}</a>'
        else:
            show_email = '-'
        out = f"""
        <dl>
            <dt>Nome:</dt><dd class="negrito">{obj.vinculo.pessoa.nome}</dd>
            {show_cpf}
            <dt>Setor:</dt><dd>{show_setor}</dd>
            <dt>E-mail:</dt><dd>{show_email}</dd>
            {show_telefones}
        </dl>
        """

        return mark_safe(out)

    get_dados_gerais.short_description = 'Dados gerais'

    def display_matricula(self, obj):
        return obj.get_matricula()

    display_matricula.short_description = 'Matrícula'

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Nome', 'Matrícula', 'Setor', 'E-mail', 'Telefone']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            email = '-'
            if obj.vinculo.user:
                email = obj.vinculo.user.email or '-'
            row = [
                idx + 1,
                format_(obj.vinculo.pessoa.nome),
                format_(obj.get_matricula()),
                format_(obj.vinculo.setor),
                format_(email),
                format_(', '.join(obj.get_telefones())),
            ]
            rows.append(row)
        return rows

    def get_foto(self, obj):
        return mark_safe(f'<img class="img-inside-container" src="{obj.get_foto_75x100_url()}"/>')

    get_foto.short_description = 'Foto'


admin.site.register(Professor, ProfessorAdmin)
