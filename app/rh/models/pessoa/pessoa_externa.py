import re
from djtools.db import models
from djtools.storages.utils import get_overwrite_storage
from djtools.thumbs import ImageWithThumbsField
from djtools.utils import anonimizar_cpf
from rh.enums import Nacionalidade
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from djtools.choices import NATUREZA_JURIDICA_CHOICES


class PessoaExterna(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'cpf', 'user__username', 'matricula']
    # Campos próprios daqui que não existem mais em PessoaFisica (migraram para Vinculo em comum/0114).
    CAMPOS_MIGRADOS_VINCULO = ('email', 'email_secundario', 'foto', 'sistema_origem', 'raca_id', 'deficiencia_id')
    MENSAGEM_TROCA_DE_CPF = 'Esta pessoa já tem documento: a troca de CPF é feita na tela da pessoa física.'

    nome = models.UnaccentField(max_length=200, db_index=True)
    nome_usual = models.UnaccentField(
        'Nome Usual', max_length=30, blank=True, help_text='O nome apresentado no crachá ou razão social', db_index=True
    )
    nome_social = models.UnaccentField('Nome Social', max_length=200, blank=True, db_index=True)
    nome_registro = models.UnaccentField('Nome de Registro', max_length=200, blank=True, db_index=True)
    email = models.EmailField(blank=True, verbose_name='E-mail Principal')
    email_secundario = models.EmailField(blank=True, verbose_name='E-mail Secundário', help_text='E-mail utilizado para recuperação de senha.')
    website = models.URLField(blank=True)
    excluido = models.BooleanField(verbose_name='Excluído', default=False, help_text='Indica se a última ocorrência é de exclusão')
    setores_adicionais = models.ManyToManyField(
        'rh.Setor',
        verbose_name='Setores Adicionais',
        blank=True,
        help_text='O funcionário terá acesso aos processos dos setores adicionais no sistema de protocolo.',
    )
    natureza_juridica = models.CharField('Natureza Jurídica', max_length=5, blank=True, choices=NATUREZA_JURIDICA_CHOICES)
    sistema_origem = models.CharField(
        max_length=50,
        blank=True,
        choices=[['', 'Cadastro manual'], ['SIAPE', 'SIAPE'], ['WS-SIAPE', 'WS-SIAPE'], ['SIAFI', 'SIAFI']],
        help_text='Indica de qual sistema a pessoa veio: SIAPE, SIAFI etc',
    )

    cpf = models.CharField(max_length=20, null=True, verbose_name='CPF', blank=False, db_index=True)
    sexo = models.CharField(max_length=1, null=True, choices=[['M', 'Masculino'], ['F', 'Feminino']])
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
    nascimento_municipio = models.ForeignKey('comum.Municipio', null=True, blank=True, verbose_name='Município', on_delete=models.CASCADE)
    nascimento_data = models.DateFieldPlus('Data de Nascimento', null=True)
    nome_mae = models.CharField('Nome da Mãe', max_length=100, null=True)
    nome_pai = models.CharField('Nome do Pai', max_length=100, null=True, blank=True)
    foto = ImageWithThumbsField(
        storage=get_overwrite_storage(),
        use_id_for_name=True,
        upload_to='fotos_pessoa_externa',
        sizes=((75, 100), (150, 200)),
        null=True,
        blank=True,
    )
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
    pis_pasep = models.CharField(max_length=20, null=True, blank=True)
    pagto_banco = models.ForeignKey('rh.Banco', null=True, blank=True, on_delete=models.CASCADE)
    pagto_agencia = models.CharField(max_length=20, null=True, blank=True)
    pagto_ccor = models.CharField(max_length=20, null=True, blank=True)
    pagto_ccor_tipo = models.CharField(max_length=2, blank=True, null=True)
    username = models.CharField(max_length=50, null=True, unique=True, db_index=True)
    tem_digital_fraca = models.BooleanField(
        default=False,
        blank=True,
        verbose_name='Permitir registro de ponto sem impressão digital',
        help_text='Servidores com impressão digital fraca devem ter essa opção marcada',
    )
    senha_ponto = models.CharField(
        max_length=128,
        blank=True,
        verbose_name='Senha para registro de ponto sem impressão digital',
        help_text='Servidores com impressão digital fraca devem ter uma senha definida para bater o ponto',
    )
    data_obito = models.DateField(null=True, blank=True)
    template = models.BinaryField(null=True, blank=True, editable=False)
    template_importado_terminal = models.BooleanField(default=False, verbose_name='Digital importada do terminal')
    # busca = SearchField(search=['nome', 'get_cpf_ou_cnpj'])
    estado_civil = models.ForeignKey('comum.EstadoCivil', null=True, on_delete=models.CASCADE)
    raca = models.ForeignKey('comum.Raca', null=True, on_delete=models.CASCADE)

    nacionalidade = models.IntegerField('Nacionalidade', choices=Nacionalidade.get_choices(), null=True)
    pais_origem = models.ForeignKey('comum.Pais', verbose_name='País de Origem', null=True, on_delete=models.CASCADE)  # para estrangeiro

    deficiencia = models.ForeignKey('rh.Deficiencia', verbose_name='Deficiência', null=True, on_delete=models.CASCADE)
    lattes = models.URLField(blank=True)
    matricula = models.CharFieldPlus('Matrícula', null=True, blank=False, max_length=30, db_index=True)
    pessoa_fisica = models.ForeignKeyPlus('rh.PessoaFisica')
    vinculos = GenericRelation(
        'comum.Vinculo', related_query_name='pessoasexternas', object_id_field='id_relacionamento', content_type_field='tipo_relacionamento'
    )

    class Meta:
        verbose_name = 'Pessoa Externa'
        verbose_name_plural = 'Pessoas Externas'

    def __str__(self):
        return f'{self.nome} - {self.matricula}'

    def get_absolute_url(self):
        return f'/admin/rh/pessoaexterna/{self.pk}/view/'

    def get_vinculo(self):
        return self.vinculos.first()

    def get_ext_combo_template(self):
        template = """
                    <div class="person">
                        <div>
                            <h4>{} ({})</h4>
                            <h5>Pessoa Externa</h5>
                        </div>
                    </div>
                    <p class="false">Vínculo inativo</p>
                    """.format(self.nome or 'Sem nome', anonimizar_cpf(self.cpf))

        return template

    def get_user(self):
        from comum.models import User

        return User.objects.filter(username=self.matricula).first()

    @property
    def pessoafisica(self):
        return self.pessoa_fisica

    def save(self, *args, **kwargs) -> PessoaExterna:
        from comum.models import Vinculo
        from rh.deduplicacao.entrada import Politica, verificar_documento

        from .pessoa_fisica import PessoaFisica

        self.matricula = re.sub(r'\D', '', str(self.cpf or '')) or None
        if not self.pessoa_fisica_id:
            # ponytail: as colunas copiadas de PessoaFisica estão mortas (revisão da PessoaExterna em spec próprio);
            # na criação, só alimentam a obtenção da pessoa e nunca sobrescrevem uma PF existente (PREENCHER só completa o vazio).
            # verificar_documento recusa, antes, o CPF de uma pessoa com outra data de nascimento.
            verificar_documento(cpf=self.cpf, nascimento_data=self.nascimento_data)
            self.pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(self._dados_pessoa_fisica(PessoaFisica), Politica.PREENCHER)
        elif self.pk and self.cpf_diverge_da_pessoa_fisica(self.cpf, PessoaExterna.objects.filter(pk=self.pk).values_list('cpf', flat=True).first()):
            # edição sem o formulário: a externa com um CPF e a PF com outro desencontram os lookups por CPF
            raise ValidationError({'cpf': self.MENSAGEM_TROCA_DE_CPF})
        else:
            self._atualizar_pessoa_fisica_exclusiva(PessoaFisica)
        super().save(*args, **kwargs)

        defaults = {'pessoa': self.pessoa_fisica.pessoa_ptr, 'ativo': False}
        tipo_relacionamento = ContentType.objects.get_for_model(self)
        vinculo, _ = Vinculo.objects.update_or_create(id_relacionamento=self.id, tipo_relacionamento=tipo_relacionamento, defaults=defaults)
        self._espelhar_campos_migrados(vinculo)
        return self

    def cpf_diverge_da_pessoa_fisica(self, cpf: str | None, cpf_gravado: str | None) -> bool:
        """Se ``cpf`` troca o ``cpf_gravado`` por um diferente do da PF que já tem documento válido (``preservar_documento``).

        Só a troca é recusada: a externa legada que já divergia continua salvável sem mexer no CPF (alinhá-la é decisão à parte).
        A troca de documento é pela tela da pessoa física; sem documento válido, a PF recebe o CPF da externa.
        """
        from rh.deduplicacao.documentos import digitos
        from rh.deduplicacao.entrada import tem_documento_valido

        if digitos(cpf) == digitos(cpf_gravado) or not self.pessoa_fisica_id:
            return False
        return tem_documento_valido(self.pessoa_fisica) and digitos(cpf) != digitos(self.pessoa_fisica.cpf)

    def _atualizar_pessoa_fisica_exclusiva(self, modelo_pessoa_fisica: type) -> None:
        """Leva a edição da externa à PF quando ela só pertence a esta externa; PF com outro vínculo nunca é tocada."""
        from comum.models import Vinculo
        from rh.deduplicacao.entrada import Politica, aplicar_politica

        tipo_relacionamento = ContentType.objects.get_for_model(self)
        outros_vinculos = Vinculo.objects.filter(pessoa_id=self.pessoa_fisica_id).exclude(
            tipo_relacionamento=tipo_relacionamento, id_relacionamento=self.pk
        )
        if outros_vinculos.exists():
            return
        aplicar_politica(self.pessoa_fisica, self._dados_pessoa_fisica(modelo_pessoa_fisica), Politica.AUTORITATIVA, preservar_documento=True)
        self.pessoa_fisica.save()

    def _dados_pessoa_fisica(self, modelo_pessoa_fisica: type) -> dict:
        campos_pessoa = {campo.attname for campo in modelo_pessoa_fisica._meta.concrete_fields}
        ignorados = {'id', 'pessoa_ptr_id', 'matricula', 'pessoa_fisica_id', 'excluido', *self.CAMPOS_MIGRADOS_VINCULO}
        return {
            campo.attname: getattr(self, campo.attname)
            for campo in self._meta.concrete_fields
            if campo.attname in campos_pessoa and campo.attname not in ignorados
        }

    def _espelhar_campos_migrados(self, vinculo):
        """Copia para o vínculo os campos que deixaram de existir em PessoaFisica.

        email/email_secundario alimentam `email_pessoal`, ficando o 1º não institucional
        (mesma regra do backfill comum/0115).
        """
        from comum.models import Configuracao

        candidatos = [e for e in (self.email_secundario, self.email) if e and not Configuracao.eh_email_institucional(e)]
        vinculo.email_pessoal = candidatos[0] if candidatos else ''
        vinculo.foto = self.foto
        vinculo.sistema_origem = self.sistema_origem
        vinculo.raca_id = self.raca_id
        vinculo.deficiencia_id = self.deficiencia_id
        vinculo.save(update_fields=['email_pessoal', 'foto', 'sistema_origem', 'raca_id', 'deficiencia_id'])
