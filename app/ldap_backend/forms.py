import ldap
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction

from comum.models import Configuracao
from djtools import forms
from djtools.utils import running_tests

from .models import LdapConf, LdapGroup, LdapUser


class SearchForm(forms.FormPlus):
    tipo = forms.ChoiceField(choices=[['busca_rapida', 'Busca Rápida'], ['busca_detalhada', 'Busca Detalhada']], label='')
    filtro = forms.CharField(required=False, label='', widget=forms.TextInput(attrs={'size': 100}))

    def __init__(self, *args, **kwargs):
        self.ldap_conf = kwargs.pop('ldap_conf')
        super().__init__(*args, **kwargs)

    def get_attrlist(self):
        return {'attrlist': [*self.ldap_conf.filterstr, 'givenName', 'sn', 'mail', 'title', 'userAccountControl', 'memberOf', 'userPrincipalName']}

    def get_filterstr(self):
        if self.cleaned_data['tipo'] == 'busca_rapida':
            return {'filterstr': f'(sAMAccountName={self.cleaned_data["filtro"]})'}
        elif self.cleaned_data['tipo'] == 'busca_detalhada':
            return {'filterstr': self.cleaned_data['filtro']}

    def search(self):
        try:
            search_fields = self.get_attrlist()
            search_fields.update(self.get_filterstr())
            return self.ldap_conf.search_objects(**search_fields)
        except ldap.LDAPError:
            raise forms.ValidationError(f'O filtro {self.cleaned_data["filtro"]} é inválido')
        except Exception:
            raise forms.ValidationError('Aconteceu um erro no processamento')

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        filtro = cleaned_data.get('filtro')
        if (tipo == 'busca_detalhada') and ('=' not in filtro):
            msg = f'O filtro {self.cleaned_data["filtro"]} é inválido para a busca detalhada.'
            self.add_error('filtro', msg)
        if (tipo == 'busca_rapida') and ('=' in filtro):
            self.add_error('filtro', f'O filtro {self.cleaned_data["filtro"]} é inválido para a busca rápida.')
        return cleaned_data


class ConfiguracaoForm(forms.FormPlus):
    dominio_institucional = forms.CharFieldPlus(label='Domínio do email Institucional', help_text='Ex: ifrn.edu.br', required=False)
    dominio_academico = forms.CharFieldPlus(label='Domínio do email Acadêmico', help_text='Ex: academico.ifrn.edu.br', required=False)
    dominio_google_classroom = forms.CharFieldPlus(label='Domínio do email Google Classroom', help_text='Ex: escolar.ifrn.edu.br', required=False)
    url_saml2idp = forms.CharFieldPlus(label='URL do SAML2IDP', help_text='Ex: http://saml2idp.ifrn.local', required=False)
    utilizar_saml2idp_outra_maquina = forms.BooleanField(label='Utilizar SAML2IDP em outra máquina?', required=False)
    utilizar_senha_randomica = forms.BooleanField(label='Utilizar senha randômica para novos usuários?', required=False)

    utilizar_autenticacao_via_ldap = forms.BooleanField(
        label='Utilizar Autenticação via LDAP/AD?', initial=True, required=False, help_text='Deixe marcado caso queira logar no usando o seu LDAP/AD.'
    )

    tentativas_maximas_bind = forms.IntegerFieldPlus(
        label='Tentativas máximas de bind', initial=3, help_text='Número máximo de tentativas de bind no LDAP/AD antes de falhar.', required=False
    )

    tentativas_maximas_busca = forms.IntegerFieldPlus(
        label='Tentativas máximas de busca', initial=3, help_text='Número máximo de tentativas de busca no LDAP/AD antes de falhar.', required=False
    )

    permite_ldap_group_estagiario = forms.BooleanField(
        label='Permite ingresso de estagiário no grupo LDAP definido?',
        initial=False,
        required=False,
        help_text='Marque esta opção caso deseje que, ao sincronizar usuários (sync_user), estagiários sejam ingressados em grupo LDAP definido no settings.py (variável grupo_estagiario).',
    )

    permite_ldap_group_prestador = forms.BooleanField(
        label='Permite ingresso de prestador de serviço no grupo LDAP definido?',
        initial=False,
        required=False,
        help_text='Marque esta opção caso deseje que, ao sincronizar usuários (sync_user), prestadores sejam ingressados em grupo LDAP definido no settings.py (variável grupo_prestador).',
    )

    resolucao = forms.CharFieldPlus(
        label='Resolução da política desativação conta',
        help_text='Resolução 26/2023 - CONSUP/IFRN, de 19 de abril de 2023',
        required=False,
        initial='Resolução 26/2023 - CONSUP/IFRN, de 19 de abril de 2023',
    )
    resolucao_url = forms.CharFieldPlus(
        label='URL da Resolução',
        help_text='url da resolução',
        required=False,
        initial='https://suap.ifrn.edu.br/documento_eletronico/conteudo_documento/5d029371-65a2-4d7a-99cb-6eb8405588a9/',
    )
    email_ti = forms.CharFieldPlus(label='E-mail do TI', help_text='E-mail para contato em caso de dúvidas.', required=False)
    sigla_ti = forms.CharFieldPlus(label='Sigla do setor de TI', help_text='Sigla do setor de TI da instituição.', required=False, initial='DIGTI')
    dias_para_inativar_conta = forms.IntegerFieldPlus(
        label='Quantidade de dias para inativar conta',
        initial=30,
        help_text='Da data do aviso a X dias a conta do AD será inativada.',
        required=False,
    )
    tempo_maximo_inativacao_email = forms.IntegerFieldPlus(
        label='Tempo máximo para inativação dos emails vínculados as contas',
        initial=90,
        help_text='Da data do aviso a X dias os emails serão excluídos de forma permanente.',
        required=False,
    )

    grupo_google_classroom = forms.CharFieldPlus(
        label='Grupo LDAP para usuários do Google Classroom',
        help_text='Usuários que fizerem parte deste grupo LDAP terão suas contas sincronizadas com o Google Classroom. Ex: CN=Professores que usam o Google Sala de Aula,OU=COINRE,OU=DIGTI,OU=RE,OU=IFRN,DC=ifrn,DC=local',
        required=False,
    )

    grupo_servidores = forms.CharFieldPlus(
        label='Grupo LDAP para usuários servidores',
        help_text='Servidores serão inseridos neste grupo LDAP. Ex: CN=G_SERVIDORES,OU=IFRN,DC=ifrn,DC=local',
        required=False,
    )

    grupo_prestadores = forms.CharFieldPlus(
        label='Grupo LDAP para usuários prestadores de serviço',
        help_text='Prestadores de serviço serão inseridos neste grupo LDAP.',
        required=False,
    )

    grupo_estagiarios = forms.CharFieldPlus(
        label='Grupo LDAP para usuários estagiários',
        help_text='Estagiários serão inseridos neste grupo LDAP.',
        required=False,
    )


