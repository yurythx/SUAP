import datetime

from django.core.exceptions import ValidationError

from djtools.db import models
from rh.models import UnidadeOrganizacional


class QuestionarioAcumuloCargos(models.ModelPlus):
    GERAL = 0
    TECNICO = 1
    DOCENTE = 2
    PUBLICO_CHOICES = [[GERAL, 'Geral'], [TECNICO, 'Técnicos'], [DOCENTE, 'Docentes']]

    descricao = models.CharField('Descrição', max_length=255)
    publico = models.IntegerField('Público', choices=PUBLICO_CHOICES)
    ano = models.IntegerField()
    data_inicio = models.DateField('Data de Início')
    data_fim = models.DateField('Data de Término')
    campus = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Campus', blank=True)

    class Meta:
        verbose_name = 'Questionário de Acúmulo de Cargos'
        verbose_name_plural = 'Questionários de Acúmulo de Cargos'

    def __str__(self):
        return f'{self.descricao} {self.ano} - {self.get_publico_display()} - {self.get_campus()}'

    def get_campus(self):
        if self.campus.count() == UnidadeOrganizacional.objects.suap().all().count():
            return 'Todos os campus'
        return ', '.join(self.campus.values_list('sigla', flat=True))

    @staticmethod
    def get_pendente(servidor):
        publico = [QuestionarioAcumuloCargos.GERAL]
        if servidor.eh_docente:
            publico.append(QuestionarioAcumuloCargos.DOCENTE)
        elif servidor.eh_tecnico_administrativo:
            publico.append(QuestionarioAcumuloCargos.TECNICO)
        else:
            return QuestionarioAcumuloCargos.objects.none()
        qs = QuestionarioAcumuloCargos.objects.filter(
            data_inicio__lte=datetime.datetime.today(), data_fim__gte=datetime.datetime.today(), publico__in=publico
        )
        return qs.filter(campus=servidor.campus)

    def get_percentual_respondido(self, servidor):
        if TermoAcumuloCargos.objects.filter(servidor=servidor, questionario_acumulo_cargos=self).exists():
            return 100
        return 0


