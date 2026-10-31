import re
from collections.abc import Iterable
from typing import Any, Protocol

from django.apps.registry import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.html import format_html, format_html_join

from djtools.db import models
from djtools.utils import (
    PREFIXOS_SINTETICOS,
    anonimizar_documento,
    get_age,
    get_ldap_conf,
    is_ldap_write_enabled,
    normalizar_token_email_conta,
    retirar_preposicoes_nome,
    to_ascii,
)
from rh.enums import Nacionalidade
from rh.managers import PessoaFisicaManager

from .pessoa import Pessoa

TIPOS_EMAIL_CONTA = ('institucional', 'academico', 'google_classroom')
CAMPOS_EMAIL_CONTA = {f'email_{tipo}' for tipo in TIPOS_EMAIL_CONTA}
METODOS_LDAP_EMAIL_CONTA = (
    'get_usernames_from_mail',
    'get_usernames_from_principalname',
    'get_usernames_from_email_academico',
    'get_usernames_from_email_google_classroom',
)


class LdapConfEmailConta(Protocol):
    def get_usernames_from_mail(self, email: str) -> list[str]: ...

    def get_usernames_from_principalname(self, email: str) -> list[str]: ...

    def get_usernames_from_email_academico(self, email: str) -> list[str]: ...

    def get_usernames_from_email_google_classroom(self, email: str) -> list[str]: ...


def _normalizar_tokens_email_conta(nome: str) -> list[str]:
    tokens = to_ascii(retirar_preposicoes_nome(nome).lower()).replace('.', '').split()
    return [token_normalizado for token in tokens if (token_normalizado := normalizar_token_email_conta(token))]


def _montar_emails_possiveis(
    tokens: list[str],
    dominio: str,
    abrevia_nome: bool = False,
    abrevia_sobrenome: bool = False,
    numero: int | None = None,
) -> list[str]:
    emails_possiveis = []
    for t1 in tokens:
        for t2 in tokens:
            if t1 != t2:
                nome = t1[0] if abrevia_nome else t1
                sobrenome = t2[0] if abrevia_sobrenome else t2
                sufixo = numero or ''
                emails_possiveis.append(f'{nome}.{sobrenome}{sufixo}@{dominio}')
    return emails_possiveis


def _obter_emails_ocupados(pessoa_fisica: PessoaFisica, emails_possiveis: list[str]) -> set[str]:
    """Emails já usados por outra pessoa em qualquer campo de email de conta, ou bloqueados."""
    from comum.models import EmailBlockList, PrestadorServico
    from edu.models import Aluno

    from ..carreira import Servidor

    emails_ocupados = set(EmailBlockList.objects.filter(email__in=emails_possiveis).values_list('email', flat=True))
    for model in (Servidor, Aluno, PrestadorServico):
        campos_do_model = {field.name for field in model._meta.fields}
        for campo in CAMPOS_EMAIL_CONTA & campos_do_model:
            emails_ocupados.update(
                model.objects.exclude(pessoa_fisica=pessoa_fisica).filter(**{f'{campo}__in': emails_possiveis}).values_list(campo, flat=True)
            )
    return emails_ocupados


def _obter_emails_existentes_no_ldap(emails_possiveis: Iterable[str], ldap_conf: LdapConfEmailConta | None) -> set[str]:
    if not ldap_conf:
        return set()
    return {email for email in emails_possiveis if any(getattr(ldap_conf, metodo)(email) for metodo in METODOS_LDAP_EMAIL_CONTA)}


class PessoasFisicasPodePegarChaveManager(models.Manager):
    """
    Manager que retorna apenas as pessoas aptas a pegar chave, seja porque já possuem
    digital seja porque não precisam da digital.
    """

    def get_queryset(self):
        qs = super().get_queryset().extra(where=['(tem_digital_fraca=True or template is not null)'])
        return qs


class PessoasFisicasPodeCadastrarAtendimentos(models.Manager):
    """
    Manager que retorna apenas as pessoas que podem cadastrar ou editar atendimentos de alunos.
    """

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .filter(
                Q(user__groups__permissions__codename='add_demandaalunoatendida')
                | Q(user__groups__permissions__codename='change_demandaalunoatendida')
            )
            .distinct()
        )
        return qs


