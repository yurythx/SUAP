import datetime

from dateutil.relativedelta import relativedelta
from django.contrib import admin, messages
from django.db.models import F, OuterRef, Subquery
from django.utils.safestring import mark_safe

from auxilioemergencial.forms import (
    EditalForm,
)
from auxilioemergencial.models import (
    DEFERIDO,
    SEM_PARECER,
    Edital,
    InscricaoAluno,
    InscricaoAlunoConectado,
    InscricaoDispositivo,
    InscricaoInternet,
    InscricaoMaterialPedagogico,
)
from comum.models import Ano
from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import format_
from edu.models import MatriculaPeriodo, Modalidade, SituacaoMatriculaPeriodo


def get_inscricoes_anteriores(obj):
    lista = []
    if InscricaoInternet.objects.filter(aluno=obj.aluno).exclude(edital=obj.edital).exists():
        lista.append('Serviço de Internet')
    if InscricaoDispositivo.objects.filter(aluno=obj.aluno).exclude(edital=obj.edital).exists():
        lista.append('Aquisição de Dispositivo Eletrônico')
    if InscricaoMaterialPedagogico.objects.filter(aluno=obj.aluno).exclude(edital=obj.edital).exists():
        lista.append('Material Didático Pedagógico')
    if InscricaoAlunoConectado.objects.filter(aluno=obj.aluno).exclude(edital=obj.edital).exists():
        lista.append('Projeto Alunos Conectados')
    return ', '.join(lista)


def get_opcoes(obj, request):
    texto = '<ul class="action-bar">'
    if not obj.pendente_assinatura():
        if request.user.has_perm('auxilioemergencial.add_edital'):
            if obj.parecer != SEM_PARECER:
                texto += f'<li><a href="/auxilioemergencial/parecer_inscricao/{obj.get_tipo_auxilio()}/{obj.pk:d}/" class="btn primary"><span class="fas fa-edit" aria-hidden="true"></span> Editar Parecer</a></li>'
            else:
                texto += f'<li><a href="/auxilioemergencial/parecer_inscricao/{obj.get_tipo_auxilio()}/{obj.pk:d}/" class="btn success"><span class="fas fa-plus" aria-hidden="true"></span> Adicionar Parecer</a></li>'
        if obj.parecer == DEFERIDO and obj.get_tipo_auxilio() == 'DIS':
            if obj.prestacao_contas_cadastrada_em:
                texto += f'<li><a href="/auxilioemergencial/prestacao_contas_dispositivo/{obj.pk:d}/" class="btn primary"><span class="fas fa-edit" aria-hidden="true"></span> Atualizar Prestação de Contas</a></li>'
            else:
                texto += f'<li><a href="/auxilioemergencial/prestacao_contas_dispositivo/{obj.pk:d}/" class="btn success"><span class="fas fa-plus" aria-hidden="true"></span> Adicionar Prestação de Contas</a></li>'
    if request.user.has_perm('auxilioemergencial.add_edital'):
        texto += f'<li><a href="/auxilioemergencial/atualizar_dados_bancarios/{obj.aluno.id}/" class="btn primary"><span class="fas fa-edit" aria-hidden="true"></span> Atualizar Dados Bancários</a></li>'
        texto += f'<li><a href="/auxilioemergencial/comprovante_inscricao/{obj.get_tipo_auxilio()}/{obj.pk:d}/" class="btn default"><span class="fas fa-eye" aria-hidden="true"></span> Comprovante de Inscrição</a></li>'
        texto += f'<li><a href="/auxilioemergencial/documentacao_aluno/{obj.aluno.pk}/{obj.get_tipo_auxilio()}/{obj.pk}/" class="btn default"><span class="fas fa-tasks" aria-hidden="true"></span> Documentação</a></li>'

        if obj.pode_encerrar():
            texto += f'<li><a href="/auxilioemergencial/encerrar_auxilio/{obj.get_tipo_auxilio()}/{obj.pk}/" class="btn danger"><span class="fas fa-times-circle" aria-hidden="true"></span> Encerrar Auxílio</a></li>'

    texto += '</ul>'
    return mark_safe(texto)


