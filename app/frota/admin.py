import datetime

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import helpers
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from comum.utils import get_uo
from djtools.choices import Situacao
from djtools.contrib.admin import CustomTabListFilter, DateRangeListFilter, ModelAdminPlus, unquote
from djtools.templatetags.filters import format_user
from djtools.templatetags.tags import icon
from djtools.utils import httprr, somar_dias
from edu.models import Aluno
from estacionamento.admin import VeiculoAdmin
from frota.forms import (
    ManutencaoMaquinaForm,
    ManutencaoViaturaForm,
    MaquinaForm,
    MaquinaOrdemAbastecimentoForm,
    MotoristaTemporarioForm,
    ViagemAgendamentoForm,
    ViagemForm,
    ViaturaForm,
    ViaturaOrdemAbastecimentoForm,
)
from frota.models import (
    ManutencaoMaquina,
    ManutencaoViatura,
    Maquina,
    MaquinaOrdemAbastecimento,
    MotoristaTemporario,
    TipoServicoMaquina,
    Viagem,
    ViagemAgendamento,
    ViagemAgendamentoResposta,
    Viatura,
    ViaturaOrdemAbastecimento,
    EdicaoAgendamentoDeferido,
    MultaViagem,
)
from rh.models import UnidadeOrganizacional


class ViaturaAdmin(VeiculoAdmin):
    form = ViaturaForm
    exclude = ('condutores',)
    search_fields = ('modelo__nome', 'placa_codigo_atual', 'placa_municipio_atual__nome', 'cor__nome')
    list_display = (
        'modelo',
        'get_placa',
        'campus',
        'get_lotacao',
        'get_responsavel',
        'get_combustiveis',
        'cor',
        'grupo',
        'get_status',
        'ativo',
        'get_opcoes',
    )
    list_display_icons = True
    list_filter = ('campus', 'ativo')
    fieldsets = (
        (
            None,
            {
                'fields': (
                    'campus',
                    'propria_instituicao',
                    'patrimonio',
                    (
                        'grupo',
                        'modelo',
                    ),
                    (
                        'cor',
                        'ano_fabric',
                    ),
                    ('placa_codigo_atual', 'placa_municipio_atual'),
                    ('placa_codigo_anterior', 'placa_municipio_anterior'),
                    (
                        'lotacao',
                        'odometro',
                    ),
                    (
                        'chassi',
                        'renavam',
                    ),
                    (
                        'potencia',
                        'cilindrada',
                    ),
                    'combustiveis',
                    (
                        'capacidade_tanque',
                        'capacidade_gnv',
                        'rendimento_estimado',
                    ),
                    (
                        'prazo_revisao',
                        'quantidade_km_revisao',
                    ),
                    'obs',
                    'ativo',
                )
            },
        ),
    )

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)

        if not request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            return qs.filter(campus=get_uo(request.user))

        return qs

    def get_opcoes(self, obj):
        if obj.patrimonio:
            return mark_safe(f'<a href="/patrimonio/inventario/{obj.patrimonio.numero}/" class="btn default">Inventário</a>')
        return '-'

    get_opcoes.short_description = 'Opções'

    def get_status(self, obj):
        return mark_safe(obj.get_status())

    get_status.short_description = 'Situação'

    def get_placa(self, obj):
        return mark_safe(f'{obj.placa_codigo_atual}')

    get_placa.short_description = 'Placa'

    def get_uo(self, obj):
        return mark_safe(f'{obj.get_uo()}')

    get_uo.short_description = 'Campus'

    def get_responsavel(self, obj):
        return f'{obj.get_responsavel()}'

    get_responsavel.short_description = 'Responsável (SIAPE)'

    def get_lotacao(self, obj):
        return obj.lotacao

    get_lotacao.short_description = 'Lotação'


admin.site.register(Viatura, ViaturaAdmin)