class TermoAcumuloCargos(models.ModelPlus):
    servidor = models.ForeignKey('rh.Servidor', verbose_name='Servidor', blank=False, null=False, on_delete=models.CASCADE)
    questionario_acumulo_cargos = models.ForeignKey(
        QuestionarioAcumuloCargos, verbose_name='Questionário de Acúmulo de Cargos', blank=False, null=False, on_delete=models.CASCADE
    )

    nao_possui_outro_vinculo = models.BooleanField(
        'Não possuo qualquer outro vínculo ativo com a administração pública direta ou indireta nas esferas federal, estadual, distrital ou municipal, nem percebo proventos de aposentadoria, reforma ou pensão de nenhum órgão ou entidade da administração pública.',
        blank=False,
        null=False,
        default=False,
    )
    tem_outro_cargo_acumulavel = models.BooleanField(
        'Ocupo cargo público acumulável com compatibilidade de horários com o vínculo assumido com o IFRN, conforme disposto no Anexo I.',
        blank=False,
        null=False,
        default=False,
    )
    tem_aposentadoria = models.BooleanField(
        'Percebo proventos de aposentadoria devidamente acumuláveis com o cargo assumido no IFRN, conforme Anexo II.',
        blank=False,
        null=False,
        default=False,
    )
    tem_pensao = models.BooleanField(
        'Sou beneficiário de pensão, conforme informações prestadas em Anexo III.', blank=False, null=False, default=False
    )
    tem_atuacao_gerencial = models.BooleanField(
        'Tenho atuação gerencial em atividade mercantil, conforme informações prestadas em Anexo IV.', blank=False, null=False, default=False
    )
    exerco_atividade_remunerada_privada = models.BooleanField(
        'Exerço atividade remunerada privada, conforme informações prestadas em Anexo V.', blank=False, null=False, default=False
    )

    anexo1_pergunta1 = models.CharField('Orgão de Lotação', max_length=255, blank=True)
    anexo1_pergunta2 = models.CharField('UF', max_length=5, blank=True)
    anexo1_pergunta3 = models.CharField('Cargo/Emprego/Função que ocupa', max_length=255, blank=True)
    anexo1_pergunta4 = models.CharField('Jornada de trabalho do cargo/emprego/função', max_length=255, blank=True)
    anexo1_pergunta5 = models.CharFieldPlus('Nível de escolaridade do cargo/emprego/função', max_length=255, blank=True)
    anexo1_pergunta6 = models.DateFieldPlus('Data de ingresso no orgão', null=True, blank=True)
    anexo1_pergunta7 = models.CharFieldPlus(
        'Situação', max_length=255, blank=True, help_text='Quadro ou Tabela: Permanente, Temporário, Comissionado, etc.'
    )
    anexo1_pergunta8 = models.CharFieldPlus('Da Remuneração', max_length=255, blank=True, help_text='Vencimentos, Salários, Proventos, etc.')
    anexo1_pergunta9 = models.CharFieldPlus(
        'Natureza do Órgão', max_length=255, blank=True, help_text='Administração Direta, Autarquia, Empresa Pública ou Sociedade de Economia Mista'
    )
    anexo1_pergunta10 = models.CharFieldPlus('Subordinação', max_length=255, blank=True, help_text='Ministério, Secretaria de Estado/Município')
    anexo1_pergunta11 = models.CharFieldPlus('Esfera do Governo', max_length=255, blank=True, help_text='Federal, Estadual ou Municipal')
    anexo1_pergunta12 = models.CharFieldPlus(
        'Área de atuação do cargo', max_length=255, blank=True, help_text='Técnica/Científica, Saúde ou Magistério'
    )

    anexo2_pergunta1 = models.CharField('Cargo que deu origem à aposentadoria', max_length=255, blank=True)
    anexo2_pergunta2 = models.CharField('UF', max_length=5, blank=True)
    anexo2_pergunta3 = models.CharField('Fundamento legal da aposentadoria', max_length=255, blank=True)
    anexo2_pergunta4 = models.CharField('Ato legal da aposentadoria', max_length=255, blank=True)
    anexo2_pergunta5 = models.CharFieldPlus('Jornada de trabalho do cargo que exerceu', max_length=255, blank=True)
    anexo2_pergunta6 = models.CharFieldPlus('Nível de escolaridade do cargo/emprego/função', max_length=255, blank=True)
    anexo2_pergunta7 = models.DateFieldPlus('Data de vigência da aposentadoria', null=True, blank=True)
    anexo2_pergunta8 = models.CharFieldPlus(
        'Área de atuação do cargo', max_length=255, blank=True, help_text='Técnica/Científica, Saúde ou Magistério'
    )
    anexo2_pergunta9 = models.CharFieldPlus(
        'Natureza do Órgão', max_length=255, blank=True, help_text='Administração Direta, Autarquia, Empresa Pública ou Sociedade de Economia Mista'
    )
    anexo2_pergunta10 = models.CharFieldPlus('Subordinação', max_length=255, blank=True, help_text='Ministério, Secretaria de Estado/Município')
    anexo2_pergunta11 = models.CharFieldPlus('Esfera do Governo', max_length=255, blank=True, help_text='Federal, Estadual ou Municipal')

    anexo3_pergunta1 = models.CharField('Tipo de pensão', max_length=255, blank=True)
    anexo3_pergunta2 = models.CharField('Fundamento legal da pensão', max_length=255, blank=True)
    anexo3_pergunta3 = models.CharField('Grau de parentesco com o instituidor de pensão', max_length=255, blank=True)
    anexo3_pergunta4 = models.DateFieldPlus('Data de início de concessão do benefício', null=True, blank=True)
    anexo3_pergunta5 = models.CharFieldPlus(
        'Dependência econômica', max_length=255, blank=True, help_text='Certidão de casamento, nascimento, declaração de IR, etc'
    )

    anexo4_empresa_que_atua = models.CharFieldPlus('Empresa em que atua', max_length=255, blank=True)
    anexo4_tipo_atuacao_gerencial = models.CharFieldPlus('Tipo de atuação gerencial', max_length=255, blank=True)
    anexo4_tipo_sociedade_mercantil = models.CharFieldPlus('Tipo de sociedade mercantil', max_length=255, blank=True)
    anexo4_descricao_atividade_exercida = models.CharFieldPlus('Descrição da atividade comercial exercida', max_length=255, blank=True)
    anexo4_qual_participacao_societaria = models.CharFieldPlus('Qual a participação societária', max_length=255, blank=True)
    anexo4_data_inicio_atuacao = models.DateFieldPlus('Data de início da atuação', max_length=255, blank=True, null=True)
    anexo4_nao_exerco_atuacao_gerencial = models.BooleanField(
        'NÃO exerço qualquer atuação gerencial em atividade mercantil', blank=True, default=False
    )
    anexo4_nao_exerco_comercio = models.BooleanField('NÃO exerço comércio', blank=True, default=False)

    anexo5_nome_empresa_trabalha = models.CharFieldPlus('Nome da empresa onde trabalha/Empregador', max_length=255, blank=True)
    anexo5_funcao_emprego_ocupado = models.CharFieldPlus('Função ou emprego ocupado(tipo de atividade desempenhada)', max_length=255, blank=True)
    anexo5_jornada_trabalho = models.CharFieldPlus('Jornada de trabalho semanal a que está submetido', max_length=255, blank=True)
    anexo5_nivel_escolaridade_funcao = models.CharFieldPlus('Nível de escolaridade da função/emprego', max_length=255, blank=True)
    anexo5_data_inicio_atividade = models.DateFieldPlus('Data de início da atividade remunerada privada', max_length=255, blank=True, null=True)
    anexo5_nao_exerco_atividade_remunerada = models.BooleanField('NÃO exerço qualquer atividade remunerada privada', blank=True, default=False)

    alterado_por = models.ForeignKey(
        'comum.User', related_name='termoacumulocargos_alterado_por', null=True, blank=True, editable=False, on_delete=models.CASCADE
    )
    alterado_em = models.DateTimeField(auto_now=True)

    hash = models.CharFieldPlus('Hash', blank=True)

    class Meta:
        verbose_name = 'Termo Acumulação de Cargos'
        verbose_name_plural = 'Termos Acumulação de Cargos'
        unique_together = ('servidor', 'questionario_acumulo_cargos')

    def __str__(self):
        return f'{self.questionario_acumulo_cargos} - {self.servidor}'

    def clean(self):
        _errors = []
        msg = ''

        if self.nao_possui_outro_vinculo and (self.tem_outro_cargo_acumulavel or self.tem_pensao or self.tem_aposentadoria):
            msg = 'Se você marcar o campo que não possui outro vínculo, não pode marcar os outros campos.'
            _errors.append(msg)

        if not self.nao_possui_outro_vinculo and not (self.tem_outro_cargo_acumulavel or self.tem_pensao or self.tem_aposentadoria):
            msg = 'Você precisa marcar um dos campos da Declaração de acumulação de cargos.'
            _errors.append(msg)

        if self.tem_outro_cargo_acumulavel and not (
            self.anexo1_pergunta1
            and self.anexo1_pergunta2
            and self.anexo1_pergunta3
            and self.anexo1_pergunta4
            and self.anexo1_pergunta5
            and self.anexo1_pergunta6
            and self.anexo1_pergunta7
            and self.anexo1_pergunta8
            and self.anexo1_pergunta9
            and self.anexo1_pergunta10
            and self.anexo1_pergunta11
            and self.anexo1_pergunta12
        ):
            msg = 'Informe todos os dados do Anexo 1 sobre o cargo/emprego/função ocupado em outro órgão.'
            _errors.append(msg)

        if not self.tem_outro_cargo_acumulavel and (
            self.anexo1_pergunta1
            or self.anexo1_pergunta2
            or self.anexo1_pergunta3
            or self.anexo1_pergunta4
            or self.anexo1_pergunta5
            or self.anexo1_pergunta6
            or self.anexo1_pergunta7
            or self.anexo1_pergunta8
            or self.anexo1_pergunta9
            or self.anexo1_pergunta10
            or self.anexo1_pergunta11
            or self.anexo1_pergunta12
        ):
            msg = 'Para preencher os campos do anexo 1 é necessário marcar que possui outro vínculo ativo.'
            _errors.append(msg)

        if self.tem_aposentadoria and not (
            self.anexo2_pergunta1
            and self.anexo2_pergunta2
            and self.anexo2_pergunta3
            and self.anexo2_pergunta4
            and self.anexo2_pergunta5
            and self.anexo2_pergunta6
            and self.anexo2_pergunta7
            and self.anexo2_pergunta8
            and self.anexo2_pergunta9
            and self.anexo2_pergunta10
            and self.anexo2_pergunta11
        ):
            msg = 'Informe todos os dados do Anexo 2 sobre as informações de Aposentadoria em outro órgão.'
            _errors.append(msg)

        if not self.tem_aposentadoria and (
            self.anexo2_pergunta1
            or self.anexo2_pergunta2
            or self.anexo2_pergunta3
            or self.anexo2_pergunta4
            or self.anexo2_pergunta5
            or self.anexo2_pergunta6
            or self.anexo2_pergunta7
            or self.anexo2_pergunta8
            or self.anexo2_pergunta9
            or self.anexo2_pergunta10
            or self.anexo2_pergunta11
        ):
            msg = 'Para preencher os campos do anexo 2 é necessário marcar que percebe proventos de aposentadoria.'
            _errors.append(msg)

        if self.tem_pensao and not (
            self.anexo3_pergunta1 and self.anexo3_pergunta2 and self.anexo3_pergunta3 and self.anexo3_pergunta4 and self.anexo3_pergunta5
        ):
            msg = 'Informe todos os dados do Anexo 3 sobre as informações sobre Pensão Civil em outro órgão.'
            _errors.append(msg)

        if not self.tem_pensao and (
            self.anexo3_pergunta1 or self.anexo3_pergunta2 or self.anexo3_pergunta3 or self.anexo3_pergunta4 or self.anexo3_pergunta5
        ):
            msg = 'Para preencher os campos do anexo 3 é necessário marcar que é beneficiário de pensão.'
            _errors.append(msg)

        if self.tem_atuacao_gerencial and not (
            self.anexo4_empresa_que_atua
            and self.anexo4_tipo_atuacao_gerencial
            and self.anexo4_tipo_sociedade_mercantil
            and self.anexo4_descricao_atividade_exercida
            and self.anexo4_qual_participacao_societaria
            and self.anexo4_data_inicio_atuacao
        ):
            msg = 'Informe todos os dados do Anexo 4 sobre as informações de atuação gerencial em atividade mercantil.'
            _errors.append(msg)

        if self.tem_atuacao_gerencial and self.anexo4_nao_exerco_atuacao_gerencial and self.anexo4_nao_exerco_comercio:
            msg = 'Você não pode marcar as opções de que não exerce atuação gerencial e não exerce comércio juntamente.'
            _errors.append(msg)

        if not self.tem_atuacao_gerencial and not self.anexo4_nao_exerco_atuacao_gerencial and not self.anexo4_nao_exerco_comercio:
            msg = 'Se você não tem atuação gerencial em atividade mercantil, marque as opções corretas na área do anexo 4'
            _errors.append(msg)

        if not self.tem_atuacao_gerencial and (
            self.anexo4_empresa_que_atua
            or self.anexo4_tipo_atuacao_gerencial
            or self.anexo4_tipo_sociedade_mercantil
            or self.anexo4_descricao_atividade_exercida
            or self.anexo4_qual_participacao_societaria
            or self.anexo4_data_inicio_atuacao
        ):
            msg = 'Para preencher os campos do anexo 4 é necessário marcar que tem atuação gerencial em atividade mercantil.'
            _errors.append(msg)

        if self.exerco_atividade_remunerada_privada and not (
            self.anexo5_nome_empresa_trabalha
            and self.anexo5_funcao_emprego_ocupado
            and self.anexo5_jornada_trabalho
            and self.anexo5_nivel_escolaridade_funcao
            and self.anexo5_data_inicio_atividade
        ):
            msg = 'Informe todos os dados do anexo 5 sobre atividade remunerada privada.'
            _errors.append(msg)

        if self.exerco_atividade_remunerada_privada and self.anexo5_nao_exerco_atividade_remunerada:
            msg = 'Você não pode marcar a opção NÃO exerço atividade remunerada privada.'
            _errors.append(msg)

        if not self.exerco_atividade_remunerada_privada and not self.anexo5_nao_exerco_atividade_remunerada:
            msg = 'Por favor, se você não exerce atividade remunerada privada, marque esta opções no anexo 5.'
            _errors.append(msg)

        if _errors:
            raise ValidationError(_errors)

    @property
    def termo_hash(self):
        return '{}{}{}{}{}{}'.format(
            self.nao_possui_outro_vinculo and 'sim' or 'nao',
            self.tem_outro_cargo_acumulavel and 'sim' or 'nao',
            self.tem_aposentadoria and 'sim' or 'nao',
            self.tem_pensao and 'sim' or 'nao',
            self.tem_atuacao_gerencial and 'sim' or 'nao',
            self.exerco_atividade_remunerada_privada and 'sim' or 'nao',
        )

    def get_absolute_url(self):
        return f'/temp_rh3/termoacumulocargos/{self.id}/'