class EditalAdmin(ModelAdminPlus):
    list_display = ('descricao', 'campus', 'data_inicio', 'data_termino', 'get_tipos_auxilios', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('descricao',)
    list_display_icons = True
    form = EditalForm

    def get_tipos_auxilios(self, obj):
        programas = []
        for programa in obj.tipo_auxilio.all():
            programas.append(programa.titulo)
        return ', '.join(programas)

    get_tipos_auxilios.short_description = 'Tipos de Auxílios'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs


admin.site.register(Edital, EditalAdmin)


class EnvioFilter(admin.SimpleListFilter):
    title = 'Pendente após envio de Documentação'
    parameter_name = 'pendentes_pos_envio'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(data_limite_envio_documentacao__isnull=False, parecer=SEM_PARECER)
        elif self.value() == '2':
            return queryset.exclude(data_limite_envio_documentacao__isnull=False, parecer=SEM_PARECER)


class DocumentacaoCadastradaFilter(admin.SimpleListFilter):
    title = 'Cadastrou documentos'
    parameter_name = 'cadastrou_documentos'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(documentacao_atualizada_em__isnull=False)
        elif self.value() == '2':
            return queryset.exclude(documentacao_atualizada_em__isnull=False)


class DocumentacaoSolicitadaFilter(admin.SimpleListFilter):
    title = 'Teve documentação solicitada'
    parameter_name = 'documentacao_solicitada'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(documentacao_pendente__isnull=False)
        elif self.value() == '2':
            return queryset.exclude(documentacao_pendente__isnull=False)


class DocumentoPosParecerFilter(admin.SimpleListFilter):
    title = 'Enviou documentação após parecer'
    parameter_name = 'documentacao_pos_parecer'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(documentacao_atualizada_em__gt=F('data_parecer'))
        elif self.value() == '2':
            return queryset.exclude(documentacao_atualizada_em__gt=F('data_parecer'))


class FICFilter(admin.SimpleListFilter):
    title = 'Modalidade FIC'
    parameter_name = 'fic'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(aluno__curso_campus__modalidade__pk__in=[Modalidade.FIC, Modalidade.PROEJA_FIC_FUNDAMENTAL])
        elif self.value() == '2':
            return queryset.exclude(aluno__curso_campus__modalidade__pk__in=[Modalidade.FIC, Modalidade.PROEJA_FIC_FUNDAMENTAL])


class DadosBancariosFilter(admin.SimpleListFilter):
    title = 'Informou dados bancários'
    parameter_name = 'dados_bancarios'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(
                aluno__in=InscricaoAluno.objects.filter(
                    banco__isnull=False, numero_agencia__isnull=False, numero_conta__isnull=False, tipo_conta__isnull=False
                ).values_list('aluno', flat=True)
            )
        elif self.value() == '2':
            return queryset.exclude(
                aluno__in=InscricaoAluno.objects.filter(
                    banco__isnull=False, numero_agencia__isnull=False, numero_conta__isnull=False, tipo_conta__isnull=False
                ).values_list('aluno', flat=True)
            )


class PrestacaoContasFilter(admin.SimpleListFilter):
    title = 'Adicionou prestação de contas'
    parameter_name = 'prestacao_contas'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(parecer=DEFERIDO, prestacao_contas_cadastrada_em__isnull=False)
        elif self.value() == '2':
            return queryset.filter(parecer=DEFERIDO, prestacao_contas_cadastrada_em__isnull=True)


class ParticipanteFilter(admin.SimpleListFilter):
    title = 'É participante'
    parameter_name = 'eh_participante'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)
        elif self.value() == '2':
            return queryset.exclude(fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)