class MotoristaTemporarioAdmin(ModelAdminPlus):
    form = MotoristaTemporarioForm
    list_display = ('get_pessoa', 'portaria', 'get_ano', 'data_inicio', 'data_limite', 'get_portaria')
    list_filter = (CustomTabListFilter,)
    list_display_icons = True

    fieldsets = ((None, {'fields': ('vinculo_pessoa', ('portaria', 'ano_portaria'), ('validade_inicial', 'validade_final'), 'obs', 'arquivo')}),)

    def data_inicio(self, obj):
        return obj.validade_inicial

    def get_pessoa(self, obj):
        return f'{obj.vinculo_pessoa.pessoa.nome}'

    get_pessoa.short_description = 'Motoristas Temporários'

    def data_limite(self, obj):
        if obj.validade_final:
            return mark_safe(obj.validade_final)
        else:
            return mark_safe('<span class="status status-alert">Não informada</span>')

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            return qs
        else:
            return qs.filter(vinculo_pessoa__setor__uo=get_uo(request.user))

    def get_tabs(self, request):
        return ['tab_vigente', 'tab_expirado']

    def tab_vigente(self, request, queryset):
        hoje = datetime.date.today()
        return queryset.filter(Q(validade_final__gte=hoje) | Q(validade_final__isnull=True))

    tab_vigente.short_description = 'Com Portarias Vigentes'

    def tab_expirado(self, request, queryset):
        hoje = datetime.date.today()
        return queryset.filter(validade_final__lt=hoje)

    tab_expirado.short_description = 'Com Portarias Expiradas'

    def get_portaria(self, obj):
        if obj.arquivo:
            return mark_safe(f"<a href='{obj.arquivo.url}' class='btn'>Visualizar Arquivo</a>")
        return '-'

    get_portaria.short_description = 'Arquivo'

    def get_ano(self, obj):
        if obj.ano_portaria:
            return mark_safe(obj.ano_portaria)
        else:
            return mark_safe("<span class='status status-alert'>Não informado</span>")

    get_ano.short_description = 'Ano da Portaria'

    def save_model(self, request, obj, form, change):
        obj.pessoa = form.cleaned_data['vinculo_pessoa'].user.get_profile()
        obj.save()


admin.site.register(MotoristaTemporario, MotoristaTemporarioAdmin)


class AgendamentoSetorFilter(admin.RelatedOnlyFieldListFilter):
    def field_choices(self, field, request, model_admin):
        uo = request.GET.get('setor__uo__id__exact')
        if uo:
            qs = model_admin.get_queryset(request).filter(setor__uo=uo)
        else:
            if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
                qs = model_admin.get_queryset(request).distinct()
            else:
                qs = model_admin.get_queryset(request).filter(pk=get_uo(request.user).id)
        pk_qs = qs.values_list(f'{self.field_path}__pk', flat=True)
        return field.get_choices(include_blank=False, limit_choices_to={'pk__in': pk_qs})


class ViagemAgendamentoCampusListFilter(admin.RelatedOnlyFieldListFilter):
    def field_choices(self, field, request, model_admin):
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
            qs = model_admin.get_queryset(request).distinct()
        else:
            qs = model_admin.get_queryset(request).filter(setor__uo=get_uo(request.user))
        pk_qs = qs.values_list(f'{self.field_path}__setor__uo__pk', flat=True)
        return field.get_choices(include_blank=False, limit_choices_to={'pk__in': pk_qs})


class EdicaoPendenteFilter(admin.SimpleListFilter):
    title = 'Com edição pendente de validação'
    parameter_name = 'edicao_pendente'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))

        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(id__in=EdicaoAgendamentoDeferido.objects.filter(deferida=None).values_list('agendamento', flat=True))
        elif self.value() == '2':
            return queryset.exclude(id__in=EdicaoAgendamentoDeferido.objects.filter(deferida=None).values_list('agendamento', flat=True))


