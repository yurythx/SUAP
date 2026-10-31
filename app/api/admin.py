from django.contrib import admin
from django.forms import PasswordInput
from django.utils.safestring import mark_safe
from oauth2_provider.generators import generate_client_secret

from api.forms import AccessTokenForm
from api.models import AplicacaoOAuth2
from comum.models import User
from djtools import forms
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.tags import icon
from djtools.utils import httprr


class AplicacaoOAuth2Admin(ModelAdminPlus):
    delete_confirmation_template = 'api/templates/delete_aplicacao.html'
    search_fields = ('name',)
    radio_fields = {
        'client_type': admin.HORIZONTAL,
        'authorization_grant_type': admin.VERTICAL,
    }

    def get_list_display(self, request):
        ld = ('show_list_display_icons', 'id', 'name', 'client_type', 'authorization_grant_type', 'active')
        if request.user.has_group_cached('Gerente Sistêmico de API'):
            ld = (*ld, 'user', 'skip_authorization')
        return ld

    def get_list_filter(self, request):
        lf = ('client_type', 'authorization_grant_type', 'skip_authorization')
        if request.user.has_group_cached('Gerente Sistêmico de API'):
            lf = (*lf, 'user')
        return lf

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, AplicacaoOAuth2.full, *args, **kwargs)
        if not request.user.has_group_cached('Gerente Sistêmico de API'):
            qs = qs.filter(user=request.user)
        return qs

    def get_fieldsets(self, request, obj=None):
        fieldsets = (('Dados gerais', {'fields': ('name', 'authorization_grant_type', 'redirect_uris', 'client_type', 'algorithm', 'active')}),)
        if not obj:
            fieldsets = (*fieldsets, ('Chaves', {'fields': ('client_id', 'client_secret')}))
        else:
            fieldsets = (*fieldsets, ('Chaves', {'fields': ('client_id',)}))
        if request.user.has_group_cached('Gerente Sistêmico de API'):
            fieldsets = (
                *fieldsets,
                ('Confiável', {'fields': ('granted_scopes', 'skip_authorization', 'keep_session', 'allowed_schemes')}),
                ('Usuário', {'fields': ('user',)}),
            )
        return fieldsets

    def show_list_display_icons(self, obj):
        out = []
        out.append(icon('edit', f'/admin/api/aplicacaooauth2/{obj.id}/change/'))
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = '#'

    def has_view_permission(self, request, obj=None):
        return request.user.has_group_cached('Gerente Sistêmico de API') or not obj or request.user == obj.user

    def has_add_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return request.user.has_group_cached('Gerente Sistêmico de API') or (obj and request.user == obj.user)

    def has_delete_permission(self, request, obj=None):
        return request.user.has_group_cached('Gerente Sistêmico de API') or (obj and request.user == obj.user)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['client_id'].widget.attrs['readonly'] = True
        form.base_fields['user'] = forms.ModelChoiceField(
            queryset=User.objects,
            widget=forms.AutocompleteWidget(search_fields=[*User.SEARCH_FIELDS, 'username', 'email', 'first_name', 'last_name']),
            label='Usuário de Destino',
        )
        if not request.user.has_group_cached('Gerente Sistêmico de API'):
            form.base_fields['user'].initial = request.user.pk
            form.base_fields['user'].disabled = True
        if not obj:
            form.base_fields['client_secret'] = forms.CharFieldPlus(
                label='Client Secret',
                help_text='Você só pode copiar este Client Secret agora',
                widget=PasswordInput(render_value=True, attrs={'readonly': True}),
                initial=generate_client_secret(),
                required=True,
                max_length=255,
            )
        else:
            form.base_fields['client_id'].disabled = True
            form.base_fields['client_id'].help_text = 'O Client Secret só está disponível durante a criação da aplicação.'
        return form

    def render_view_object(self, request, obj_pk):
        return httprr('/admin/api/aplicacaooauth2/', 'Você não pode ver isto.', 'error')

    def save_model(self, request, obj, form, change):
        if not request.user.has_group_cached('Gerente Sistêmico de API'):
            obj.user = request.user
            obj.save()
        else:
            super().save_model(request, obj, form, change)


class AccessTokenAdmin(ModelAdminPlus):
    list_display = ('token', 'user', 'application', 'expires')
    list_select_related = ('application', 'user')
    raw_id_fields = ('source_refresh_token',)
    search_fields = (
        'token',
        'user__email',
    )
    list_filter = ('application',)
    form = AccessTokenForm
