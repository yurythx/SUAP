import uuid

from django.apps.registry import apps
from django.conf import settings
from pycpfcnpj import cpfcnpj

from djtools.choices import NATUREZA_JURIDICA_CHOICES
from djtools.db import models
from djtools.utils import anonimizar_cpf, running_tests
from rh.managers import PessoaManager


class Pessoa(models.ModelPlus):
    SEARCH_FIELDS = ['search_fields_optimized']
    PUBLIC_SEARCH = True
    RELEVANCE_ORDERING = [
        ('pessoafisica__eh_servidor', True),
        ('pessoafisica__eh_prestador', True),
        ('pessoafisica__eh_aluno', True),
        ('pessoajuridica__isnull', False),
    ]

    nome = models.UnaccentField(max_length=200, db_index=True)
    nome_usual = models.UnaccentField(
        'Nome Usual', max_length=30, blank=True, help_text='O nome apresentado no crachá ou razão social', db_index=True
    )
    nome_social = models.UnaccentField('Nome Social', max_length=200, blank=True, db_index=True)
    nome_registro = models.UnaccentField('Nome de Registro', max_length=200, blank=True, db_index=True)
    website = models.URLField(blank=True)
    natureza_juridica = models.CharField('Natureza Jurídica', max_length=5, blank=True, choices=NATUREZA_JURIDICA_CHOICES)

    uuid = models.UUIDField(unique=True, default=uuid.uuid4)

    """
     Campo de busca criado para otimizar a consulta em Pessoa, PessoaFisica e PessoaJuridica.
     Caso os campos definidos em SEARCH_FIELDS envolvam mais de uma entidade, o que é o caso, a engine do banco de
     dados acaba tendo que fazer uma busca sequencial (Seq Scan). A ideia deste novo atributo é concentrar todas essas
     informações, de forma que o banco de dados possa fazer uma busca otimizada (Bitmap Scan), já que apenas uma coluna
     de uma tabela será alvo da consulta. Obs: Os dados redundantes, presentes nesse atributo, serão atualizados no save
     de Pessoa. Cada entidade filha deverá definir esse conteúdo através da sobreescrita do método
     _get_search_fields_optimized_content_to_save.

     Durante' os testes, no universo de 315.000 registros, a consulta caiu, em média, de 4 segundos para 0,2 segundos.
    """
    search_fields_optimized = models.UnaccentField(max_length=400, db_index=True)

    objects = PessoaManager()

    # Hints for autocomplete rendering: preload child tables used by get_ext_combo_template
    EXT_COMBO_RELATED = {
        'select_related': ['pessoafisica', 'pessoajuridica'],
        'prefetch_related': [],
    }

    class Meta:
        db_table = 'pessoa'
        ordering = ('nome',)
        permissions = (
            ('pode_editar_email_secundario_servidor', 'Pode editar e-mail secundário'),
            ('pode_editar_email_institucional', 'Pode editar e-mail institucional'),
            ('pode_editar_email_secundario_aluno', 'Pode editar e-mail secundário do aluno'),
            ('pode_editar_email_secundario_prestador', 'Pode editar e-mail secundário do Prestador de Serviço'),
            ('pode_editar_email_academico', 'Pode editar e-mail acadêmico'),
            ('pode_editar_email_google_classroom', 'Pode editar e-mail google classroom'),
        )

    def __str__(self):
        if hasattr(self, 'pessoafisica'):
            from rh.models import Servidor

            Aluno = None
            if 'edu' in settings.INSTALLED_APPS:
                Aluno = apps.get_model('edu', 'aluno')

            qs_servidor = Servidor.objects.filter(pessoa_fisica__id=self.id)

            qs_aluno = None
            if Aluno:
                qs_aluno = Aluno.objects.filter(pessoa_fisica__id=self.id)

            if qs_servidor.exists():
                matricula, nome, cpf = qs_servidor.values_list('matricula', 'pessoa_fisica__nome', 'pessoa_fisica__cpf')[0]
                if not cpf:
                    cpf = ''
                return f'{nome} (CPF: {anonimizar_cpf(cpf)}, Servidor {matricula})'
            elif Aluno and qs_aluno.exists():
                matricula, nome, cpf = qs_aluno.values_list('matricula', 'pessoa_fisica__nome', 'pessoa_fisica__cpf')[0]
                if not cpf:
                    cpf = ''
                return f'{nome} (CPF: {anonimizar_cpf(cpf)}, Aluno {matricula})'
            else:
                cpf = self.pessoafisica.cpf
                if not cpf:
                    cpf = ''
                return f'{self.pessoafisica.nome} (CPF: {anonimizar_cpf(cpf)})'
        elif hasattr(self, 'pessoajuridica'):  # Pessoa jurídica
            return f'{self.pessoajuridica.nome} ({self.pessoajuridica.cnpj})'
        else:
            return self.nome

    def get_representantes(self):
        return self.pessoajuridica.ocupacaoprestador_set.filter(ocupacao__representante=True) if hasattr(self, 'pessoajuridica') else ''

    def get_absolute_url(self):
        if hasattr(self, 'pessoajuridica'):
            return self.pessoajuridica.get_absolute_url()
        elif hasattr(self, 'pessoafisica'):
            return self.pessoafisica.get_absolute_url()

    def save(self, *args, **kwargs) -> None:
        """
        Caso `self` tenha username, um usuário será criado para `self`.
        """
        # Ajustando as informações reduntantes que serão usadas para uma busca mais eficiente na entidade.
        self.search_fields_optimized = self._get_search_fields_optimized_content_to_save()

        return super().save(*args, **kwargs)

    def _get_search_fields_optimized_content_to_save(self):
        """
        Esse método retorna o conteúdo que deverá ser armazenado no atributo search_fields_optimized. As classes filhas
        de Pessoa deverão sobreescrever esse método para personalizar essa informação.
        :return: texto
        """
        return f'{self.nome_social}{self.nome_registro}{self.nome_usual}'

    def get_foto_75x100_url(self):
        retorno = '/static/comum/img/default.jpg'
        if hasattr(self, 'pessoafisica'):
            retorno = self.pessoafisica.get_foto_75x100_url()
        elif hasattr(self, 'pessoajuridica'):
            retorno = self.pessoajuridica.get_foto_75x100_url()
        return retorno

    def get_foto_150x200_url(self):
        retorno = '/static/comum/img/default.jpg'
        if hasattr(self, 'pessoafisica'):
            retorno = self.pessoafisica.get_foto_150x200_url()
        elif hasattr(self, 'pessoajuridica'):
            retorno = self.pessoajuridica.get_foto_150x200_url()
        return retorno

    def get_ext_combo_template(self):
        if hasattr(self, 'pessoafisica'):
            template = self.pessoafisica.get_ext_combo_template()
        elif hasattr(self, 'pessoajuridica'):
            template = self.pessoajuridica.get_ext_combo_template()
        else:
            out = [f'{self.nome}']
            template = """
                      <div>
                          {}
                      </div>
                      """.format(''.join(out))

        return template

    # TODO: Talvez essas properties possam virar atributos
    @property
    def eh_pessoa_fisica(self):
        retorno = False
        if hasattr(self, 'pessoafisica'):
            retorno = True
        return retorno

    # TODO: Talvez essas properties possam virar atributos
    @property
    def eh_pessoa_juridica(self):
        retorno = False
        if hasattr(self, 'pessoajuridica'):
            retorno = True
        return retorno

    def get_cpf_ou_cnpj(self):
        if hasattr(self, 'pessoafisica'):
            return self.pessoafisica.cpf
        elif hasattr(self, 'pessoajuridica'):  # Pessoa jurídica
            return self.pessoajuridica.cnpj
        return '-'

    def get_cpf_ou_cnpj_ou_passaporte(self):
        """Retorna CPF, CNPJ ou passaporte (para estrangeiros) quando disponível.

        - Se for pessoa física e estrangeira com passaporte preenchido, retorna o passaporte.
        - Se for pessoa física sem passaporte/CPF, retorna o CPF (pode ser None).
        - Se for pessoa jurídica, retorna o CNPJ.
        - Caso contrário, retorna '-'.
        """
        if hasattr(self, 'pessoafisica'):
            return self.pessoafisica.get_cpf_ou_passaporte()
        elif hasattr(self, 'pessoajuridica'):
            return self.pessoajuridica.cnpj
        return '-'

    def cpf_ou_cnpj_valido(self):
        if running_tests():
            return True

        if hasattr(self, 'pessoafisica'):
            if not self.pessoafisica.cpf:
                return False
            return cpfcnpj.validate(self.pessoafisica.cpf)

        if hasattr(self, 'pessoajuridica'):
            if not self.pessoajuridica.cnpj:
                return False
            return cpfcnpj.validate(self.pessoajuridica.cnpj)

        return False

    @property
    def telefones(self):
        tels = ' / '.join([self.telefones_pessoais or '', self.telefones_institucionais or ''])
        if tels.strip().endswith('/'):
            tels = tels.strip()[:-1]
        return tels

    @property
    def telefones_pessoais(self):
        return ', '.join(self.pessoatelefone_set.values_list('numero', flat=True))

    @property
    def telefones_institucionais(self):
        out = []
        if hasattr(self, 'setor') and self.setor:
            for st in self.setor.setortelefone_set.all():
                out.append(f'{st}')
        return ', '.join(out)

    @property
    def endereco(self):
        return str(self.pessoaendereco or '')

    @property
    def endereco_cep(self):
        return self.pessoaendereco.cep if self.pessoaendereco else ''

    @property
    def endereco_municipio(self):
        return self.pessoaendereco.municipio if self.pessoaendereco else ''

    @property
    def endereco_logradouro(self):
        return self.pessoaendereco.logradouro if self.pessoaendereco else ''

    @property
    def endereco_numero(self):
        return self.pessoaendereco.numero if self.pessoaendereco else ''

    @property
    def endereco_complemento(self):
        return self.pessoaendereco.complemento if self.pessoaendereco else ''

    @property
    def endereco_bairro(self):
        return self.pessoaendereco.bairro if self.pessoaendereco else ''

    @property
    def pessoaendereco(self):
        return self.pessoaendereco_set.order_by('-pk').first()