class ViagemAgendamentoAdmin(ModelAdminPlus):
    form = ViagemAgendamentoForm
    list_display = (
        'get_acoes',
        'id',
        'get_solicitante',
        'get_responsavel',
        'setor',
        'data_saida',
        'data_chegada',
        'objetivo',
        'get_campus_viatura',
        'get_autorizado',
        'get_situacao',
        'get_opcoes',
    )
    list_filter = (
        CustomTabListFilter,
        ('setor__uo', ViagemAgendamentoCampusListFilter),
        ('setor', AgendamentoSetorFilter),
        'status',
        EdicaoPendenteFilter,
    )
    date_hierarchy = 'data_saida'
    show_count_on_tabs = True
    search_fields = ('id', 'objetivo', 'intinerario', 'local_saida')
    filters_ajax = False

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
            qs = qs.filter(setor__uo=get_uo(request.user))
        return qs

    def get_acoes(self, obj):
        user_do_usuario = self.request.user
        vinculo_do_usuario = user_do_usuario.get_vinculo()
        uo_usuario = get_uo(user_do_usuario)
        eh_do_campus = obj.setor and obj.setor.uo == uo_usuario
        outro_campus_usa_viatura = (
            obj.is_deferido() and obj.viagemagendamentoresposta.viatura and obj.viagemagendamentoresposta.viatura.get_uo() == uo_usuario.sigla
        )
        pode_editar = True
        if not user_do_usuario.has_perm('frota.change_viagemagendamento'):
            pode_editar = False

        if user_do_usuario.has_perm('frota.tem_acesso_agendamento_agendador') and (
            obj.vinculo_solicitante != vinculo_do_usuario or not obj.is_pendente()
        ):
            pode_editar = False
        if user_do_usuario.has_perm('frota.tem_acesso_agendamento_operador'):
            if eh_do_campus or outro_campus_usa_viatura:
                pode_editar = True
            else:
                pode_editar = False

        mostra_acoes = icon('view', f'/frota/agendamento/{obj.id}/')
        if pode_editar:
            mostra_acoes = mostra_acoes + icon('edit', f'/admin/frota/viagemagendamento/{obj.id}/')
        elif (
            (
                (self.request.user.has_perm('frota.tem_acesso_agendamento_operador') and (eh_do_campus or outro_campus_usa_viatura))
                or (obj.vinculo_solicitante == self.request.user.get_vinculo())
            )
            and obj.is_deferido()
            and not obj.viagem_em_andamento()
        ):
            mostra_acoes = mostra_acoes + icon('edit', f'/frota/editar_agendamento_deferido/{obj.id}/', extra_class='popup')
        return mark_safe(mostra_acoes)

    get_acoes.short_description = 'Ações'

    def get_tabs(self, request):
        return ['tab_ultimos_agendamentos', 'tab_agendamentos_futuros', 'tab_agendamentos_pendentes_autorizacao', 'tab_any_data']

    def tab_ultimos_agendamentos(self, request, queryset):
        limite_inferior = somar_dias(datetime.date.today(), -30)
        limite_superior = datetime.date.today()
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
            return queryset.filter(data_saida__gt=limite_inferior, data_saida__lt=limite_superior).order_by('-data_saida')
        else:
            return queryset.filter(data_saida__gt=limite_inferior, data_saida__lt=limite_superior, setor__uo=get_uo(request.user)).order_by(
                '-data_saida'
            )

    tab_ultimos_agendamentos.short_description = 'Últimos Agendamentos'

    def tab_agendamentos_futuros(self, request, queryset):
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
            return queryset.filter(data_saida__gte=datetime.datetime.now()).order_by('data_saida')
        else:
            return queryset.filter(data_saida__gte=datetime.datetime.now(), setor__uo=get_uo(request.user)).order_by('data_saida')

    tab_agendamentos_futuros.short_description = 'Agendamentos Futuros'

    def tab_agendamentos_pendentes_autorizacao(self, request, queryset):
        retorno = queryset.filter(data_saida__gte=datetime.datetime.now(), avaliado_em__isnull=True, status=Situacao.PENDENTE).order_by('data_saida')
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
            return retorno
        else:
            return retorno.filter(setor__uo=get_uo(request.user))

    tab_agendamentos_pendentes_autorizacao.short_description = 'Pendentes de Autorização da Chefia'

    def tab_any_data(self, request, queryset):
        return queryset.order_by('-data_saida')

    tab_any_data.short_description = 'Todos'

    def get_situacao(self, obj):
        return mark_safe(obj.get_situacao(self.request.user))

    get_situacao.short_description = 'Situação'

    def get_autorizado(self, obj):
        return mark_safe(obj.get_autorizado(self.request.user))

    get_autorizado.short_description = 'Autorizado'

    def get_solicitante(self, obj):
        if obj.vinculo_solicitante and obj.vinculo_solicitante.user:
            return format_user(obj.vinculo_solicitante.user)
        return obj.vinculo_solicitante

    get_solicitante.short_description = 'Solicitante'

    def get_responsavel(self, obj):
        if obj.nome_responsavel:
            return f'{obj.nome_responsavel} - {obj.telefone_responsavel}'

    get_responsavel.short_description = 'Responsável'

    def get_campus_viatura(self, obj):
        if obj.is_deferido():
            avaliacao = obj.viagemagendamentoresposta
            return avaliacao and avaliacao.viatura and avaliacao.viatura.get_uo()
        return '-'

    get_campus_viatura.short_description = 'Campus da viatura'

    def get_opcoes(self, obj):
        mostra_opcoes = '<ul class="action-bar">'
        if obj.status != Situacao.PENDENTE and (
            self.request.user.has_perm('frota.tem_acesso_agendamento_sistemico') or self.request.user.has_perm('frota.tem_acesso_agendamento_campus')
        ):
            if ViagemAgendamentoResposta.objects.filter(agendamento=obj).exists():
                mostra_opcoes += f'<li><a href="/frota/avaliar_agendamento_viagem/{obj.id}/" class="btn primary">Editar</a></li>'
                if obj.status == Situacao.DEFERIDA and (
                    self.request.user.has_perm('frota.tem_acesso_viagem_sistemico')
                    or self.request.user.has_perm('frota.tem_acesso_viagem_campus')
                    or self.request.user.has_perm('frota.tem_acesso_viagem_operador')
                ):
                    resp_agendamento = get_object_or_404(ViagemAgendamentoResposta, agendamento=obj)
                    mostra_opcoes += f'<li><a class="btn" href="/frota/pdf_requisicao/{resp_agendamento.id}/">Requisição de Transporte</a></li>'

        if obj.tem_solicitacao_edicao():
            mostra_opcoes += f'<li><a class="btn default popup" href="/frota/ver_solicitacoes_edicao/{obj.id}/">Ver solicitações de edição</a></li>'
        string = self.request.get_full_path()
        if '?' in string:
            string = string.split('?')[1]
        else:
            string = ''
        mostra_opcoes += f'<li><a class="btn default" href="/frota/ver_calendario_agendamento/?{string}">Ver Calendário</a></li>'
        mostra_opcoes += '</ul>'
        return mark_safe(mostra_opcoes)

    get_opcoes.short_description = 'Opções'

    def response_change(self, request, obj):
        self.message_user(request, 'Agendamento alterado com sucesso.')
        return HttpResponseRedirect(f'/frota/agendamento/{obj.pk}/')

    def save_model(self, request, obj, form, change):
        obj.solicitante = form.cleaned_data['vinculo_solicitante'].user.get_profile()
        obj.save()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        turmas = form.cleaned_data.get('turma')
        lista_alunos = form.cleaned_data.get('lista_alunos')
        diarios = form.cleaned_data.get('diario')
        if turmas:
            for turma in turmas:
                matriculas = turma.get_alunos_matriculados().union(turma.get_alunos_matriculados_diarios())
                for matricula in matriculas:
                    form.instance.vinculos_passageiros.add(matricula.aluno.vinculos.all()[0])
                    form.instance.save()

        if lista_alunos:
            matriculas = lista_alunos.split(',')
            for matricula in matriculas:
                aluno = Aluno.objects.filter(matricula=matricula)
                if aluno.exists():
                    form.instance.vinculos_passageiros.add(aluno[0].vinculos.all()[0])
                    form.instance.save()

        if diarios:
            for diario in diarios:
                alunos = Aluno.objects.filter(matriculaperiodo__matriculadiario__diario=diario)
                if alunos.exists():
                    for aluno in alunos:
                        form.instance.vinculos_passageiros.add(aluno.vinculos.all()[0])

                        form.instance.save()

        form.instance.save()

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        if self.has_add_permission(request):
            string = request.get_full_path()
            if '?' in string:
                string = string.split('?')[1]
            else:
                string = ''
            items.append({'url': f'/frota/ver_calendario_agendamento/?{string}', 'label': 'Ver no Calendário', 'css_class': 'default'})
        return items