class PessoaFisica(Pessoa):
    GENERO_MASCULINO = 'M'
    GENERO_FEMININO = 'F'
    GENERO_MULHER_TRANS = 'MT'
    GENERO_HOMEM_TRANS = 'HT'
    GENERO_TRAVESTI = 'TR'
    GENERO_NAO_BINARIO = 'NB'
    GENERO_INTERSEXUAL = 'IN'

    GENERO_CHOICES = {
        GENERO_MASCULINO: 'Masculino',
        GENERO_FEMININO: 'Feminino',
        GENERO_MULHER_TRANS: 'Mulher Trans',
        GENERO_HOMEM_TRANS: 'Homem Trans',
        GENERO_TRAVESTI: 'Travesti',
        GENERO_NAO_BINARIO: 'Não Binário',
        GENERO_INTERSEXUAL: 'Intersexual',
    }
    SEARCH_FIELDS = ['search_fields_optimized']
    RELEVANCE_ORDERING = [('eh_servidor', True), ('eh_prestador', True), ('eh_aluno', True)]

    cpf = models.CharField(max_length=20, null=True, unique=True, verbose_name='CPF', blank=False)
    passaporte = models.CharFieldPlus(max_length=50, verbose_name='Nº do Passaporte', null=True, blank=True)
    # CPF, senão passaporte/país, senão sintético (SEMDOC-/SEMPAIS-/CONFLITO-/INVALIDO-): ver rh/deduplicacao/documentos.py
    documento_identificador = models.CharFieldPlus(max_length=80, null=False, blank=False, unique=True)
    sexo = models.CharField(max_length=1, null=True, choices=[['M', 'Masculino'], ['F', 'Feminino']])
    genero = models.CharField(max_length=2, null=True, choices=GENERO_CHOICES.items(), verbose_name='Gênero')
    grupo_sanguineo = models.CharField(
        'Grupo sanguíneo', max_length=2, null=True, blank=True, choices=[[None, '-------'], ['A', 'A'], ['B', 'B'], ['AB', 'AB'], ['O', 'O']]
    )
    fator_rh = models.CharField('Fator RH', max_length=8, null=True, blank=True, choices=[[None, '-------'], ['+', '+'], ['-', '-']])
    titulo_numero = models.CharField(max_length=12, null=True, blank=True)
    titulo_zona = models.CharField(max_length=3, null=True, blank=True)
    titulo_secao = models.CharField(max_length=4, null=True, blank=True)
    titulo_uf = models.BrEstadoBrasileiroField(null=True, blank=True)
    titulo_data_emissao = models.DateField(null=True)
    rg = models.CharField(max_length=20, null=True, verbose_name='RG')
    rg_orgao = models.CharField(max_length=10, null=True)
    rg_data = models.DateField(null=True)
    rg_uf = models.BrEstadoBrasileiroField(null=True)
    nascimento_municipio = models.ForeignKeyPlus('comum.Municipio', null=True, blank=True, verbose_name='Município', on_delete=models.CASCADE)
    nascimento_data = models.DateFieldPlus('Data de Nascimento', null=True)
    nome_mae = models.CharField('Nome da Mãe', max_length=100, null=True)
    nome_pai = models.CharField('Nome do Pai', max_length=100, null=True, blank=True)
    cnh_carteira = models.CharField(max_length=10, null=True, blank=True)
    cnh_registro = models.CharField(max_length=10, null=True, blank=True)
    cnh_categoria = models.CharField(max_length=10, null=True, blank=True)
    cnh_emissao = models.DateField(null=True, blank=True)
    cnh_uf = models.CharField(max_length=2, null=True, blank=True)
    cnh_validade = models.DateField(null=True, blank=True)
    ctps_numero = models.CharField(max_length=20, null=True, blank=True)
    ctps_uf = models.CharField(max_length=2, null=True, blank=True)
    ctps_data_prim_emprego = models.DateField(null=True, blank=True)
    ctps_serie = models.CharField(max_length=10, null=True, blank=True)
    pis_pasep = models.CharField(max_length=20, null=True, blank=True, verbose_name='PIS / PASEP')
    pagto_banco = models.ForeignKeyPlus('rh.Banco', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Banco')
    pagto_agencia = models.CharField(max_length=20, null=True, blank=True, verbose_name='Agência')
    pagto_ccor = models.CharField(max_length=20, null=True, blank=True, verbose_name='Conta')
    pagto_ccor_tipo = models.CharField(max_length=2, blank=True, null=True, verbose_name='Tipo')
    tem_digital_fraca = models.BooleanField(
        default=False,
        blank=True,
        verbose_name='Permitir registro de ponto sem impressão digital',
        help_text='Pessoas com impressão digital fraca devem ter essa opção marcada',
    )
    senha_ponto = models.CharField(
        max_length=128,
        blank=True,
        verbose_name='Senha para registro de ponto sem impressão digital',
        help_text='Pessoas com impressão digital fraca devem ter uma senha definida para usar o terminal',
    )
    data_obito = models.DateField(null=True, blank=True)
    template = models.BinaryField(null=True, blank=True, editable=False)
    template_importado_terminal = models.BooleanField(default=False, verbose_name='Digital importada do terminal')
    # busca = SearchField(search=['nome', 'get_cpf_ou_cnpj'])
    estado_civil = models.ForeignKeyPlus('comum.EstadoCivil', null=True, on_delete=models.CASCADE)
    nacionalidade = models.IntegerField('Nacionalidade', choices=Nacionalidade.get_choices(), null=True)
    pais_origem = models.ForeignKeyPlus('comum.Pais', verbose_name='País de Origem', null=True, on_delete=models.CASCADE)  # para estrangeiro
    lattes = models.URLField(blank=True)
    orcid = models.URLField('ORCID', blank=True)
    eh_servidor = models.BooleanField(default=False)
    eh_aluno = models.BooleanField(default=False)
    eh_prestador = models.BooleanField(default=False)
    eh_usuarioexterno = models.BooleanField(default=False)
    eh_estrangeiro = models.BooleanField(verbose_name='É estrangeiro?', default=False)

    objects = PessoaFisicaManager()
    pode_pegar_chave = PessoasFisicasPodePegarChaveManager()
    pode_cadastrar_atendimentos = PessoasFisicasPodeCadastrarAtendimentos()

    EXT_COMBO_RELATED = {
        'select_related': [],
        'prefetch_related': ['vinculo_set__user', 'vinculo_set__tipo_relacionamento', 'vinculo_set__relacionamento'],
    }

    class History:
        ignore_fields = ('template', 'search_fields_optimized')

    class Meta:
        db_table = 'pessoa_fisica'
        verbose_name = 'Pessoa Física'
        verbose_name_plural = 'Pessoas Físicas'

        permissions = (
            ('pode_gerar_cracha', 'Pode gerar crachá'),
            ('pode_cadastrar_digital', 'Pode cadastrar digital'),
            ('pode_atualizar_digital', 'Pode atualizar digital'),
            ('pode_gerar_carteira', 'Pode gerar carteira'),
        )
        constraints = [
            # passaporte só identifica junto com o país emissor
            models.UniqueConstraint(fields=['pais_origem', 'passaporte'], name='pessoa_fisica_pais_passaporte_unico'),
            # sem CPF, o país é obrigatório; documento sintético (legado sem documento) fica isento
            models.CheckConstraint(
                condition=Q(cpf__isnull=False)
                | Q(pais_origem__isnull=False)
                | Q(documento_identificador__regex=r'^(SEMDOC|SEMPAIS|CONFLITO|INVALIDO)-'),
                name='pessoa_fisica_sem_cpf_exige_pais',
            ),
        ]

    def __str__(self):
        return self.nome

    def get_ext_combo_template_text(self):
        return str(self)

    def get_ext_combo_template(self) -> str:
        """Nome, documento anonimizado e cada vínculo (papel e matrícula); a foto é a do primeiro vínculo."""
        vinculos = sorted((v for v in self.vinculo_set.all() if v.relacionamento is not None), key=lambda v: v.pk)  # all(): EXT_COMBO_RELATED
        foto_url = vinculos[0].get_foto_75x100_url() if vinculos else self.get_foto_75x100_url()
        papeis = format_html_join(
            '',
            '<dd>{}</dd>',
            (
                (
                    f'{v.relacionamento._meta.verbose_name}: {self._matricula_no_combo(v.user.username)}'
                    if v.user
                    else v.relacionamento._meta.verbose_name,
                )
                for v in vinculos
            ),
        )
        return format_html(
            """<div class="person">
                <div class="photo-circle"><img src="{}" alt="Foto de {}" /></div>
                <dl>
                    <dt class="visually-hidden">Nome</dt><dd class="title">{} ({})</dd>
                    <dt class="visually-hidden">Vínculos</dt>{}
                </dl>
            </div>""",
            foto_url,
            self.nome,
            self.nome or 'Sem nome',
            anonimizar_documento(self.documento_identificador),
            papeis or format_html('<dd>{}</dd>', 'Sem vínculo'),
        )

    def _matricula_no_combo(self, username: str) -> str:
        """A matrícula do prestador é o CPF (ou o passaporte com país): no combo ela sai anonimizada como o documento.

        No sintético (``CONFLITO-<id>-<documento>``, ``INVALIDO-<id>-<dígitos>``) compara com o documento guardado nele.
        """
        documento = self.documento_identificador or ''
        guardado = documento.split('-', 2)[-1] if documento.startswith(PREFIXOS_SINTETICOS) else documento
        return anonimizar_documento(guardado) if username in {guardado, re.sub(r'\D', '', guardado)} else username

    def _get_search_fields_optimized_content_to_save(self, usernames: Iterable[str | None] | None = None) -> str:
        """``usernames`` dos vínculos já lidos (o ``aplicar`` lê os do lote numa consulta); sem eles, lê os desta pessoa.

        O passaporte entra com a sigla ISO 3166-1 alfa-3 do país (``ARG-AB123456``, o documento do estrangeiro): acha pelo
        número, pela sigla ou pelo documento.
        """
        from rh.deduplicacao.documentos import chave_passaporte

        if usernames is None:
            usernames = self.vinculo_set.values_list('user__username', flat=True) if self.pk else []
        # ordenados: o banco devolve os vínculos sem ordem fixa, e a busca mudaria a cada leitura (o aplicar regravaria)
        usernames = ''.join(sorted(item for item in usernames if item))
        iso = self.pais_origem.iso_alfa3 if self.pais_origem_id else None
        # os usernames por último: o ModelPlus.save() corta no tamanho da coluna, e o que sobra fora é só username
        return '{}{}{}{}{}'.format(
            self.nome or '',
            self.cpf or '',
            re.sub(r'\D', '', str(self.cpf)) or '',
            chave_passaporte(self.passaporte, iso) or self.passaporte or '',
            usernames,
        )

    def clean(self):
        if not self.nome_registro and not self.nome_social:
            raise ValidationError('É necessário preencher o Nome de Registro ou Nome Social')

    def reset_user_profiles(self):
        if 'edu' in settings.INSTALLED_APPS:
            for aluno in self.aluno_set.all():
                user = aluno.get_user()
                user and (user.reset_profile() or user.reset_vinculo())
        for servidor in self.servidor_set.all():
            user = servidor.get_user()
            user and (user.reset_profile() or user.reset_vinculo())
        for prestador in self.prestadorservico_set.all():
            user = prestador.get_user()
            user and (user.reset_profile() or user.reset_vinculo())

    def save(self, *args: Any, **kwargs: Any) -> None:
        from comum.models import PrestadorServico

        """
        Caso `self` tenha username, um usuário será criado para `self`.
        """
        tem_aluno = False

        if self.pk:
            if 'edu' in settings.INSTALLED_APPS:
                tem_aluno = self.aluno_set.all().exists()
            # O servidor ainda não existe no banco quando o próprio Servidor.save marca a flag.
            self.eh_servidor = self.servidor_set.exists() or self.eh_servidor
            self.eh_aluno = tem_aluno
            prestador = PrestadorServico.objects.filter(pessoa_fisica_id=self.pk).first()
            self.eh_prestador = prestador is not None
            self.eh_usuarioexterno = prestador is not None and not prestador.possui_ocupacao_ativa()

        self._derivar_nomes()
        self._normalizar_documentos()

        # Comentado à pedido de Augusto
        # if not settings.DEBUG and not cpfcnpj.validate(self.cpf):
        #     raise ValidationError(u"O CPF {} associado a {} não é valido.".format(self.cpf, self.nome))
        pf = super().save(*args, **kwargs)
        self.reset_user_profiles()
        return pf

    def _derivar_nomes(self) -> None:
        """``nome_registro``, ``nome`` e ``nome_usual`` a partir dos nomes informados (o save e a mescla do deduplicar_pessoas)."""
        if not self.nome_registro and self.nome:
            self.nome_registro = self.nome

        if self.nome_social:
            self.nome = self.nome_social
        else:
            self.nome = self.nome_registro

        if not self.nome_usual:
            if len(self.nome.split(' ')) > 1:
                self.nome_usual = ' '.join(self.nome.split()[:1] + self.nome.split()[-1:])[:30]
            else:
                # Ocorre quando nome só possui uma palavra
                self.nome_usual = self.nome[:30]

    def _normalizar_documentos(self) -> None:
        """Formata CPF/passaporte e recalcula ``documento_identificador`` (CPF, senão passaporte/ISO do país, senão sintético).

        Só formata: anular documento inválido é decisão auditada do comando ``deduplicar_pessoas``.
        """
        from rh.deduplicacao.documentos import (
            chave_passaporte,
            formatar_cpf,
            formatar_passaporte,
            recusar_documento_invalido,
            recusar_pais_sem_iso,
            sintetico_atual,
        )

        self.cpf = formatar_cpf(self.cpf)
        # A coluna no PostgreSQL desta instalação não aceita nulo.
        self.passaporte = formatar_passaporte(self.passaporte) or ''
        iso = self.pais_origem.iso_alfa3 if self.pais_origem_id else None
        if self.pk is None:
            # só a PF nova: a legada continua salvável, quem anula o documento inválido dela é a higiene (auditada)
            recusar_documento_invalido(self.cpf, self.passaporte)
            recusar_pais_sem_iso(self.cpf, self.passaporte, bool(self.pais_origem_id), iso)
        chave = self.cpf or chave_passaporte(self.passaporte, iso)
        if chave:
            self.documento_identificador = chave
        elif self.pk is None:
            raise ValidationError('Informe o CPF, ou o passaporte e o país de origem da pessoa.')
        else:
            # a PF existente sem documento (ex.: alguém apagou o CPF) ganha o sintético, como na normalização do deduplicar_pessoas;
            # documento_identificador é NOT NULL e único, e o sintético é isento da CHECK "sem CPF exige país"
            self.documento_identificador = sintetico_atual(self.pk, self.documento_identificador, self.passaporte, bool(self.pais_origem_id))

    def get_emails_disponiveis(self, tipo: str = 'institucional') -> list[str]:
        """
        Gera os emails de conta ainda disponíveis para a pessoa, no domínio do `tipo` informado.

        A regra é a mesma para os três tipos: o email não pode estar em uso por outra pessoa em
        nenhum campo de email de conta (institucional, acadêmico ou Google Classroom) de Servidor,
        Aluno ou PrestadorServico, nem na EmailBlockList, nem no LDAP. A ocupação vale por endereço
        completo: o mesmo prefixo pode existir em domínios diferentes, de pessoas diferentes.
        """
        from comum.models import Configuracao

        assert tipo in TIPOS_EMAIL_CONTA

        dominio = Configuracao.get_valor_por_chave('ldap_backend', f'dominio_{tipo}')
        if not dominio:
            return []

        ldap_conf = get_ldap_conf()
        ldap_enabled = is_ldap_write_enabled()

        def define_emails(tokens: list[str], abrevia_nome: bool = False, abrevia_sobrenome: bool = False, numero: int | None = None) -> set[str]:
            if not ldap_enabled:
                return set()
            emails_possiveis = _montar_emails_possiveis(tokens, dominio, abrevia_nome, abrevia_sobrenome, numero)
            candidatos = set(emails_possiveis) - _obter_emails_ocupados(self, emails_possiveis)
            return candidatos - _obter_emails_existentes_no_ldap(candidatos, ldap_conf)

        tokens = _normalizar_tokens_email_conta(self.nome)

        if len(tokens) < 2:
            return []
        emails = dict.fromkeys(define_emails(tokens))
        emails.update(dict.fromkeys(define_emails(tokens, abrevia_nome=True)))
        emails.update(dict.fromkeys(define_emails(tokens, abrevia_sobrenome=True)))
        numero = 1
        while len(emails) < 5 and ldap_enabled:
            emails.update(dict.fromkeys(define_emails(tokens, numero=numero)))
            numero += 1
        return list(emails)

    def get_foto_url_publica(self, tamanho=None):
        # foto de servidor/prestador migrou p/ Vinculo; acesso role-less cai no default
        path_img = '/static/comum/img/default.jpg'
        if self.eh_aluno:
            aluno = self.aluno_set.order_by('-pk').first()
            if aluno and aluno.foto:
                path_img = aluno.foto.get_url_publica(tamanho)
        return f'{settings.SITE_URL}{path_img}'

    def get_foto_75x100_url_publica(self):
        return self.get_foto_url_publica('75x100')

    def get_foto_150x200_url_publica(self):
        return self.get_foto_url_publica('150x200')

    def get_foto_75x100_url(self):
        # foto de servidor/prestador migrou p/ Vinculo; acesso role-less cai no default
        default_img = '/static/comum/img/default.jpg'
        if self.eh_aluno:
            aluno = self.aluno_set.order_by('-pk').first()
            if aluno and aluno.foto:
                return aluno.foto.url_75x100
        return default_img

    def get_foto_150x200_url(self):
        # foto de servidor/prestador migrou p/ Vinculo; acesso role-less cai no default
        default_img = '/static/comum/img/default.jpg'
        if self.eh_aluno:
            aluno = self.aluno_set.order_by('-pk').first()
            if aluno and aluno.foto:
                return aluno.foto.url_150x200
        return default_img

    def get_foto_url(self):
        # foto de servidor/prestador migrou p/ Vinculo; acesso role-less cai no default
        if self.eh_aluno:
            aluno = self.aluno_set.order_by('-pk').first()
            if aluno and aluno.foto:
                return aluno.foto.url
        return '/static/comum/img/default.jpg'

    def get_template(self, encoding='utf-8'):
        if self.template is None:
            return ''.encode(encoding)
        if isinstance(self.template, memoryview):
            template = self.template.tobytes()
        else:
            template = self.template
        if encoding == 'utf-8':
            return template
        else:
            return template.decode('utf-8').encode(encoding)

    def get_absolute_url(self):
        return '#'

    def get_vinculo(self):
        candidato = None
        if self.eh_servidor:
            candidato = self.servidor_set.all().order_by('-ativo', '-matricula').first()
        elif self.eh_aluno:
            candidato = self.aluno_set.all().order_by('-situacao__ativo', '-matricula').first()
        elif self.eh_prestador:
            candidato = self.prestadorservico_set.all().first()
        if candidato:
            return candidato.get_vinculo()
        from comum.models import Vinculo

        return Vinculo.objects.filter(pessoa_id=self.pk).order_by('-ativo').first()

    @property
    def banco_display(self):
        return f'{self.pagto_banco}, AG: {self.pagto_agencia}, CC: {self.pagto_ccor}'

    @property
    def ctps_display(self):
        return 'Número: {}, UF: {}, Prim.Emprego: {}, Série: {}'.format(
            self.ctps_numero or '',
            self.ctps_uf or '',
            self.ctps_data_prim_emprego and self.ctps_data_prim_emprego.strftime('%d/%m/%Y') or '',
            self.ctps_serie or '',
        )

    @property
    def cnh_display(self):
        return 'Cart: {}, Reg: {}, Categ: {}, Emissão: {}, UF: {}, Validade: {}'.format(
            self.cnh_carteira or '',
            self.cnh_registro or '',
            self.cnh_categoria or '',
            self.cnh_emissao or '',
            self.cnh_uf or '',
            self.cnh_validade or '',
        )

    @property
    def rg_display(self):
        return '{} - {}/{} - {}'.format(self.rg, self.rg_orgao or '', self.rg_uf or '', self.rg_data and self.rg_data.strftime('%d/%m/%Y') or '')

    @property
    def titulo_eleitoral_display(self):
        return 'Número: {}, Zona: {}, Seção: {}, UF: {}, Emissão: {}'.format(
            self.titulo_numero or '',
            self.titulo_zona or '',
            self.titulo_secao or '',
            self.titulo_uf or '',
            self.titulo_data_emissao and self.titulo_data_emissao.strftime('%d/%m/%Y') or '',
        )

    @property
    def idade(self):
        if self.nascimento_data:
            return get_age(self.nascimento_data)
        return '-'

    def tem_digital(self):
        return bool(self.get_template())

    def get_atendimento_enf_aberto(self):
        if 'saude' in settings.INSTALLED_APPS:
            from saude.models import Atendimento, SituacaoAtendimento, TipoAtendimento

            if Atendimento.objects.filter(
                tipo=TipoAtendimento.ENFERMAGEM_MEDICO, prontuario__vinculo__pessoa__pessoafisica=self, situacao=SituacaoAtendimento.ABERTO
            ).exists():
                return Atendimento.objects.filter(
                    tipo=TipoAtendimento.ENFERMAGEM_MEDICO, prontuario__vinculo__pessoa__pessoafisica=self, situacao=SituacaoAtendimento.ABERTO
                )[0].id
        return None

    def get_atendimento_odonto_aberto(self):
        if 'saude' in settings.INSTALLED_APPS:
            from saude.models import Atendimento, SituacaoAtendimento, TipoAtendimento

            if Atendimento.objects.filter(
                tipo=TipoAtendimento.ODONTOLOGICO, prontuario__vinculo__pessoa__pessoafisica=self, situacao=SituacaoAtendimento.ABERTO
            ).exists():
                return Atendimento.objects.filter(
                    tipo=TipoAtendimento.ODONTOLOGICO, prontuario__vinculo__pessoa__pessoafisica=self, situacao=SituacaoAtendimento.ABERTO
                )[0]
        return None

    def get_genero(self):
        return self.GENERO_CHOICES.get(self.genero, None)

    @property
    def emails(self):
        lista = []
        for vinculo in self.vinculo_set.all():
            if vinculo.email_pessoal:
                lista.append(vinculo.email_pessoal)
            if vinculo.user and vinculo.user.email:
                lista.append(vinculo.user.email)
            if vinculo.email_notificacao:
                lista.append(vinculo.email_notificacao)
        return ' - '.join(lista)

    @property
    def primeiro_ultimo_nome(self):
        nomes = self.nome.split(' ')
        return nomes[0], nomes[-1]

    @property
    def tipo_sanguineo(self):
        return f'{self.get_grupo_sanguineo_display()}{self.get_fator_rh_display()}'

    def get_cpf_ou_passaporte(self):
        if self.nacionalidade and int(self.nacionalidade) == Nacionalidade.ESTRANGEIRO and not self.cpf:
            return self.passaporte
        else:
            return self.cpf

    # @property
    # def eh_estrangeiro(self):
    #     return bool(self.nacionalidade and int(self.nacionalidade) == Nacionalidade.ESTRANGEIRO and not self.cpf)

    def projetos_extensao(self):
        if 'projetos' in settings.INSTALLED_APPS:
            ParticipacaoExtensao = apps.get_model('projetos', 'Participacao')
            return ParticipacaoExtensao.objects.filter(vinculo_pessoa__pessoa_id=self.id)
        else:
            return None

    def get_lattes(self):
        if not self.lattes and 'cnpq' in settings.INSTALLED_APPS:
            from cnpq.models import CurriculoVittaeLattes

            curriculo = CurriculoVittaeLattes.objects.filter(vinculo__pessoa_id=self.id).first()
            if curriculo:
                self.lattes = f'http://lattes.cnpq.br/{curriculo.numero_identificador}'
                self.save()
        return self.lattes

    def get_cpf_anonimo(self):
        return self.cpf and f'{self.cpf[0:3]}.***.***-{self.cpf[12:14]}' or '-'