class MatriculaAtivaFilter(admin.SimpleListFilter):
    title = 'Matrícula Ativa'
    parameter_name = 'matricula_ativa'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Sim'),
            ('2', 'Não'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.annotate(
                situacao_matricula=Subquery(
                    MatriculaPeriodo.objects.filter(aluno=OuterRef('aluno')).order_by('-ano_letivo__ano', '-periodo_letivo').values('situacao')[:1]
                )
            ).filter(situacao_matricula=SituacaoMatriculaPeriodo.MATRICULADO)
        elif self.value() == '2':
            return queryset.annotate(
                situacao_matricula=Subquery(
                    MatriculaPeriodo.objects.filter(aluno=OuterRef('aluno')).order_by('-ano_letivo__ano', '-periodo_letivo').values('situacao')[:1]
                )
            ).exclude(situacao_matricula=SituacaoMatriculaPeriodo.MATRICULADO)


class AnoLetivoFilter(admin.SimpleListFilter):
    title = 'Ano Letivo'
    parameter_name = 'anoletivo'

    def lookups(self, request, model_admin):
        anos = []
        for data in Ano.objects.filter(ano__gte=2020):
            anos.append((data.ano, data.ano))
        anos.reverse()
        return anos

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(data_cadastro__year=self.value())


class InscricaoInternetAdmin(ModelAdminPlus):
    list_display = (
        'get_aluno',
        'data_cadastro',
        'valor_solicitacao',
        'justificativa_solicitacao',
        'get_renda_bruta',
        'get_renda_per_capita',
        'get_situacao',
        'ultima_atualizacao',
        'get_parecer',
        'data_parecer',
        'documentacao_pendente',
        'documentacao_atualizada_em',
        'tem_dados_bancarios',
        'termo_compromisso_assinado',
        'termo_compromisso_assinado_em',
        'fim_auxilio',
        'data_limite_assinatura_termo',
        'get_opcoes',
    )
    search_fields = (
        'aluno__pessoa_fisica__nome',
        'aluno__matricula',
    )
    list_filter = (
        'edital',
        'edital__campus',
        'situacao',
        'parecer',
        'termo_compromisso_assinado',
        FICFilter,
        DocumentacaoCadastradaFilter,
        EnvioFilter,
        DocumentoPosParecerFilter,
        DadosBancariosFilter,
        DocumentacaoSolicitadaFilter,
        ParticipanteFilter,
        MatriculaAtivaFilter,
        AnoLetivoFilter,
    )
    list_display_icons = False
    list_display_links = None
    export_to_xls = True
    actions = [
        'prorrogar_assinatura_termo',
    ]
    actions_on_top = True
    actions_on_bottom = True

    def prorrogar_assinatura_termo(self, request, queryset):
        for objeto in queryset:
            if not objeto.termo_compromisso_assinado:
                objeto.data_limite_assinatura_termo = datetime.datetime.now() + relativedelta(days=+3)
                objeto.save()
        self.message_user(request, 'Prazo para assinatura do termo de compromisso prorrogado com sucesso.', level=messages.SUCCESS)

    prorrogar_assinatura_termo.short_description = 'Prorrogar assinatura do Termo de Compromisso'

    def get_inscricoes_anteriores(self, obj):
        return get_inscricoes_anteriores(obj)

    get_inscricoes_anteriores.short_description = 'Inscrições Anteriores'

    def get_aluno(self, obj):
        return mark_safe(f'{obj.aluno.pessoa_fisica.nome} <a href="{obj.aluno.get_absolute_url()}?tab=caracterizacao">({obj.aluno.matricula})</a>')

    get_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'
    get_aluno.short_description = 'Aluno'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Edital',
            'Campus',
            'Aluno',
            'Renda Bruta Mensal Média - R$',
            'Renda Per Capita - R$',
            'Data da Inscrição',
            'Telefones de Contato',
            'Emails de Contato',
            'Situação quanto à Internet',
            'Valor da Solicitação',
            'Justificativa',
            'Situação',
            'Documentação Pendente',
            'Documentação Atualizada em',
            'Parecer',
            'Data do Parecer',
            'Valor Concedido - R$',
            'Dados Bancários',
        ]
        rows = [header]

        for idx, obj in enumerate(processo.iterate(queryset)):
            inscricaoaluno = InscricaoAluno.objects.get(aluno=obj.aluno)
            row = [
                idx + 1,
                obj.edital.descricao,
                obj.edital.campus,
                obj.aluno,
                inscricaoaluno.renda_bruta_familiar,
                inscricaoaluno.renda_per_capita,
                format_(obj.data_cadastro),
                inscricaoaluno.telefones_contato,
                inscricaoaluno.emails_contato,
                obj.situacao_acesso_internet,
                obj.valor_solicitacao,
                obj.justificativa_solicitacao,
                obj.situacao,
                obj.documentacao_pendente,
                obj.documentacao_atualizada_em,
                obj.parecer,
                obj.data_parecer,
                obj.valor_concedido,
                inscricaoaluno.get_dados_bancarios(),
            ]
            rows.append(row)
        return rows

    def get_situacao(self, obj):
        return mark_safe(obj.get_situacao())

    get_situacao.short_description = 'Situação'

    def get_parecer(self, obj):
        return mark_safe(obj.get_parecer())

    get_parecer.short_description = 'Parecer'

    def get_opcoes(self, obj):
        return get_opcoes(obj, self.request)

    get_opcoes.short_description = 'Opções'

    def get_renda_bruta(self, obj):
        return InscricaoAluno.objects.get(aluno=obj.aluno).renda_bruta_familiar

    get_renda_bruta.short_description = 'Renda Bruta Mensal Média (R$)'

    def get_renda_per_capita(self, obj):
        return InscricaoAluno.objects.get(aluno=obj.aluno).renda_per_capita

    get_renda_per_capita.short_description = 'Renda per Capita (R$)'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
            qs = qs.filter(edital__campus=get_uo(request.user))
        return qs

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        items.append({'url': '/auxilioemergencial/folha_pagamento/INT/', 'label': 'Folha de Pagamento'})
        return items

    def tem_dados_bancarios(self, obj):
        if obj.tem_dados_bancarios():
            return mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        return mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')

    tem_dados_bancarios.short_description = 'Tem Dados Bancários'