admin.site.register(ViagemAgendamento, ViagemAgendamentoAdmin)


class ViaturaOrdemAbastecimentoListFilter(admin.SimpleListFilter):
    title = 'Viatura'
    parameter_name = 'id'

    def lookups(self, request, model_admin):
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            if request.GET.get('campus'):
                viaturas = Viatura.objects.filter(campus=request.GET.get('campus'))
            else:
                viaturas = Viatura.objects.all()

        else:
            viaturas = Viatura.objects.filter(campus=get_uo(request.user))
        return viaturas.values_list('id', 'placa_codigo_atual')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(viatura=self.value())


class OrdemAbastecimentoCampusListFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'campus'

    def lookups(self, request, model_admin):
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            uo = UnidadeOrganizacional.objects.suap().all()
        else:
            uo = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(request.user).id)
        return uo.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(viatura__campus=self.value())


class ViaturaOrdemAbastecimentoAdmin(ModelAdminPlus):
    form = ViaturaOrdemAbastecimentoForm
    list_display = (
        'id',
        'viatura',
        'get_campus',
        'data',
        'cupom_fiscal',
        'combustivel',
        'quantidade',
        'valor_total_nf',
        'get_nota_fiscal',
        'get_opcoes',
    )
    list_filter = (
        OrdemAbastecimentoCampusListFilter,
        ViaturaOrdemAbastecimentoListFilter,
        'validada',
        ('data', DateRangeListFilter),
    )
    search_fields = ('data', 'viatura__placa_codigo_atual')
    date_hierarchy = 'data'
    list_display_icons = True

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        eh_motorista = (
            not request.user.has_perm('frota.tem_acesso_viagem_sistemico')
            and not request.user.has_perm('frota.tem_acesso_viagem_campus')
            and not request.user.has_perm('frota.tem_acesso_viagem_operador')
        )
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            return qs.order_by('-data')
        elif not eh_motorista:
            return qs.filter(viatura__campus=get_uo(request.user)).order_by('-data')
        else:
            return qs.filter(informada_por=request.user.get_vinculo()).order_by('-data')

    def get_nota_fiscal(self, obj):
        if obj.arquivo:
            return mark_safe(f"<a href='{obj.arquivo.url}' class='btn default'>Visualizar Nota Fiscal</a>")
        return '-'

    get_nota_fiscal.short_description = 'Nota Fiscal'

    def get_campus(self, obj):
        return mark_safe(obj.get_campus())

    get_campus.short_description = 'Campus'

    def get_opcoes(self, obj):
        texto = ''
        eh_motorista = (
            not self.request.user.has_perm('frota.tem_acesso_viagem_sistemico')
            and not self.request.user.has_perm('frota.tem_acesso_viagem_campus')
            and not self.request.user.has_perm('frota.tem_acesso_viagem_operador')
        )
        if not eh_motorista and not obj.validada:
            texto = f'<ul class="action-bar"><li><a href="/frota/validar_ordem_abastecimento/{obj.pk}/" class="btn success popup confirm">Validar ordem</a></li></ul>'

        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'


