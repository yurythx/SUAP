from django.contrib import admin
from django.urls import path
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.utils import httprr
from edu.forms import EstagioDocenteForm
from edu.models import EstagioDocente


class EstagioDocenteAdmin(ModelAdminPlus):
    form = EstagioDocenteForm
    fieldsets = EstagioDocenteForm.fieldsets
    search_fields = ('matricula_diario__matricula_periodo__aluno__matricula', 'matricula_diario__matricula_periodo__aluno__pessoa_fisica__nome')
    list_display = (
        'nome_aluno',
        'tipo_estagio_docente',
        'get_escola',
        'ch_final',
        'turno',
        'professor_orientador',
        'professor_coordenador',
        'data_inicio',
        'data_fim',
        'get_situacao_estagio',
        'get_situacao_diario',
        'get_opcoes',
    )
    list_display_icons = True
    export_to_xls = True
    list_filter = (
        CustomTabListFilter,
        'matricula_diario__diario__componente_curricular__tipo_estagio_docente',
        'matricula_diario__matricula_periodo__aluno__curso_campus__diretoria__setor__uo',
        'matricula_diario__matricula_periodo__aluno__curso_campus',
        'matricula_diario__matricula_periodo__aluno__polo',
        'matricula_diario__matricula_periodo__ano_letivo',
        'matricula_diario__diario__periodo_letivo',
    )
    change_form_template = 'estagiodocente_change_form.html'
    add_form_template = 'estagiodocente_change_form.html'
    show_count_on_tabs = True

    def get_queryset(self, request, *args, **kwargs):
        return super().get_queryset(request, EstagioDocente.locals)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('notificacao/', self.admin_site.admin_view(self.notificacao))]
        return my_urls + urls

    def notificacao(self, request):
        qs = (
            self.get_queryset(request)
            .exclude(visitaestagiodocente__isnull=False)
            .filter(situacao__in=[EstagioDocente.SITUACAO_AGUARDANDO_ENCERRAMENTO, EstagioDocente.SITUACAO_EM_ANDAMENTO])
        )
        contador = 0
        for obj in qs:
            contador += obj.notificar()
        return httprr(request.META.get('HTTP_REFERER', '..'), f'Foram enviados e-mails referentes à {contador} prática(s) com pendências.')

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        if 'tab' in request.GET:
            items.append(
                {'url': '/admin/edu/estagiodocente/notificacao/?tab={}'.format(request.GET['tab']), 'label': 'Enviar Notificações de Pendências'}
            )
        else:
            if EstagioDocente.objects.filter(escola__isnull=False, local__isnull=True).exists():
                items.append({'url': '/edu/associar_escolas/', 'label': 'Associar Escolas'})
            items.append({'url': '/admin/edu/estagiodocente/notificacao/', 'label': 'Enviar Notificações de Pendências'})
        return items

    def get_tabs(self, request):
        return [
            'tab_aguardando_informacoes_cadastrais',
            'tab_em_andamento',
            'tab_aguardando_visita',
            'tab_aguardando_portfolio',
            'tab_aguardando_encerramento',
            'tab_encerrado',
        ]

    def tab_aguardando_informacoes_cadastrais(self, request, queryset):
        return queryset.filter(situacao=EstagioDocente.SITUACAO_AGUARDANDO_INFORMACOES_CADASTRAIS)

    tab_aguardando_informacoes_cadastrais.short_description = 'Aguardando Informações Cadastrais'

    def tab_em_andamento(self, request, queryset):
        return queryset.filter(situacao=EstagioDocente.SITUACAO_EM_ANDAMENTO)

    tab_em_andamento.short_description = 'Em Andamento'

    def tab_aguardando_visita(self, request, queryset):
        return queryset.filter(
            visitaestagiodocente=None, situacao__in=[EstagioDocente.SITUACAO_EM_ANDAMENTO, EstagioDocente.SITUACAO_AGUARDANDO_ENCERRAMENTO]
        )

    tab_aguardando_visita.short_description = 'Aguardando Visita'

    def tab_aguardando_portfolio(self, request, queryset):
        return queryset.filter(portfolio='', situacao__in=[EstagioDocente.SITUACAO_EM_ANDAMENTO, EstagioDocente.SITUACAO_AGUARDANDO_ENCERRAMENTO])

    tab_aguardando_portfolio.short_description = 'Aguardando Portfólio'

    def tab_aguardando_encerramento(self, request, queryset):
        return queryset.filter(situacao=EstagioDocente.SITUACAO_AGUARDANDO_ENCERRAMENTO)

    tab_aguardando_encerramento.short_description = 'Aguardando Encerramento'

    def tab_encerrado(self, request, queryset):
        return queryset.filter(situacao__in=[EstagioDocente.SITUACAO_ENCERRADO, EstagioDocente.SITUACAO_NAO_CONCLUIDO])

    tab_encerrado.short_description = 'Encerrado'

    def get_situacao_diario(self, obj):
        return obj.matricula_diario.get_situacao_display()

    get_situacao_diario.short_description = 'Situação no Diário'

    def get_situacao_estagio(self, obj):
        if obj.matricula_diario.estagiodocente_set.exclude(situacao__in=[EstagioDocente.SITUACAO_MUDANCA]).count() > 1:
            return obj.get_situacao_display() + ' / ' + 'Concomitante'
        else:
            return obj.get_situacao_display()

    get_situacao_estagio.short_description = 'Situação do Estágio'

    def get_opcoes(self, obj):
        texto = '<ul class="action-bar">'
        if obj.situacao in [obj.SITUACAO_AGUARDANDO_ENCERRAMENTO, obj.SITUACAO_EM_ANDAMENTO]:
            texto = (
                texto
                + f'<li><a class="btn success popup" href="/edu/cadastrar_estagio_docente_concomitante/{obj.pk}/">Adicionar Estágio Concomitante</a></li>'
            )
            texto = (
                texto + f'<li><a class="btn primary popup" href="/edu/mudanca_escola_estagio_docente/{obj.pk}/">Registrar Mudança de Escola</a></li>'
            )
            texto = texto + f'<li><a class="btn warning popup" href="/edu/encerrar_estagio_docente/{obj.pk}/">Encerrar</a></li>'
        texto = texto + '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        if obj:
            aluno = obj.matricula_diario.matricula_periodo.aluno
            context.update({'email_aluno': aluno.email_notificacao})
        return super().render_change_form(request, context, form_url=form_url, add=add, change=change, obj=obj)


admin.site.register(EstagioDocente, EstagioDocenteAdmin)
