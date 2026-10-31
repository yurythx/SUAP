from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.safestring import mark_safe

from acumulocargo.forms import DeclaracaoAcumulacaoCargoForm, PeriodoDeclaracaoAcumuloCargosForm
from acumulocargo.models import (
    CargoPublicoAcumulavel,
    DeclaracaoAcumulacaoCargo,
    ExerceAtividadeRemuneradaPrivada,
    PeriodoDeclaracaoAcumuloCargos,
    TemAposentadoria,
    TemAtuacaoGerencial,
    TemPensao,
)
from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus, StackedInlinePlus
from djtools.templatetags.filters import in_group
from djtools.templatetags.tags import icon


def _funcao_validar(self, campo_check, msg):
    erro = False
    if self.data.get(campo_check):
        for form in self.forms:
            if erro:
                break
            if not hasattr(form, 'cleaned_data'):
                continue
            if not form.cleaned_data:
                erro = True
                break
            for campo in form.cleaned_data:
                if form.cleaned_data.get(campo) == '':
                    erro = True
                    break
        if erro:
            raise ValidationError(msg)


class CargoPublicoAcumulavelInLineFormSet(BaseInlineFormSet):
    """
    Valida formset
    """

    pode_cadastrar = True

    def clean(self):
        _funcao_validar(self, 'tem_outro_cargo_acumulavel', 'Você precisa preencher todos os campos do Anexo I.')


class CargoPublicoAcumulavelInLine(StackedInlinePlus):
    model = CargoPublicoAcumulavel
    max_num = 3
    formset = CargoPublicoAcumulavelInLineFormSet

    def get_extra(self, request, obj=None, **kwargs):
        extra = 1
        if obj and obj.cargopublicoacumulavel_set.exists():
            extra = 0
        return extra


class TemAposentadoriaInLineFormSet(BaseInlineFormSet):
    """
    Valida formset
    """

    pode_cadastrar = True

    def clean(self):
        _funcao_validar(self, 'tem_aposentadoria', 'Você precisa preencher todos os campos do Anexo II.')


class TemAposentadoriaInLine(StackedInlinePlus):
    model = TemAposentadoria
    max_num = 3
    formset = TemAposentadoriaInLineFormSet

    def get_extra(self, request, obj=None, **kwargs):
        extra = 1
        if obj and obj.temaposentadoria_set.exists():
            extra = 0
        return extra


class TemPensaoInLineFormSet(BaseInlineFormSet):
    """
    Valida formset
    """

    pode_cadastrar = True

    def clean(self):
        _funcao_validar(self, 'tem_pensao', 'Você precisa preencher todos os campos do Anexo III.')


class TemPensaoInLine(StackedInlinePlus):
    model = TemPensao
    max_num = 3
    formset = TemPensaoInLineFormSet

    def get_extra(self, request, obj=None, **kwargs):
        extra = 1
        if obj and obj.tempensao_set.exists():
            extra = 0
        return extra


class TemAtuacaoGerencialInLineFormSet(BaseInlineFormSet):
    """
    Valida formset
    """

    def clean(self):
        _funcao_validar(self, 'tem_atuacao_gerencial', 'Você precisa preencher todos os campos do Anexo IV.')
        for form in self.forms:
            if form.data.get('tem_atuacao_gerencial') and (
                form.cleaned_data.get('nao_exerco_atuacao_gerencial') or form.cleaned_data.get('nao_exerco_comercio')
            ):
                msg = 'Você não pode marcar as opções de que não exerce atuação gerencial e não exerce comércio na situação em que se encontra esta declaração.'
                raise ValidationError(msg)

            if (
                not form.data.get('tem_atuacao_gerencial')
                and not form.cleaned_data.get('nao_exerco_atuacao_gerencial')
                and not form.cleaned_data.get('nao_exerco_comercio')
            ):
                msg = 'Se você não tem atuação gerencial em atividade mercantil, marque estas opções na área do anexo 4'
                raise ValidationError(msg)


class TemAtuacaoGerencialInLine(StackedInlinePlus):
    model = TemAtuacaoGerencial
    max_num = 3
    formset = TemAtuacaoGerencialInLineFormSet

    def get_extra(self, request, obj=None, **kwargs):
        extra = 1
        if obj and obj.tematuacaogerencial_set.exists():
            extra = 0
        return extra


class ExerceAtividadeRemuneradaPrivadaInLineFormSet(BaseInlineFormSet):
    """
    Valida formset
    """

    def clean(self):
        _funcao_validar(self, 'exerco_atividade_remunerada_privada', 'Você precisa preencher todos os campos do Anexo V.')
        for form in self.forms:
            if form.data.get('exerco_atividade_remunerada_privada') and form.cleaned_data.get('nao_exerco_atividade_remunerada'):
                msg = 'Você não pode marcar a opção NÃO exerço atividade remunerada privada.'
                raise ValidationError(msg)

            if not form.data.get('exerco_atividade_remunerada_privada') and not form.cleaned_data.get('nao_exerco_atividade_remunerada'):
                msg = 'Por favor, se você não exerce atividade remunerada privada, marque esta opção no anexo 5.'
                raise ValidationError(msg)