admin.site.register(ViaturaOrdemAbastecimento, ViaturaOrdemAbastecimentoAdmin)


class MultaPendenteFilter(admin.SimpleListFilter):
    title = 'Com multa pendente de comprovante de pagamento'
    parameter_name = 'multa_pendente'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))

        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(id__in=MultaViagem.objects.filter(Q(comprovante='') | Q(comprovante=None)).values_list('viagem', flat=True))
        elif self.value() == '2':
            return queryset.exclude(id__in=MultaViagem.objects.filter(Q(comprovante='') | Q(comprovante=None)).values_list('viagem', flat=True))


class SaidaPendenteFilter(admin.SimpleListFilter):
    title = 'Com registro de saída pendente de validação'
    parameter_name = 'saida_pendente'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))

        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(saida_validada=False)
        elif self.value() == '2':
            return queryset.filter(saida_validada=True)


class ChegadaPendenteFilter(admin.SimpleListFilter):
    title = 'Com registro de chegada pendente de validação'
    parameter_name = 'chegada_pendente'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))

        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(chegada_validada=False).exclude(chegada_odometro=None)
        elif self.value() == '2':
            return queryset.filter(chegada_validada=True).exclude(chegada_odometro=None)


class ViagemAdmin(ModelAdminPlus):
    form = ViagemForm
    list_display = ('get_id', 'viatura', 'get_objetivo', 'get_itinerario', 'saida_data', 'chegada_data', 'get_motoristas', 'get_opcoes')
    list_filter = (
        OrdemAbastecimentoCampusListFilter,
        ViaturaOrdemAbastecimentoListFilter,
        ('saida_data', DateRangeListFilter),
        MultaPendenteFilter,
        SaidaPendenteFilter,
        ChegadaPendenteFilter,
    )
    list_display_icons = True
    ordering = ('-saida_data',)
    search_fields = (
        'agendamento_resposta__agendamento__id',
        'agendamento_resposta__agendamento__objetivo',
        'agendamento_resposta__agendamento__intinerario',
    )
    export_to_xls = True

    def get_id(self, obj):
        return mark_safe(obj.agendamento_resposta.agendamento.id)

    get_id.short_description = 'ID'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        viagem_a_editar = self.get_object(request, unquote(object_id))
        if not request.user.has_perm('frota.tem_acesso_viagem_sistemico') and viagem_a_editar and not viagem_a_editar.tem_descontinuidade():
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if retorno and obj is not None:
            if not request.user.has_perm('frota.tem_acesso_viagem_sistemico') and not obj.tem_descontinuidade():
                retorno = False

        return retorno

    def response_change(self, request, obj):
        return httprr('..', 'Viagem atualizada com sucesso.')

    def get_queryset(self, request, *args, **kwargs):
        queryset = super().get_queryset(request, *args, **kwargs)
        if not any([request.user.is_superuser, request.user.has_perm('frota.tem_acesso_viagem_sistemico')]):
            queryset = queryset.filter(agendamento_resposta__agendamento__setor__uo=get_uo(request.user))
        return queryset.prefetch_related('motoristas__relacionamento')

    def get_motoristas(self, obj):
        return ', '.join([str(motorista) for motorista in obj.motoristas.all()])

    get_motoristas.short_description = 'Motoristas'
    get_motoristas.admin_order_field = 'motoristas'

    def get_objetivo(self, obj):
        return obj.agendamento_resposta.agendamento.objetivo

    get_objetivo.short_description = 'Objetivo'

    def get_itinerario(self, obj):
        return obj.agendamento_resposta.agendamento.intinerario

    get_itinerario.short_description = 'Itinerário'

    def get_opcoes(self, obj):
        texto = f'<ul class="action-bar"><li><a href="/frota/cadastrar_multa/{obj.pk}/" class="btn success popup">Registrar multa</a></li>'
        if obj.multaviagem_set.exists():
            texto += f'<li><a href="/frota/visualizar_multas/{obj.pk}/" class="btn primary popup">Visualizar multas</a></li>'
        if not obj.saida_validada:
            texto += f'<li><a href="/frota/validar_saida/{obj.pk}/" class="btn success popup confirm">Validar registro de saída</a></li>'
        if obj.chegada_odometro and not obj.chegada_validada:
            texto += f'<li><a href="/frota/validar_chegada/{obj.pk}/" class="btn success popup confirm">Validar registro de chegada</a></li>'

        texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'ID',
            'Viatura',
            'Objetivo da Viagem',
            'Itinerario',
            'Data da Saída',
            'Data da Chegada',
            'Motorista',
            'Campus do Cadastro da viagem',
            'Setor Solicitante',
            'Odômetro na saída',
            'Odômetro na Chegada',
        ]
        rows = [header]
        queryset = queryset.select_related(
            'agendamento_resposta',
            'agendamento_resposta__agendamento',
            'viatura',
            'viatura__modelo',
            'viatura__modelo__marca',
            'agendamento_resposta__agendamento__setor',
            'agendamento_resposta__agendamento__setor__uo',
        ).prefetch_related('motoristas__relacionamento')
        for idx, obj in enumerate(processo.iterate(queryset)):
            setor = obj.agendamento_resposta.agendamento.setor
            uo = setor.uo if setor else None
            row = [
                idx + 1,
                mark_safe(obj.agendamento_resposta.agendamento.id),
                obj.viatura,
                self.get_objetivo(obj),
                self.get_itinerario(obj),
                obj.saida_data,
                obj.chegada_data,
                self.get_motoristas(obj),
                uo,
                setor,
                obj.saida_odometro,
                obj.chegada_odometro,
            ]
            rows.append(row)
        return rows