admin.site.register(InscricaoInternet, InscricaoInternetAdmin)


class InscricaoDispositivoAdmin(ModelAdminPlus):
    search_fields = (
        'aluno__pessoa_fisica__nome',
        'aluno__matricula',
    )
    list_display_icons = False
    list_display_links = None
    export_to_xls = True

    def changelist_view(self, request, extra_context=None):
        list_filter = (
            'edital',
            'edital__campus',
            'situacao',
            'parecer',
            'termo_compromisso_assinado',
            FICFilter,
            DocumentacaoCadastradaFilter,
            EnvioFilter,
            DocumentoPosParecerFilter,
            DadosBancariosFilter,
            DocumentacaoSolicitadaFilter,
            PrestacaoContasFilter,
            ParticipanteFilter,
            MatriculaAtivaFilter,
            AnoLetivoFilter,
        )
        list_display = (
            'get_aluno',
            'data_cadastro',
            'valor_solicitacao',
            'justificativa_solicitacao',
            'get_renda_bruta',
            'get_renda_per_capita',
            'get_situacao',
            'ultima_atualizacao',
            'get_parecer',
            'data_parecer',
            'documentacao_pendente',
            'documentacao_atualizada_em',
            'tem_dados_bancarios',
            'termo_compromisso_assinado',
            'termo_compromisso_assinado_em',
            'fim_auxilio',
            'data_limite_assinatura_termo',
            'get_opcoes',
        )
        if not request.user.has_perm('auxilioemergencial.add_edital') and not request.user.has_perm('comum.is_auditor'):
            list_display = (
                'get_aluno',
                'data_cadastro',
                'parecer',
                'get_opcoes',
            )
            list_filter = (
                'edital',
                PrestacaoContasFilter,
            )
        self.list_filter = list_filter
        self.list_display = list_display

        return super().changelist_view(request, extra_context=extra_context)

    actions = [
        'prorrogar_assinatura_termo',
    ]
    actions_on_top = True
    actions_on_bottom = True

    def prorrogar_assinatura_termo(self, request, queryset):
        if request.user.has_perm('ae.pode_ver_relatorios_todos') or request.user.has_perm('auxilioemergencial.add_edital'):
            for objeto in queryset:
                if not objeto.termo_compromisso_assinado:
                    objeto.data_limite_assinatura_termo = datetime.datetime.now() + relativedelta(days=+3)
                    objeto.save()
        self.message_user(request, 'Prazo para assinatura do termo de compromisso prorrogado com sucesso.', level=messages.SUCCESS)

    prorrogar_assinatura_termo.short_description = 'Prorrogar assinatura do Termo de Compromisso'

    def get_inscricoes_anteriores(self, obj):
        return get_inscricoes_anteriores(obj)

    get_inscricoes_anteriores.short_description = 'Inscrições Anteriores'

    def get_aluno(self, obj):
        return mark_safe(f'{obj.aluno.pessoa_fisica.nome} <a href="{obj.aluno.get_absolute_url()}?tab=caracterizacao">({obj.aluno.matricula})</a>')

    get_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'
    get_aluno.short_description = 'Aluno'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Edital',
            'Campus',
            'Aluno',
            'Renda Bruta Mensal Média - R$',
            'Renda Per Capita - R$',
            'Data da Inscrição',
            'Telefones de Contato',
            'Emails de Contato',
            'Situação quanto ao Equipamento',
            'Valor da Solicitação',
            'Justificativa',
            'Situação',
            'Documentação Pendente',
            'Documentação Atualizada em',
            'Parecer',
            'Data do Parecer',
            'Valor Concedido - R$',
            'Dados Bancários',
        ]
        rows = [header]

        for idx, obj in enumerate(processo.iterate(queryset)):
            inscricaoaluno = InscricaoAluno.objects.get(aluno=obj.aluno)
            row = [
                idx + 1,
                obj.edital.descricao,
                obj.edital.campus,
                obj.aluno,
                inscricaoaluno.renda_bruta_familiar,
                inscricaoaluno.renda_per_capita,
                format_(obj.data_cadastro),
                inscricaoaluno.telefones_contato,
                inscricaoaluno.emails_contato,
                obj.situacao_equipamento,
                obj.valor_solicitacao,
                obj.justificativa_solicitacao,
                obj.situacao,
                obj.documentacao_pendente,
                obj.documentacao_atualizada_em,
                obj.parecer,
                obj.data_parecer,
                obj.valor_concedido,
                inscricaoaluno.get_dados_bancarios(),
            ]
            rows.append(row)
        return rows

    def get_situacao(self, obj):
        return mark_safe(obj.get_situacao())

    get_situacao.short_description = 'Situação'

    def get_parecer(self, obj):
        return mark_safe(obj.get_parecer())

    get_parecer.short_description = 'Parecer'

    def get_opcoes(self, obj):
        return get_opcoes(obj, self.request)

    get_opcoes.short_description = 'Opções'

    def get_renda_bruta(self, obj):
        return InscricaoAluno.objects.get(aluno=obj.aluno).renda_bruta_familiar

    get_renda_bruta.short_description = 'Renda Bruta Mensal Média (R$)'

    def get_renda_per_capita(self, obj):
        return InscricaoAluno.objects.get(aluno=obj.aluno).renda_per_capita

    get_renda_per_capita.short_description = 'Renda per Capita (R$)'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorios_todos') and not request.user.has_perm('comum.is_auditor'):
            qs = qs.filter(edital__campus=get_uo(request.user))
            if not request.user.has_perm('auxilioemergencial.add_edital'):
                qs = qs.filter(parecer='Deferido', termo_compromisso_assinado=True)
        return qs

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        items.append({'url': '/auxilioemergencial/folha_pagamento/DIS/', 'label': 'Folha de Pagamento'})
        return items

    def tem_dados_bancarios(self, obj):
        if obj.tem_dados_bancarios():
            return mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        return mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')

    tem_dados_bancarios.short_description = 'Tem Dados Bancários'


