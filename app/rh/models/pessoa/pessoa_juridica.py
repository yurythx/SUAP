import re

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from pycpfcnpj import cpfcnpj

from djtools.db import models
from djtools.utils import normalizar_nome_proprio

from .pessoa import Pessoa


class PessoaJuridica(Pessoa):
    SEARCH_FIELDS = ['search_fields_optimized']
    RELEVANCE_ORDERING = []

    nome_fantasia = models.CharFieldPlus(verbose_name='Nome Fantasia', blank=True)
    cnpj = models.BrCnpjField(unique=True)
    ativo = models.BooleanField(verbose_name='Ativo', default=True, help_text='Indica se o servidor está ativo na instituição')

    ramo_atividade = models.CharFieldPlus(verbose_name='Ramo de Atividade', null=True, blank=True)
    nome_representante_legal = models.CharFieldPlus(verbose_name='Nome do Representante Legal', null=True, blank=True)

    inscricao_estadual = models.CharField(max_length=20, null=True, blank=True, verbose_name='Inscrição Estadual')
    matricula = models.CharFieldPlus('Matrícula', max_length=30, db_index=True)
    vinculos = GenericRelation(
        'comum.Vinculo',
        related_query_name='pessoasjuridicas',
        object_id_field='id_relacionamento',
        content_type_field='tipo_relacionamento',
    )

    optante_simples = models.BooleanField('Optante do SIMPLES', null=True)
    optante_mei = models.BooleanField('Optante do MEI', null=True)

    # Atributos obtidos via integração com a API da Receita Federal
    situacao_cadastral_codigo = models.CharFieldPlus('Código da Situação Cadastral', max_length=30, null=True, blank=True)
    situacao_cadastral_motivo = models.CharFieldPlus('Motivo da Situação Cadastral', max_length=100, null=True, blank=True)
    situacao_cadastral_data = models.DateFieldPlus('Data da Situação Cadastral', null=True, blank=True)

    natureza_juridica_codigo = models.CharFieldPlus('Código da Natureza Jurídica', max_length=30, null=True, blank=True)
    natureza_juridica_descricao = models.CharFieldPlus('Descricao da Natureza Juridica', max_length=150, null=True, blank=True)
    data_abertura = models.DateFieldPlus('Data de Abertura', null=True, blank=True)

    cnae_principal_codigo = models.CharFieldPlus('Código CNAE Principal', max_length=30, null=True, blank=True)
    cnae_principal_descricao = models.CharFieldPlus('Descrição do CNAE Principal', max_length=150, null=True, blank=True)

    class Meta:
        db_table = 'pessoa_juridica'
        verbose_name = 'Pessoa Jurídica'
        verbose_name_plural = 'Pessoas Jurídicas'

    def __str__(self):
        if self.nome_fantasia and len(self.nome_fantasia) > 1:
            return f'{normalizar_nome_proprio(self.nome_fantasia)} ({self.matricula})'
        return f'{normalizar_nome_proprio(self.nome)} ({self.matricula})'

    def get_absolute_url(self):
        return f'/rh/pessoajuridica/{self.pk}/'

    def get_vinculo(self):
        return self.vinculo_set.first()

    def get_foto_75x100_url(self):
        return '/static/comum/img/default.jpg'

    def get_foto_150x200_url(self):
        return '/static/comum/img/default.jpg'

    def get_representantes(self):
        return self.ocupacaoprestador_set.filter(ocupacao__representante=True)

    def get_ext_combo_template(self):
        out = [f'{self.pessoajuridica.nome} ({self.pessoajuridica.cnpj})']
        template = """
              <div>
                  {}
              </div>
              """.format(''.join(out))

        if not self.ativo:
            template += '<p class="false">Vínculo inativo</p>'

        return template

    def get_user(self):
        from comum.models import User

        return User.objects.filter(username=self.matricula).first()

    def _get_search_fields_optimized_content_to_save(self):
        return '{}{}{}'.format(self.nome or '', self.cnpj or '', self.matricula or '')

    @staticmethod
    def adicionar_pessoajuridica_importar_api_cnpj(cnpj):
        from comum.models import APIExterna

        if not APIExterna.CNPJ.ativo:
            raise ValidationError('A integração com a API de CNPJ está desativada.')

        api_service = APIExterna.CNPJ.get_service()
        sucesso, dict_resposta = api_service.consulta_empresa(cnpj)
        if sucesso:
            pessoa_juridica, criou = PessoaJuridica.objects.update_or_create(
                cnpj=cnpj,
                nome='nomeEmpresarial',
                nome_fantasia=dict_resposta['nomeFantasia'],
                nome_representante_legal=dict_resposta['socios'][0]['representanteLegal'],
            )
            if criou:
                return pessoa_juridica

    def save(self, *args, **kwargs):
        from comum.models import Vinculo

        if not cpfcnpj.validate(self.cnpj):
            raise ValidationError(f'O CNPJ {self.cnpj} associado a {self.nome_fantasia} não é valido.')

        self.matricula = re.sub(r'\D', '', str(self.cnpj))

        super().save(*args, **kwargs)

        user = self.get_user()
        defaults = {
            'pessoa': self.pessoa_ptr,
            'user': user,
            'ativo': False,
        }
        tipo_relacionamento = ContentType.objects.get_for_model(self)
        Vinculo.objects.update_or_create(id_relacionamento=self.id, tipo_relacionamento=tipo_relacionamento, defaults=defaults)
        return self


class PessoaJuridicaContato(models.ModelPlus):
    pessoa_juridica = models.ForeignKey(PessoaJuridica, on_delete=models.CASCADE)
    descricao = models.CharField('Descrição', null=True, max_length=200)
    telefone = models.CharField('Telefone', null=True, max_length=45)
    email = models.EmailField('E-mail', null=True)
    via_form_suap = models.BooleanField('Via SUAP?', default=False)

    class Meta:
        verbose_name = 'Contato da Pessoa Jurídica'
        verbose_name_plural = 'Contatos da Pessoa Jurídica'

    def __str__(self):
        return f'{self.descricao}{self.telefone}'
