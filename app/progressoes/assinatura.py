"""
assinatura com chave única baseada em um método de hash e um método de codificação. A
assinatura resultante "guarda/lembra" a chave que foi utilizada.

-- Gerar --
conteudo, chave
    autenticador = hash(conteudo + chave)
    chave_codificada = encode(chave)
    assinatura = encode(autenticador + chave)

-- Verificar --
conteudo, assinatura
    autenticador = decode(assinatura)[0]
    chave_codificada = decode(assinatura)[1]
    chave = decode(chave_codificada)
    autenticador_recalculado = hash(conteudo + chave)
    se autenticador == autenticador_recalculado, assinatura é válida

-- Codificação --
Entradas = Texto (unicode, str)
Saídas = Texto (unicode)
"""

##################################################################################
#    hash: SHA1
#    codificação: BASE64
##################################################################################

import hashlib
import random

from djtools.forms.fields.password import PasswordField, TokenInput
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django import forms
from django.contrib.auth import authenticate

from comum.exceptions import LoginException, UserMustResetPassword
from djtools.utils import b64decode, b64encode

QUEBRA_LINHA_ESPACO = ' '  # com espaço em branco
QUEBRA_LINHA_ENTER_NL = '\n'  # com um caractere de nova linha
QUEBRA_LINHA_ENTER_CR = '\r'  # com um caractere de retorno de linha
QUEBRA_LINHA_HTML = '<br/>'  # com uma tag HTML de quebra de linha
QUEBRA_LINHA_OPCOES = [QUEBRA_LINHA_ESPACO, QUEBRA_LINHA_ENTER_NL, QUEBRA_LINHA_ENTER_CR, QUEBRA_LINHA_HTML]


def gera_assinatura(conteudo, chave):
    #
    # calcula o autenticador (tamanho fixo 40 caracteres hexadecimal)
    #
    autenticador = hashlib.sha1(f'{conteudo}{chave}'.encode()).hexdigest()  # 0..9 a..f A..F
    #
    # codifica a chave repetindo o processo "n" vezes/rodadas
    # o tamanho da chave codificada depende do tamanho da chave original e o número de rodadas/codificação aplicadas
    #
    chave_codificada_num_rodadas = random.randrange(2, 5)  # mínimo 2 rodadas (2..5)
    chave_codificada = f'{chave}'
    for _rodada in range(1, chave_codificada_num_rodadas + 1):
        chave_codificada = b64encode(f'{chave_codificada}')  # 0..9 a..z A..Z + / =
    #
    # assinatura = autenticador + numero de rodadas para codificar a chave + chave codificada após as rodadas
    # utiliza "," para separar as partes da assinatura ("," não pertence aos alfabetos usados até aqui)
    # o tamanho final da assinatura vai depender do tamanho da chave codificada
    #
    # partes da assinatura ------>  0  1  2
    assinatura = b64encode(f'{autenticador},{chave_codificada_num_rodadas},{chave_codificada}')
    #
    return assinatura


def verifica_assinatura(conteudo, assinatura):
    try:
        #
        # extrai o autenticador e a chave da assinatura
        #
        autenticador = obtem_autenticador(assinatura)
        chave_decodificada = obtem_chave_decodificada(assinatura)
        #
        # recalcula o autenticador com o conteúdo informado e compara o autenticador
        # com o que foi extraído da assinatura (se iguais, assinatura é válida)
        #
        autenticador_recalculado = hashlib.sha1(f'{conteudo}{chave_decodificada}'.encode()).hexdigest()
        #
        assinatura_eh_valida = autenticador_recalculado == autenticador
        #
        return assinatura_eh_valida
    except Exception:
        return False


def quebra_assinatura(assinatura, num_caracteres_por_linha=None, caractere_quebra_linha=QUEBRA_LINHA_ENTER_NL):
    #
    # "olha" para a assinatura "de fora" (unicode)
    #
    if not num_caracteres_por_linha:
        return assinatura
    else:
        posicao_inicial = 0
        linha = assinatura[posicao_inicial:num_caracteres_por_linha]
        assinatura_linhas = f'{linha}'
        #
        posicao_inicial += num_caracteres_por_linha
        linha = assinatura[posicao_inicial : num_caracteres_por_linha + posicao_inicial]
        while len(linha) > 0:
            assinatura_linhas = f'{assinatura_linhas}{caractere_quebra_linha}{linha}'
            posicao_inicial += num_caracteres_por_linha
            linha = assinatura[posicao_inicial : num_caracteres_por_linha + posicao_inicial]
        #
        return assinatura_linhas