class SelecaoEmailForm(forms.FormPlus):
    email = forms.ChoiceField(label='E-mail', choices=())

    def __init__(self, pessoa, tipo_dominio, *args, **kwargs):
        self.pessoa = pessoa
        self.tipo_dominio = tipo_dominio
        ldap_conf = LdapConf.get_active()
        if ldap_conf or running_tests():
            emails_disponiveis = self.pessoa.get_emails_disponiveis(tipo=self.tipo_dominio)
            if not emails_disponiveis:
                messages.error(kwargs['request'], 'Você precisa de pelo menos um nome e um sobrenome para escolher um email.')
        else:
            emails_disponiveis = []
        self.base_fields['email'].choices = list(zip(emails_disponiveis, emails_disponiveis, strict=False))
        super().__init__(*args, **kwargs)
        texto_politica_email = Configuracao.get_valor_por_chave('comum', 'texto_politica_email')
        if texto_politica_email:
            self.INFO = texto_politica_email

    def clean_email(self):
        ldap_conf = LdapConf.get_active()
        if ldap_conf or running_tests():
            emails_disponiveis = self.pessoa.get_emails_disponiveis(tipo=self.tipo_dominio)
        else:
            raise forms.ValidationError('Não foi possível conectar com o servidor de email, por favor, tente novamente.')
        # Pode ser que um outro usuário escolheu o mesmo email antes que esse usuário submeteu o form
        if self.cleaned_data['email'] not in emails_disponiveis:
            raise forms.ValidationError('O email {} não está disponível'.format(self.cleaned_data['email']))
        return self.cleaned_data['email']

    @transaction.atomic
    def processar(self, instance, username):
        instance.save()
        if not settings.DEBUG:
            ldap_conf = LdapConf.get_active()
            ldap_conf.sync_user(username)
        cache.delete(f'_cache_{username}_index_quick_access_data')  # Limpa a cache de quick access
        cache.delete(f'_cache_{username}_index_infos_data')  # Limpa a cache de infos


class LdapUserForm(forms.ModelFormPlus):
    class Meta:
        model = LdapUser
        fields = ('uid', 'sAMAccountName', 'givenName', 'sn', 'mail')


class LdapGroupForm(forms.ModelFormPlus):
    class Meta:
        model = LdapGroup
        fields = ('name', 'sAMAccountName', 'cn', 'dn')


class ExpirarSenhaLoteForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo TXT',
        filetypes=['csv', 'txt'],
        required=True,
        help_text='Arquivo TXT no formato: "username\tsenha\tformato_senha" um por linha. Exemplo: <a href="/static/comum/csv/expirar_senhas_lote.txt">expirar_senha_lote.txt</a>.',
    )
    simular = forms.BooleanField(label='Simular execução', initial=True, required=False)
    forcar_expiracao = forms.BooleanField(label='Forçar expiração', initial=False, required=False)

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        try:
            self.usuarios = [
                [column.strip() for column in line.decode().strip().split('\t')] for line in arquivo.readlines() if line.decode().strip()
            ][1:]
            for idx, usuario in enumerate(self.usuarios):
                if len(usuario) != 3:
                    raise ValidationError(
                        f'Linha {idx + 2} inválida. Cada linha deve conter username, senha e formato_senha separados por tabulação.'
                    )
            if not self.usuarios:
                raise ValidationError('O arquivo não contém dados válidos.')
        except Exception as e:
            raise ValidationError(f'Formato do arquivo inválido. Detalhe: {e}')
        return arquivo