class ExerceAtividadeRemuneradaPrivadaInLine(StackedInlinePlus):
    model = ExerceAtividadeRemuneradaPrivada
    max_num = 3
    formset = ExerceAtividadeRemuneradaPrivadaInLineFormSet

    def get_extra(self, request, obj=None, **kwargs):
        extra = 1
        if obj and obj.exerceatividaderemuneradaprivada_set.exists():
            extra = 0
        return extra


class DeclaracaoAcumulacaoCargoAdmin(ModelAdminPlus):
    list_display = ('servidor', 'periodo_declaracao_acumulo_cargo', 'data_cadastro')
    search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula')
    list_filter = ('servidor__setor__uo', 'periodo_declaracao_acumulo_cargo')
    list_display_icons = True

    inlines = [
        CargoPublicoAcumulavelInLine,
        TemAposentadoriaInLine,
        TemPensaoInLine,
        TemAtuacaoGerencialInLine,
        ExerceAtividadeRemuneradaPrivadaInLine,
    ]
    form = DeclaracaoAcumulacaoCargoForm
    fieldsets = (
        (
            'Declaro que:',
            {
                'fields': (
                    'servidor',
                    'periodo_declaracao_acumulo_cargo',
                    'nao_possui_outro_vinculo',
                    'tem_outro_cargo_acumulavel',
                    'tem_aposentadoria',
                    'tem_pensao',
                    'tem_atuacao_gerencial',
                    'exerco_atividade_remunerada_privada',
                )
            },
        ),
    )

    """
    Só pode cadastrar uma declaração de acumulação de cargos se o período estiver aberto e não tiver nenhum registro cadastrado para o período
    """

    def has_add_permission(self, request, obj=None):
        try:
            if request.user.eh_servidor:
                return request.user.is_superuser or PeriodoDeclaracaoAcumuloCargos.pode_cadastrar_declaracao(request.user.get_relacionamento())
        except Exception:
            pass
        return False

    """
    Se for superuser pode ver todas as declarações, senão, só visualiza a própria
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser or in_group(request.user, 'Coordenador de Gestão de Pessoas Sistêmico'):
            return qs

        if in_group(request.user, 'Coordenador de Gestão de Pessoas'):
            uo_usuario = get_uo(request.user)
            return qs.filter(servidor__setor__uo__id=uo_usuario.id)

        return qs.filter(servidor=request.user.get_relacionamento())

    def render_change_form(self, request, context, *args, **kwargs):
        servidor = request.user.get_relacionamento()
        cargo_funcao = '{} {}'.format(servidor.cargo_emprego, servidor.funcao or '')

        html_info = '<p class="alert alert-info">As informações prestadas neste formulário serão consideradas verídicas, sujeitando-se o servidor à apuração de responsabilidade administrativa (através de PAD), civil e penal, no caso de prestar informação falsa.</p>'
        html_table = f"""
                        <div class ="box">
                            <h3>Dados do servidor</h3>
                            <div>
                                <dl class="definition-list">
                                    <dt>Nome</dt><dd>{servidor.pessoa_fisica.nome}</dd>
                                    <dt>Cargo/Função</dt><dd>{cargo_funcao}</dd>
                                    <dt>Jornada de trabalho</dt><dd>{servidor.jornada_trabalho}</dd>
                                </dl>
                            </div>
                        </div>
                        """
        html = html_info + html_table

        extra = {'info_extra': html}
        context.update(extra)
        return super().render_change_form(request, context, *args, **kwargs)

    def show_list_display_icons(self, obj):
        out = []
        out.append(icon('view', obj.get_absolute_url()))
        if obj.pode_editar(self.request.user.get_relacionamento()):
            out.append(icon('edit', f'/admin/acumulocargo/declaracaoacumulacaocargo/{obj.id}/change/'))
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = 'Ações'


admin.site.register(DeclaracaoAcumulacaoCargo, DeclaracaoAcumulacaoCargoAdmin)


class PeriodoDeclaracaoAcumuloCargosAdmin(ModelAdminPlus):
    list_display = ('descricao', 'publico', 'ano', 'get_campus')
    ordering = ('id',)
    search_fields = ('descricao',)
    list_filter = ('ano', 'publico')
    list_display_icons = True
    form = PeriodoDeclaracaoAcumuloCargosForm

    def get_campus(self, obj):
        return mark_safe(obj.get_campus() or ' - ')

    get_campus.short_description = 'Campus'

    def get_acoes(self, obj):
        html = f"""
        <ul class="action-bar">
            <li class="has-child">
                <a href="#" class="btn"> Imprimir </a>
                <ul>
                    <li><a href="/acumulocargo/imprimir_declaracoes/{obj.id}/"> Declarações </a></li>
                    <li><a href="/acumulocargo/imprimir_declaracoes_campus/{obj.id}/"> Declarações por Campus </a></li>
                </ul>
            </li>
        </ul>
        """
        return mark_safe(html)

    get_acoes.short_description = 'Ações'


admin.site.register(PeriodoDeclaracaoAcumuloCargos, PeriodoDeclaracaoAcumuloCargosAdmin)