def normaliza_assinatura(assinatura):
    #
    # "olha" para a assinatura "de fora" (unicode)
    #
    for caractere_quebra in QUEBRA_LINHA_OPCOES:
        assinatura = assinatura.replace(caractere_quebra, '')
    #
    return assinatura


def obtem_autenticador(assinatura):
    assinatura = normaliza_assinatura(assinatura)
    try:
        autenticador = b64decode(assinatura).split(',')[0]
    except Exception:
        autenticador = ''
    #
    return autenticador


def obtem_chave_codificada_num_rodadas(assinatura):
    assinatura = normaliza_assinatura(assinatura)
    try:
        codificada_num_rodadas = int(b64decode(assinatura).split(',')[1])
    except Exception:
        codificada_num_rodadas = 0
    #
    return codificada_num_rodadas


def obtem_chave_codificada(assinatura):
    assinatura = normaliza_assinatura(assinatura)
    try:
        chave_codificada = b64decode(assinatura).split(',')[2]
    except Exception:
        chave_codificada = ''
    #
    return chave_codificada


def obtem_chave_decodificada(assinatura):
    try:
        chave_codificada_num_rodadas = obtem_chave_codificada_num_rodadas(assinatura)
        chave_codificada = obtem_chave_codificada(assinatura)
        #
        # decodifica a chave repetindo o processo de acordo com o número de rodadas extraído da assinatura
        #
        chave = chave_codificada
        for _rodada in range(1, chave_codificada_num_rodadas + 1):
            chave = b64decode(chave)
        #
        chave_decodificada = chave
    except Exception:
        chave_decodificada = ''
    #
    return chave_decodificada


##################################################################################
# forms e widgets
##################################################################################