admin.site.register(InscricaoDispositivo, InscricaoDispositivoAdmin)


class InscricaoMaterialPedagogicoAdmin(ModelAdminPlus):
    list_display = (
        'get_aluno',
        'data_cadastro',
        'descricao_material',
        'especificacao_material',
        'valor_solicitacao',
        'justificativa_solicitacao',
        'get_situacao',
        'ultima_atualizacao',
        'get_parecer',
        'data_parecer',
        'documentacao_pendente',
        'documentacao_atualizada_em',
        'tem_dados_bancarios',
        'termo_compromisso_assinado',
        'termo_compromisso_assinado_em',
        'fim_auxilio',
        'data_limite_assinatura_termo',
        'get_opcoes',
    )
    search_fields = (
        'aluno__pessoa_fisica__nome',
        'aluno__matricula',
    )
    list_filter = (
        'edital',
        'edital__campus',
        'situacao',
        'parecer',
        'termo_compromisso_assinado',
        FICFilter,
        DocumentacaoCadastradaFilter,
        EnvioFilter,
        DocumentoPosParecerFilter,
        DadosBancariosFilter,
        DocumentacaoSolicitadaFilter,
        ParticipanteFilter,
        MatriculaAtivaFilter,
        AnoLetivoFilter,
    )
    list_display_icons = False
    list_display_links = None
    export_to_xls = True

    actions = [
        'prorrogar_assinatura_termo',
    ]
    actions_on_top = True
    actions_on_bottom = True

    def prorrogar_assinatura_termo(self, request, queryset):
        for objeto in queryset:
            if not objeto.termo_compromisso_assinado:
                objeto.data_limite_assinatura_termo = datetime.datetime.now() + relativedelta(days=+3)
                objeto.save()
        self.message_user(request, 'Prazo para assinatura do termo de compromisso prorrogado com sucesso.', level=messages.SUCCESS)

    prorrogar_assinatura_termo.short_description = 'Prorrogar assinatura do Termo de Compromisso'

    def get_inscricoes_anteriores(self, obj):
        return get_inscricoes_anteriores(obj)

    get_inscricoes_anteriores.short_description = 'Inscrições Anteriores'

    def get_aluno(self, obj):
        return mark_safe(f'{obj.aluno.pessoa_fisica.nome} <a href="{obj.aluno.get_absolute_url()}?tab=caracterizacao">({obj.aluno.matricula})</a>')

    get_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'
    get_aluno.short_description = 'Aluno'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Edital',
            'Campus',
            'Aluno',
            'Renda Bruta Mensal Média - R$',
            'Renda Per Capita - R$',
            'Data da Inscrição',
            'Telefones de Contato',
            'Emails de Contato',
            'Descrição do Material',
            'Especificação do Material',
            'Valor da Solicitação',
            'Justificativa',
            'Situação',
            'Documentação Pendente',
            'Documentação Atualizada em',
            'Parecer',
            'Data do Parecer',
            'Valor Concedido - R$',
            'Dados Bancários',
        ]
        rows = [header]

        for idx, obj in enumerate(processo.iterate(queryset)):
            inscricaoaluno = InscricaoAluno.objects.get(aluno=obj.aluno)
            row = [
                idx + 1,
                obj.edital.descricao,
                obj.edital.campus,
                obj.aluno,
                inscricaoaluno.renda_bruta_familiar,
                inscricaoaluno.renda_per_capita,
                format_(obj.data_cadastro),
                inscricaoaluno.telefones_contato,
                inscricaoaluno.emails_contato,
                obj.descricao_material,
                obj.especificacao_material,
                obj.valor_solicitacao,
                obj.justificativa_solicitacao,
                obj.situacao,
                obj.documentacao_pendente,
                obj.documentacao_atualizada_em,
                obj.parecer,
                obj.data_parecer,
                obj.valor_concedido,
                inscricaoaluno.get_dados_bancarios(),
            ]
            rows.append(row)
        return rows

    def get_situacao(self, obj):
        return mark_safe(obj.get_situacao())

    get_situacao.short_description = 'Situação'

    def get_parecer(self, obj):
        return mark_safe(obj.get_parecer())

    get_parecer.short_description = 'Parecer'

    def get_opcoes(self, obj):
        return get_opcoes(obj, self.request)

    get_opcoes.short_description = 'Opções'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
            qs = qs.filter(edital__campus=get_uo(request.user))
        return qs

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        items.append({'url': '/auxilioemergencial/folha_pagamento/MAT/', 'label': 'Folha de Pagamento'})
        return items

    def tem_dados_bancarios(self, obj):
        if obj.tem_dados_bancarios():
            return mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        return mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')

    tem_dados_bancarios.short_description = 'Tem Dados Bancários'