admin.site.register(Viagem, ViagemAdmin)


class ManutencaoViaturaAdmin(ModelAdminPlus):
    form = ManutencaoViaturaForm
    list_display = ('get_acoes', 'viatura', 'data', 'tipo_servico', 'valor_total_pecas', 'valor_total_servico', 'get_nf_pecas', 'get_nf_servicos')
    date_hierarchy = 'data'
    list_filter = (
        OrdemAbastecimentoCampusListFilter,
        ViaturaOrdemAbastecimentoListFilter,
        'tipo_servico',
        ('data', DateRangeListFilter),
    )
    export_to_xls = True
    actions = [
        'baixar_notas_fiscais',
    ]
    actions_on_top = True
    actions_on_bottom = True

    def get_acoes(self, obj):
        return mark_safe(''.join([icon('view', f'/frota/manutencaoviatura/{obj.id}/'), icon('edit', f'/admin/frota/manutencaoviatura/{obj.id}/')]))

    get_acoes.short_description = 'Ações'

    def get_nf_pecas(self, obj):
        if obj.arquivo_nf_pecas:
            return mark_safe(f"<a href='{obj.arquivo_nf_pecas.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_nf_pecas.short_description = 'Nota Fiscal das Peças'

    def get_nf_servicos(self, obj):
        if obj.arquivo_nf_servicos:
            return mark_safe(f"<a href='{obj.arquivo_nf_servicos.url}' class='btn'>Visualizar Arquivo</a>")
        return '-'

    get_nf_servicos.short_description = 'Nota Fiscal dos Serviços'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Viatura',
            'Data',
            'Tipo de Serviço',
            'Valor Total da Nota Fiscal de Peças (R$)',
            'Valor Total da Nota Fiscal de Serviços (R$)',
            'Link - Nota Fiscal das Peças',
            'Link - Nota Fiscal dos Serviços',
        ]
        rows = [header]

        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.viatura,
                obj.data,
                obj.tipo_servico,
                obj.valor_total_pecas,
                obj.valor_total_servico,
                obj.arquivo_nf_pecas and f'{settings.SITE_URL}{obj.arquivo_nf_pecas.url}',
                obj.arquivo_nf_servicos and f'{settings.SITE_URL}{obj.arquivo_nf_servicos.url}',
            ]
            rows.append(row)
        return rows

    def baixar_notas_fiscais(self, request, queryset):
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/frota/baixar_notas_fiscais_servicos/?ids={}'.format(','.join(selected)))