class AssinaturaTextInput(forms.TextInput):
    css_width = None

    def __init__(self, css_width=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.css_width = css_width

    def render(self, name, value, attrs=None, renderer=None):
        if self.css_width:
            attrs.update({'style': f'width: {self.css_width};'})
        #
        render_out = super().render(name, value, attrs)
        #
        return render_out


class AssinaturaForm(forms.Form):
    """
    Form Django com os seguintes fields:

        conteúdo assinado
        nome do assinante
        senha de confirmação com o objetivo de gerar a assinatura
        chave de assinatura/verificação (chave única)
        valor da assinatura

        conteudo...: xxxxxxxxxxxxxxxxxx
        assinante..: fulano de tal
        senha......: 123456
        chave......: lakjsd90182390asjdajklsd
        assinatura.: aksdçlopqiwekqweop29038laçsdjalpksdlçaksdlçaksdlçaskdlçaklsd
    """

    #
    # valores dos form-fields
    #
    conteudo = None
    nome_assinante = None
    senha_assinante = None
    chave = None
    assinatura = None
    codigo_verificacao = None  # usado para assinatura com gov.br

    #
    # exibição dos form-fields
    # o field 'senha' terá exibição decidida no método 'senha_assinante_field_exibir()'
    #
    conteudo_field_exibir = True
    nome_assinante_field_exibir = True
    chave_field_exibir = True
    assinatura_field_exibir = True  # o valor da assinatura será somente leitura

    #
    # nome dos form-fields
    #
    conteudo_field_name = 'conteudo'
    nome_assinante_field_name = 'nome_assinante'
    senha_assinante_field_name = 'senha_assinante'
    chave_field_name = 'chave'
    assinatura_field_name = 'assinatura'

    #
    # modificação de valor dos form-fields
    # o field 'assinatura' é sempre somente-leitura
    # o field 'senha', quando exibido, é sempre editável
    #
    conteudo_field_somente_leitura = False
    nome_assinante_field_somente_leitura = False
    chave_field_somente_leitura = False
    pode_assinar_com_gov_br = False

    #
    # help-text dos form-fields
    #
    conteudo_field_help_text = ''
    nome_assinante_field_help_text = ''
    senha_assinante_field_help_text = 'Senha para geração da assinatura'
    chave_field_help_text = ''
    assinatura_field_help_text = ''

    #
    # outros atributos do form
    #
    SUBMIT_LABEL = 'Assinar'
    ACTION = ''
    METHOD = 'POST'

    #
    # inicialização do formulário
    #
    def __init__(
        self,
        data=None,
        #
        conteudo=None,
        nome_assinante=None,
        senha_assinante=None,
        chave=None,
        assinatura=None,
        pode_assinar_com_gov_br=False,
        codigo_verificacao=None,
        #
        *args,
        **kwargs,
    ):
        if 'request' in kwargs:
            self.request = kwargs.pop('request')
        super().__init__(data, *args, **kwargs)
        #
        # inicializa os valores
        # ordem de precedência:
        #   1) valor passado no parâmetro correspondente em '__init__'
        #   2) valor definido no próprio atributo correspondente na definição da classe
        #   3) valor definido no método que inicializa o valor do atributo
        #
        self.inicializa_valores(
            conteudo=conteudo or self.conteudo or self.init_conteudo(),
            nome_assinante=nome_assinante or self.nome_assinante or self.init_nome_assinante(),
            senha_assinante=senha_assinante or self.senha_assinante or self.init_senha_assinante(),
            chave=chave or self.chave or self.init_chave(),
            assinatura=assinatura or self.assinatura or self.init_assinatura(),
            pode_assinar_com_gov_br=pode_assinar_com_gov_br or self.init_pode_assinar_com_gov_br(),
            codigo_verificacao=codigo_verificacao or self.codigo_verificacao or self.init_codigo_verificacao(),
        )

    def inicializa_valores(
        self,
        conteudo=None,
        nome_assinante=None,
        senha_assinante=None,
        chave=None,
        assinatura=None,
        pode_assinar_com_gov_br=False,
        codigo_verificacao=None,
    ):
        #
        # define os valores
        #
        self.conteudo = conteudo
        self.nome_assinante = nome_assinante
        self.senha_assinante = senha_assinante
        self.chave = chave
        self.assinatura = assinatura
        self.pode_assinar_com_gov_br = pode_assinar_com_gov_br
        self.codigo_verificacao = codigo_verificacao
        #
        # prepara os fields
        #
        self.prepara_fields()

    def prepara_fields(self):
        #
        self.fields.clear()
        #
        if self.conteudo_field_exibir:
            widget_attrs = {'value': self.conteudo}
            if self.conteudo_field_somente_leitura:
                widget_attrs.update({'readonly': 'readonly'})
            #
            self.fields[self.conteudo_field_name] = forms.CharField(
                label='Conteúdo',
                help_text=f'{self.conteudo_field_help_text}',
                required=True,
                initial=self.conteudo,
                widget=AssinaturaTextInput(attrs=widget_attrs),
            )
        #
        if self.nome_assinante_field_exibir:
            widget_attrs = {'value': self.nome_assinante}
            if self.nome_assinante_field_somente_leitura:
                widget_attrs.update({'readonly': 'readonly'})
            #
            self.fields[self.nome_assinante_field_name] = forms.CharField(
                label='Nome do Assinante',
                help_text=f'{self.nome_assinante_field_help_text}',
                required=False,
                initial=self.nome_assinante,
                widget=AssinaturaTextInput(attrs=widget_attrs),
            )
        #
        if self.chave_field_exibir:
            widget_attrs = {'value': self.chave}
            if self.chave_field_somente_leitura:
                widget_attrs.update({'readonly': 'readonly'})
            #
            self.fields[self.chave_field_name] = forms.CharField(
                label='Chave de Assinatura/Verificação',
                help_text=f'{self.chave_field_help_text}',
                required=True,
                initial=self.chave,
                widget=AssinaturaTextInput(attrs=widget_attrs),
            )
        #
        if self.assinatura_field_exibir:
            self.fields[self.assinatura_field_name] = forms.CharField(
                label='Assinatura',
                help_text=f'{self.assinatura_field_help_text}',
                required=False,
                initial=self.assinatura,
                widget=AssinaturaTextInput(attrs={'value': self.assinatura, 'readonly': 'readonly'}),
            )
        #
        if self.senha_assinante_field_exibir():
            self.fields[self.senha_assinante_field_name] = forms.CharField(
                label='Senha',
                help_text=f'{self.senha_assinante_field_help_text}',
                required=True,
                initial=self.senha_assinante,
                widget=forms.PasswordInput(attrs={'value': self.senha_assinante}),
            )
            if self.pode_assinar_com_gov_br:
                self.fields[self.senha_assinante_field_name].widget = TokenInput(attrs={'value': self.senha_assinante})

    #
    # decisão para exibição do field 'senha'
    #
    def senha_assinante_field_exibir(self):
        return self.assinatura_is_vazia()  # implementação padrão (se não há assinatura, solicita senha para gerá-la)

    #
    # definição dos valores iniciais dos form-fields, que devem retornar uma string
    #
    def init_conteudo(self):
        return ''  # implementação padrão

    def init_nome_assinante(self):
        return ''  # implementação padrão

    def init_senha_assinante(self):
        return ''  # implementação padrão

    def init_chave(self):
        return ''  # implementação padrão

    def init_assinatura(self):
        return ''  # implementação padrão

    def init_pode_assinar_com_gov_br(self):
        field_test = PasswordField()
        field_test.reload()
        return field_test.pode_assinar_com_gov_br

    def _get_cache_key_for_verification_code(self):
        if not hasattr(self, 'request') or not self.request.user.is_authenticated:
            return None
        try:
            vinculo = self.request.user.get_vinculo()
            return f'password_check_{vinculo.id}'
        except AttributeError, ObjectDoesNotExist:
            return None

    def init_codigo_verificacao(self):
        cache_key = self._get_cache_key_for_verification_code()
        if cache_key:
            return cache.get(cache_key)
        return None

    def destruir_codigo_verificacao(self):
        cache_key = self._get_cache_key_for_verification_code()
        if cache_key:
            cache.delete(cache_key)
        self.codigo_verificacao = None

    #
    # confirmação/verificação da senha do assinante para gerar a assinatura
    #
    def confirma_senha_assinante(self):
        return self.senha_assinante is not None  # implementação padrão

    def before_gera_assinatura(self):
        pass  # pode ser redefinido nas classes filhas para realizar alguma ação antes da geração da assinatura

    #
    # geração/verificação da assinatura
    #
    def gera_assinatura(self):
        self.before_gera_assinatura()
        self.assinatura = gera_assinatura(self.conteudo, self.chave)
        self.after_gera_assinatura()
        self.SUBMIT_LABEL = 'Ok'
        self.prepara_fields()  # atualiza os form-fields

    def after_gera_assinatura(self):
        pass  # pode ser redefinido nas classes filhas para realizar alguma ação após a geração da assinatura

    def verifica_assinatura(self):
        return verifica_assinatura(self.conteudo, self.assinatura)

    #
    # clean do formulário
    #
    def clean(self):
        cleaned_data = super().clean()
        #
        if not self.errors:
            #
            # atualiza atributos (se necessário)
            #
            if self.conteudo_field_exibir:
                self.conteudo = cleaned_data[self.conteudo_field_name]
            if self.nome_assinante_field_exibir:
                self.nome_assinante = cleaned_data[self.nome_assinante_field_name]
            if self.chave_field_exibir:
                self.chave = cleaned_data[self.chave_field_name]
            #
            # gera a assinatura (se necessário)
            #
            if self.senha_assinante_field_name in cleaned_data:
                self.senha_assinante = cleaned_data[self.senha_assinante_field_name]
                if self.confirma_senha_assinante():
                    self.gera_assinatura()
                else:
                    self.errors[self.senha_assinante_field_name] = ['Senha inválida. Tente novamente.']
                    del cleaned_data[self.senha_assinante_field_name]
            else:
                self.SUBMIT_LABEL = 'Ok'
        #
        return cleaned_data

    def assinatura_is_vazia(self):
        return self.assinatura is None or len(self.assinatura) == 0

    def assinatura_is_valida(self):
        return self.verifica_assinatura()

    def assinatura_situacao_as_html(self):
        if self.assinatura_is_valida():
            assinatura_situacao = 'Válida'
        else:
            if not self.assinatura_is_vazia():
                assinatura_situacao = 'Inválida'
            else:
                assinatura_situacao = 'Pendente'
        return f'<span>{assinatura_situacao}</span>'


#
# classe a ser extendida nas demandas de assinatura com chave única no suap
#
class SuapAssinaturaForm(AssinaturaForm):
    conteudo_field_exibir = False
    chave_field_exibir = False
    nome_assinante_field_somente_leitura = True
    senha_assinante_field_help_text = 'A mesma usada no acesso ao SUAP'
    login_assinante = None

    #
    # informe a request como parâmetro do __init__ para
    # que o login_assinante e nome_assinante sejam
    # resolvidos a partir do usuário logado
    #
    def __init__(self, data=None, login_assinante=None, *args, **kwargs):
        super().__init__(data, *args, **kwargs)
        self.login_assinante = login_assinante or self.login_assinante or self.init_login_assinante()

    def get_usuario_logado(self):
        try:
            usuario_logado = self.request.user
            return usuario_logado
        except Exception:
            return None

    def init_login_assinante(self):
        usuario_logado = self.get_usuario_logado()
        if usuario_logado:
            return usuario_logado.username
        else:
            return ''

    def init_nome_assinante(self):
        usuario_logado = self.get_usuario_logado()
        if usuario_logado:
            return str(usuario_logado.get_relacionamento())
        else:
            return ''

    def confirma_senha_assinante(self):
        """
        Confirma a assinatura do usuário.

        - Se NÃO pode assinar com gov.br:
            valida login/senha via authenticate.
        - Se PODE assinar com gov.br:
            valida o código de verificação salvo no cache.

        Retorna:
            True  -> se a confirmação foi bem-sucedida
            False -> se falhar autenticação "normal" (quando você quiser só indicar falha)
        Lança:
            forms.ValidationError -> nos casos de código inválido/expirado ou erro de fluxo.
        """

        # ============================
        # 1) Fluxo SEM gov.br -> senha
        # ============================
        if not self.pode_assinar_com_gov_br:
            login = self.login_assinante or self.request.user.username
            senha = self.senha_assinante

            if not login or not senha:
                return False

            try:
                usuario_autenticado = authenticate(
                    self.request,
                    username=login,
                    password=senha,
                )
            except (UserMustResetPassword, LoginException) as e:
                # validação específica para erros de login
                raise forms.ValidationError(str(e) or 'Erro ao tentar realizar a autenticação.')

            if not usuario_autenticado:
                # validação normal de falha de autenticação
                raise forms.ValidationError('A senha não confere com a do usuário logado.')

            return True

        # ==================================
        # 2) Fluxo COM gov.br -> código cache
        # ==================================
        codigo_informado = self.senha_assinante

        if not self.codigo_verificacao:
            raise forms.ValidationError('Código de Verificação Expirou. Você precisa gerar um novo Código de Verificação!')

        if not codigo_informado:
            raise forms.ValidationError('Por favor preencha o Código de Verificação!')

        if str(codigo_informado) != str(self.codigo_verificacao):
            raise forms.ValidationError('Código de Verificação não confere!')

        # se chegou aqui, o código está OK -> invalida para não ser reutilizado
        self.destruir_codigo_verificacao()

        return True

    def assinatura_situacao_as_html(self):
        assinatura_situacao_attrs = ''
        if self.assinatura_is_valida():
            assinatura_situacao = 'Válida'
            assinatura_situacao_attrs = "class='status status-success'"
        else:
            if not self.assinatura_is_vazia():
                assinatura_situacao = 'Inválida'
                assinatura_situacao_attrs = "class='status status-error'"
            else:
                assinatura_situacao = 'Pendente'
                assinatura_situacao_attrs = "class='status status-alert'"

        return f'<span {assinatura_situacao_attrs}>{assinatura_situacao}</span>'