admin.site.register(InscricaoMaterialPedagogico, InscricaoMaterialPedagogicoAdmin)


class InscricaoAlunoConectadoAdmin(ModelAdminPlus):
    list_display = (
        'get_aluno',
        'data_cadastro',
        'casa_possui_servico_internet',
        'foi_contemplado_servico_internet',
        'localidade_possui_cobertura',
        'justificativa_solicitacao',
        'get_situacao',
        'ultima_atualizacao',
        'get_parecer',
        'data_parecer',
        'documentacao_pendente',
        'documentacao_atualizada_em',
        'termo_compromisso_assinado',
        'termo_compromisso_assinado_em',
        'fim_auxilio',
        'get_renda_bruta',
        'get_renda_per_capita',
        'data_limite_assinatura_termo',
        'get_opcoes',
    )
    search_fields = (
        'aluno__pessoa_fisica__nome',
        'aluno__matricula',
    )
    list_filter = (
        'edital',
        'edital__campus',
        'situacao',
        'parecer',
        'termo_compromisso_assinado',
        FICFilter,
        DocumentacaoCadastradaFilter,
        EnvioFilter,
        DocumentoPosParecerFilter,
        DocumentacaoSolicitadaFilter,
        ParticipanteFilter,
        MatriculaAtivaFilter,
        AnoLetivoFilter,
    )
    list_display_icons = False
    list_display_links = None
    export_to_xls = True
    actions = [
        'prorrogar_assinatura_termo',
    ]
    actions_on_top = True
    actions_on_bottom = True

    def prorrogar_assinatura_termo(self, request, queryset):
        for objeto in queryset:
            if not objeto.termo_compromisso_assinado:
                objeto.data_limite_assinatura_termo = datetime.datetime.now() + relativedelta(days=+3)
                objeto.save()
        self.message_user(request, 'Prazo para assinatura do termo de compromisso prorrogado com sucesso.', level=messages.SUCCESS)

    prorrogar_assinatura_termo.short_description = 'Prorrogar assinatura do Termo de Compromisso'

    def get_inscricoes_anteriores(self, obj):
        return get_inscricoes_anteriores(obj)

    get_inscricoes_anteriores.short_description = 'Inscrições Anteriores'

    def get_aluno(self, obj):
        return mark_safe(f'{obj.aluno.pessoa_fisica.nome} <a href="{obj.aluno.get_absolute_url()}?tab=caracterizacao">({obj.aluno.matricula})</a>')

    get_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'
    get_aluno.short_description = 'Aluno'

    def get_renda_bruta(self, obj):
        inscricaoaluno = InscricaoAluno.objects.get(aluno=obj.aluno)
        return inscricaoaluno.renda_bruta_familiar

    get_renda_bruta.short_description = 'Renda Bruta Mensal Média - R$'

    def get_renda_per_capita(self, obj):
        inscricaoaluno = InscricaoAluno.objects.get(aluno=obj.aluno)
        return inscricaoaluno.renda_per_capita

    get_renda_per_capita.short_description = 'Renda Per Capita - R$'

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Edital',
            'Campus',
            'Aluno',
            'Renda Bruta Mensal Média - R$',
            'Renda Per Capita - R$',
            'Data da Inscrição',
            'Telefones de Contato',
            'Emails de Contato',
            'Casa Possui Serviço Internet',
            'Foi Contemplado com Auxílio Internet',
            'Localidade Possui Cobertura WIFI',
            'Justificativa',
            'Situação',
            'Documentação Pendente',
            'Documentação Atualizada em',
            'Parecer',
            'Data do Parecer',
        ]
        rows = [header]

        for idx, obj in enumerate(processo.iterate(queryset)):
            inscricaoaluno = InscricaoAluno.objects.get(aluno=obj.aluno)
            row = [
                idx + 1,
                obj.edital.descricao,
                obj.edital.campus,
                obj.aluno,
                inscricaoaluno.renda_bruta_familiar,
                inscricaoaluno.renda_per_capita,
                format_(obj.data_cadastro),
                inscricaoaluno.telefones_contato,
                inscricaoaluno.emails_contato,
                obj.casa_possui_servico_internet,
                obj.foi_contemplado_servico_internet,
                obj.localidade_possui_cobertura,
                obj.justificativa_solicitacao,
                obj.situacao,
                obj.documentacao_pendente,
                obj.documentacao_atualizada_em,
                obj.parecer,
                obj.data_parecer,
            ]
            rows.append(row)
        return rows

    def get_situacao(self, obj):
        return mark_safe(obj.get_situacao())

    get_situacao.short_description = 'Situação'

    def get_parecer(self, obj):
        return mark_safe(obj.get_parecer())

    get_parecer.short_description = 'Parecer'

    def get_opcoes(self, obj):
        return get_opcoes(obj, self.request)

    get_opcoes.short_description = 'Opções'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
            qs = qs.filter(edital__campus=get_uo(request.user))
        return qs

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        items.append({'url': '/auxilioemergencial/folha_pagamento/CHP/', 'label': 'Folha de Pagamento'})
        return items

    def tem_dados_bancarios(self, obj):
        if obj.tem_dados_bancarios():
            return mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        return mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')

    tem_dados_bancarios.short_description = 'Tem Dados Bancários'


admin.site.register(InscricaoAlunoConectado, InscricaoAlunoConectadoAdmin)