admin.site.register(ManutencaoViatura, ManutencaoViaturaAdmin)


class MaquinaCampusListFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'campus'

    def lookups(self, request, model_admin):
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_maquina_sistemico'):
            uo = UnidadeOrganizacional.objects.suap().all()
        else:
            uo = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(request.user).id)
        return uo.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(campus=self.value())


class MaquinaAdmin(ModelAdminPlus):
    form = MaquinaForm
    list_display = ('descricao', 'campus', 'capacidade_tanque', 'consumo_anual_estimado')
    list_filter = (MaquinaCampusListFilter,)
    list_display_icons = True
    search_fields = ('descricao',)


admin.site.register(Maquina, MaquinaAdmin)


class MaquinaOrdemAbastecimentoListFilter(admin.SimpleListFilter):
    title = 'Máquina'
    parameter_name = 'id'

    def lookups(self, request, model_admin):
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_maquina_sistemico'):
            if request.GET.get('campus'):
                maquinas = Maquina.objects.filter(campus=request.GET.get('campus'))
            else:
                maquinas = Maquina.objects.all()

        else:
            maquinas = Maquina.objects.filter(campus=get_uo(request.user))
        return maquinas.values_list('id', 'descricao')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(maquina=self.value())


class MaquinaOrdemAbastecimentoCampusListFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'campus'

    def lookups(self, request, model_admin):
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_maquina_sistemico'):
            uo = UnidadeOrganizacional.objects.suap().all()
        else:
            uo = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(request.user).id)
        return uo.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(maquina__campus=self.value())


class MaquinaOrdemAbastecimentoAdmin(ModelAdminPlus):
    form = MaquinaOrdemAbastecimentoForm
    list_display = ('get_maquina', 'get_campus', 'data', 'cupom_fiscal', 'combustivel', 'quantidade', 'valor_total_nf', 'get_nota_fiscal')
    list_filter = (MaquinaOrdemAbastecimentoCampusListFilter, MaquinaOrdemAbastecimentoListFilter)
    date_hierarchy = 'data'
    list_display_icons = True

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if request.user.is_superuser or request.user.has_perm('frota.tem_acesso_maquina_sistemico'):
            return qs.order_by('-data')
        else:
            return qs.filter(maquina__campus=get_uo(request.user)).order_by('-data')

    def get_nota_fiscal(self, obj):
        if obj.arquivo_nf:
            return mark_safe(f"<a href='{obj.arquivo_nf.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_nota_fiscal.short_description = 'Nota Fiscal'

    def get_campus(self, obj):
        if obj.maquina.campus:
            return mark_safe(obj.maquina.campus)
        else:
            return '-'

    get_campus.short_description = 'Campus'

    def get_maquina(self, obj):
        return mark_safe(obj.maquina)

    get_maquina.short_description = 'Máquina'


admin.site.register(MaquinaOrdemAbastecimento, MaquinaOrdemAbastecimentoAdmin)


class TipoServicoMaquinaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')


admin.site.register(TipoServicoMaquina, TipoServicoMaquinaAdmin)


class ManutencaoMaquinaAdmin(ModelAdminPlus):
    form = ManutencaoMaquinaForm
    list_display = (
        'get_acoes',
        'get_campus',
        'maquina',
        'data',
        'tipo_servico',
        'valor_total_pecas',
        'valor_total_servico',
        'get_nf_pecas',
        'get_nf_servicos',
    )
    date_hierarchy = 'data'
    list_filter = ('maquina__campus', 'maquina', 'tipo_servico')

    def get_acoes(self, obj):
        return mark_safe(''.join([icon('view', f'/frota/manutencaomaquina/{obj.id}/'), icon('edit', f'/admin/frota/manutencaomaquina/{obj.id}/')]))

    get_acoes.short_description = 'Ações'

    def get_nf_pecas(self, obj):
        if obj.arquivo_nf_pecas:
            return mark_safe(f"<a href='{obj.arquivo_nf_pecas.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_nf_pecas.short_description = 'Nota Fiscal da Peças'

    def get_nf_servicos(self, obj):
        if obj.arquivo_nf_servicos:
            return mark_safe(f"<a href='{obj.arquivo_nf_servicos.url}' class='btn'>Visualizar Arquivo</a>")
        return '-'

    get_nf_servicos.short_description = 'Nota Fiscal dos Serviços'

    def get_campus(self, obj):
        return obj.maquina.campus

    get_campus.short_description = 'Campus'


admin.site.register(ManutencaoMaquina, ManutencaoMaquinaAdmin)
