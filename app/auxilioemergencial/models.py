import datetime

from dateutil.relativedelta import relativedelta
from django.utils.safestring import mark_safe

from djtools.db import models
from djtools.templatetags.filters import format_
from rh.models import UnidadeOrganizacional

TIPOCONTA_CONTACORRENTE = 'Conta Corrente'
TIPOCONTA_POUPANCA = 'Conta Poupança'

TIPOCONTA_CHOICES = ((TIPOCONTA_CONTACORRENTE, 'Conta Corrente'), (TIPOCONTA_POUPANCA, 'Conta Poupança'))

PENDENTE_ASSINATURA = 'Pendente de assinatura do responsável'
INSCRICAO_CONCLUIDA = 'Concluída'
SITUACAO_CHOICES = (
    (INSCRICAO_CONCLUIDA, INSCRICAO_CONCLUIDA),
    (PENDENTE_ASSINATURA, PENDENTE_ASSINATURA),
)
DEFERIDO_SEM_RECURSO = 'Deferido, mas sem recurso disponível para atendimento no momento'
PENDENTE_DOCUMENTACAO = 'Pendente de documentação complementar'
SEM_PARECER = 'Sem parecer'
DEFERIDO = 'Deferido'
PARECER_CHOICES = (
    (SEM_PARECER, SEM_PARECER),
    (DEFERIDO, DEFERIDO),
    (DEFERIDO_SEM_RECURSO, DEFERIDO_SEM_RECURSO),
    (PENDENTE_DOCUMENTACAO, PENDENTE_DOCUMENTACAO),
    ('Indeferido', 'Indeferido'),
)

PARECER_FORM_CHOICES = (
    ('Deferido', 'Deferido'),
    (DEFERIDO_SEM_RECURSO, DEFERIDO_SEM_RECURSO),
    (PENDENTE_DOCUMENTACAO, PENDENTE_DOCUMENTACAO),
    ('Indeferido', 'Indeferido'),
)


def get_inscricao_aluno(obj):
    return InscricaoAluno.objects.get(aluno=obj.aluno)


def get_inscricoes_anteriores(obj):
    lista = []
    if (
        InscricaoInternet.objects.filter(aluno=obj.aluno, fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)
        .exclude(edital=obj.edital)
        .exists()
    ):
        lista.append('Serviço de Internet')
    if (
        InscricaoDispositivo.objects.filter(aluno=obj.aluno, fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)
        .exclude(edital=obj.edital)
        .exists()
    ):
        lista.append('Aquisição de Dispositivo Eletrônico')
    if (
        InscricaoMaterialPedagogico.objects.filter(
            aluno=obj.aluno, fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False
        )
        .exclude(edital=obj.edital)
        .exists()
    ):
        lista.append('Material Didático Pedagógico')
    if (
        InscricaoAlunoConectado.objects.filter(
            aluno=obj.aluno, fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False
        )
        .exclude(edital=obj.edital)
        .exists()
    ):
        lista.append('Projeto Alunos Conectados')
    return ', '.join(lista)


def get_situacao_prestacao_contas(obj):
    if obj.situacao_prestacao_contas == InscricaoDispositivo.PENDENTE_VALIDACAO:
        return '<span class="status status-alert">Pendente de validação</span>'
    elif obj.situacao_prestacao_contas == InscricaoDispositivo.CONCLUIDA:
        return '<span class="status status-success">Concluída</span>'
    return '<span class="status status-info">Aguardando documentos</span>'


def pode_cadastrar_prestacao_contas(obj):
    if (
        obj.parecer == 'Deferido'
        and obj.termo_compromisso_assinado_em
        and obj.situacao_prestacao_contas == InscricaoDispositivo.AGUARDANDO_DOCUMENTOS
    ):
        if not obj.prestacao_contas_cadastrada_em:
            return True
        if obj.prestacao_contas_cadastrada_em and obj.data_limite_envio_prestacao_contas >= datetime.datetime.now().date():
            return True
    return False


def pode_atualizar_documentacao(obj):
    if obj.edital.eh_ativo():
        if obj.parecer == SEM_PARECER:
            return True
    return bool(obj.parecer == PENDENTE_DOCUMENTACAO and obj.data_limite_envio_documentacao >= datetime.datetime.now().date())


def tem_dados_bancarios(obj):
    inscricao = InscricaoAluno.objects.filter(aluno=obj.aluno)
    if inscricao.exists():
        return inscricao[0].tem_dados_bancarios()
    return False


def pode_assinar_termo(obj):
    if obj.data_limite_assinatura_termo:
        data_limite = obj.data_limite_assinatura_termo
        data_limite = datetime.datetime(data_limite.year, data_limite.month, data_limite.day, 23, 59, 59)
        return (
            obj.tem_dados_bancarios() and obj.parecer == 'Deferido' and data_limite >= datetime.datetime.now() and not obj.termo_compromisso_assinado
        )
    return False


def get_parecer(obj):
    if obj.parecer == 'Deferido':
        return f'<span class="status status-success">{obj.parecer}</span>'
    elif obj.parecer == DEFERIDO_SEM_RECURSO or obj.parecer == PENDENTE_DOCUMENTACAO:
        return f'<span class="status status-alert">{obj.parecer}</span>'
    elif obj.parecer == 'Indeferido':
        return f'<span class="status status-error">{obj.parecer}</span>'
    return f'<span class="status status-alert">{obj.parecer}</span>'


def get_situacao(obj):
    if obj.situacao == PENDENTE_ASSINATURA:
        return f'<span class="status status-alert">{obj.situacao}</span>'
    return f'<span class="status status-success">{obj.situacao}</span>'


def get_observacoes(obj):
    texto = ''
    if obj.parecer == PENDENTE_DOCUMENTACAO:
        if obj.data_limite_envio_documentacao >= datetime.date.today():
            texto = f'O Serviço Social do seu Campus solicita que você anexe a seguinte documentação complementar: <strong>{obj.documentacao_pendente}</strong>. Caso não anexe a documentação solicitada até a data <strong>{format_(obj.data_limite_envio_documentacao)}</strong>, sua inscrição será invalidada. Qualquer dúvida contate o Serviço Social do seu Campus.<br><br>'
        else:
            texto = f'A documentação complementar: <strong>{obj.documentacao_pendente}</strong>, solicitada pelo Serviço Social, <strong>não foi enviada</strong>. A data limite para o envio era <strong>{format_(obj.data_limite_envio_documentacao)}</strong>.<br><br>'
    if InscricaoAluno.objects.filter(aluno=obj.aluno).exists():
        inscricao_aluno = InscricaoAluno.objects.filter(aluno=obj.aluno)[0]
    if inscricao_aluno and not inscricao_aluno.banco:
        texto += '<strong>* Cadastre seus dados bancários</strong>. Atenção: O pagamento do auxílio só pode ser feito em conta bancária em nome do próprio estudante.<br><br>'
    if (
        obj.parecer == 'Deferido'
        and not obj.termo_compromisso_assinado
        and obj.edital.data_divulgacao
        and obj.edital.data_divulgacao < datetime.datetime.now()
    ):
        data_limite = obj.edital.data_divulgacao + relativedelta(days=+3)
        if obj.data_limite_assinatura_termo:
            data_limite = obj.data_limite_assinatura_termo
        if data_limite:
            texto += '* Você precisa <strong>assinar o termo de compromisso</strong> para ter seu auxílio validado. Prazo limite: <strong>{}</strong>'.format(
                data_limite.strftime('%d/%m/%Y')
            )

    if obj.get_tipo_auxilio() in ['MAT', 'DIS']:
        if (
            obj.parecer == 'Deferido'
            and obj.termo_compromisso_assinado_em
            and obj.edital.ativo
            and obj.situacao_prestacao_contas == InscricaoDispositivo.AGUARDANDO_DOCUMENTOS
            and obj.prestacao_contas_cadastrada_em
            and obj.pendencia_prestacao_contas
            and obj.prestacao_contas_atualizada_em < obj.pendencia_cadastrada_em
        ):
            texto += 'A Comissão de prestação de contas dos auxílios emergenciais do seu Campus solicita que você anexe a seguinte documentação: <strong>{}</strong>. Você deverá editar o documento da sua prestação de contas até a data <strong>{}</strong>, adicionando o documento solicitado pela Comissão.'.format(
                obj.pendencia_prestacao_contas, obj.data_limite_envio_prestacao_contas.strftime('%d/%m/%Y')
            )
        if (
            obj.parecer == 'Deferido'
            and obj.termo_compromisso_assinado_em
            and obj.edital.ativo
            and obj.situacao_prestacao_contas == InscricaoDispositivo.AGUARDANDO_DOCUMENTOS
            and obj.arquivo_gru
            and obj.prestacao_contas_atualizada_em
            and obj.arquivo_gru_cadastrado_em
            and obj.prestacao_contas_atualizada_em < obj.arquivo_gru_cadastrado_em
        ):
            texto += 'A Comissão de prestação de contas dos auxílios emergenciais do seu Campus <strong>adicionou GRU para pagamento</strong> na sua prestação de contas.'
    return mark_safe(texto)


def pode_encerrar(obj):
    return obj.parecer == 'Deferido' and obj.termo_compromisso_assinado_em and not obj.fim_auxilio


class TipoAuxilio(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', max_length=255)
    descricao = models.CharFieldPlus('Descrição', max_length=2000, null=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Auxílio'
        verbose_name_plural = 'Tipos de Auxílios'

    def __str__(self):
        return self.titulo

    def get_tipo_auxilio(self):
        if self.id == 1:
            return 'INT'
        elif self.id == 2:
            return 'DIS'
        elif self.id == 3:
            return 'MAT'
        elif self.id == 4:
            return 'CHP'
        return None


class Edital(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=5000)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', related_name='campus_periodoinscricao', on_delete=models.CASCADE)
    tipo_auxilio = models.ManyToManyFieldPlus(TipoAuxilio, verbose_name='Tipos de Auxílio')
    data_inicio = models.DateTimeFieldPlus('Data de Início das Inscrições')
    data_termino = models.DateTimeFieldPlus('Data de Término das Inscrições')
    data_divulgacao = models.DateTimeFieldPlus('Data de Divulgação do Resultado', null=True)
    link_edital = models.CharFieldPlus('Link para o Edital', null=True, blank=True, max_length=1000)
    ativo = models.BooleanField('Ativo', default=True)
    impedir_fic = models.BooleanField('Impedir inscrição para alunos de cursos FIC', default=False)
    impedir_pos_graduacao = models.BooleanField('Impedir inscrição para alunos de cursos de pós-graduação', default=False)
    arquivo_instrucoes = models.PrivateFileField(
        verbose_name='Instruções Gerais', max_length=255, upload_to='auxilioemergencial/edital/documentos', null=True
    )

    class Meta:
        verbose_name = 'Edital Emergencial'
        verbose_name_plural = 'Editais Emergenciais'

    def __str__(self):
        return '{} ({})'.format(self.descricao, ', '.join([auxilio.titulo for auxilio in self.tipo_auxilio.all()]))

    def eh_ativo(self):
        return self.data_inicio <= datetime.datetime.now() and self.data_termino > datetime.datetime.now() and self.ativo


class InscricaoAluno(models.ModelPlus):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data_cadastro = models.DateTimeField('Data', auto_now_add=True)
    telefones_contato = models.CharFieldPlus('Telefones de Contato', max_length=500)
    emails_contato = models.CharFieldPlus('Emails de Contato', max_length=500)
    tem_matricula_outro_instituto = models.BooleanField('Possui matrícula em outra Instituição de Ensino?', default=False)
    foi_atendido_outro_instituto = models.BooleanField(
        'Foi atendido por algum auxílio emergencial de inclusão digital ou auxílio semelhante em outra Instituição de Ensino?', default=False
    )
    mora_com_pessoas_instituto = models.BooleanField('Você mora com outras pessoas que também estão matriculadas no IFRN?', default=False)
    pessoas_do_domicilio = models.CharFieldPlus('Informe o(s) nome(s) completo(s) do(s) estudante(s) que moram com você:', null=True, blank=True)
    banco = models.CharField('Banco', max_length=50, null=True)
    numero_agencia = models.CharField('Número da Agência', max_length=50, null=True, help_text='Ex: 3293-X')
    tipo_conta = models.CharField('Tipo da Conta', max_length=50, choices=TIPOCONTA_CHOICES, null=True)
    numero_conta = models.CharField('Número da Conta', max_length=50, null=True, help_text='Ex: 23384-6')
    operacao = models.CharField('Operação', max_length=50, null=True, blank=True)
    cpf = models.CharField(max_length=20, null=True, verbose_name='CPF', blank=False)
    renda_bruta_familiar = models.DecimalFieldPlus(
        null=True, verbose_name='Renda Bruta Familiar R$', help_text='Considerar a soma de todos os rendimentos mensais da família sem os descontos.'
    )
    renda_per_capita = models.DecimalFieldPlus('Renda per Capita', null=True, blank=True)
    valor_doacoes = models.DecimalFieldPlus('Valor que a família está recebendo de doações e/ou ajuda de terceiros (R$)', null=True, blank=True)

    class Meta:
        verbose_name = 'Inscrição do Aluno'
        verbose_name_plural = 'Inscrições do Aluno'

    def __str__(self):
        return 'Inscrição do Aluno'

    def tem_dados_bancarios(self):
        tem = self.banco and self.numero_agencia and self.numero_conta and self.tipo_conta
        return bool(tem)

    def get_dados_bancarios(self):
        texto = ''
        if self.banco:
            texto += f'Banco: {self.banco}'
        if self.numero_agencia:
            texto += f' Agência: {self.numero_agencia}'
        if self.numero_conta:
            texto += f' Conta: {self.numero_conta}'
        if self.tipo_conta:
            texto += f' Tipo da Conta: {self.numero_conta}'
        if self.operacao:
            texto += f' Operação: {self.operacao}'
        if self.cpf:
            texto += f' CPF: {self.cpf}'
        return texto


class IntegranteFamiliar(models.ModelPlus):
    inscricao = models.ForeignKeyPlus(InscricaoAluno, verbose_name='Inscrição', on_delete=models.CASCADE, null=True)
    nome = models.CharFieldPlus('1. Nome')
    data_nascimento = models.DateFieldPlus('2. Data de Nascimento', null=True)
    idade = models.IntegerField('Idade', null=True)
    parentesco = models.CharFieldPlus('3. Relação com o Aluno')
    estado_civil = models.ForeignKeyPlus('ae.EstadoCivil', verbose_name='4. Estado Civil')
    situacao_trabalho = models.ForeignKeyPlus('ae.SituacaoTrabalho', verbose_name='5. Ocupação')
    remuneracao = models.DecimalFieldPlus('6. Renda Bruta* Mensal', null=True)
    ultima_remuneracao = models.DecimalFieldPlus('Última Remuneração', null=True)
    data = models.DateTimeField('Data', auto_now=True, null=True)

    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE, null=True)
    id_inscricao = models.CharFieldPlus('Id da Inscrição', max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Integrante Familiar'
        verbose_name_plural = 'Integrantes Familiares'

    def __str__(self):
        return self.nome

    def save(self, *args, **kargs):
        if self.inscricao:
            self.aluno = self.inscricao.aluno
            self.id_inscricao = self.inscricao.id
        super().save(*args, **kargs)

    def get_integrantes(self):
        idade = ''
        if self.data_nascimento:
            idade = relativedelta(datetime.datetime.now().date(), self.data_nascimento)
            idade = idade.years
        elif self.idade:
            idade = self.idade
        if self.remuneracao:
            valor_remuneracao = self.remuneracao
        else:
            valor_remuneracao = self.ultima_remuneracao
        return '{}, {} anos, {}, {}, {}, remuneração de R$ {}'.format(
            self.nome, idade, self.parentesco, self.estado_civil, self.situacao_trabalho, format_(valor_remuneracao or '0,00')
        )


class InscricaoInternet(models.ModelPlus):
    SITUACAO_INTERNET_CHOICES = (
        (
            'NÃO possuo conexão própria à internet, dependo de redes de terceiros para me conectar.',
            'NÃO possuo conexão própria à internet, dependo de redes de terceiros para me conectar.',
        ),
        (
            'Possuo conexão própria com a internet, mas meu acesso é limitado, instável, ou de baixa capacidade, preciso de outra rede melhor para acesso rápido.',
            'Possuo conexão própria com a internet, mas meu acesso é limitado, instável, ou de baixa capacidade, preciso de outra rede melhor para acesso rápido.',
        ),
        (
            'Possuo conexão própria com a internet e adequada para o acompanhamento das aulas e atividades remotas.',
            'Possuo conexão própria com a internet e adequada para o acompanhamento das aulas e atividades remotas.',
        ),
    )

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data_cadastro = models.DateTimeField('Data da Inscrição', auto_now_add=True)
    ultima_atualizacao = models.DateTimeField('Última Atualização', null=True)

    situacao_acesso_internet = models.CharFieldPlus(
        'Quanto a minha situação de acesso à internet necessário as aulas remotas, declaro que', choices=SITUACAO_INTERNET_CHOICES, max_length=1000
    )
    justificativa_solicitacao = models.CharFieldPlus('Justificativa para Solicitação', max_length=5000)
    valor_solicitacao = models.DecimalFieldPlus('Valor da Solicitação de Auxílio (Valor Máximo: R$ 100,00)', decimal_places=2, max_digits=6)

    situacao = models.CharFieldPlus('Situação', max_length=100, choices=SITUACAO_CHOICES, default=PENDENTE_ASSINATURA)
    assinado_pelo_responsavel = models.BooleanField('Assinado pelo Responsável', default=False)
    assinado_pelo_responsavel_em = models.DateTimeFieldPlus('Assinado pelo Responsável em', null=True)

    parecer = models.CharFieldPlus('Parecer', max_length=100, choices=PARECER_CHOICES, default=SEM_PARECER)
    data_parecer = models.DateTimeField('Data do Parecer', null=True)
    autor_parecer = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Autor do Parecer',
        related_name='autor_parecer_auxiliointernet',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    valor_concedido = models.DecimalFieldPlus('Valor Concedido', decimal_places=2, max_digits=6, null=True)
    documentacao_pendente = models.CharFieldPlus('Indique qual documentação esse estudante deve anexar', max_length=2000, null=True)
    data_limite_envio_documentacao = models.DateFieldPlus('Indique a data limite para que o estudante anexe essa documentação', null=True)

    termo_compromisso_assinado = models.BooleanField('Termo de Compromisso Assinado', default=False)
    termo_compromisso_assinado_em = models.DateTimeFieldPlus('Termo de Compromisso Assinado em', null=True)
    fim_auxilio = models.DateTimeFieldPlus('Fim do Auxílio', null=True)
    documentacao_atualizada_em = models.DateTimeFieldPlus('Documentação Atualizada em', null=True)
    data_limite_assinatura_termo = models.DateTimeFieldPlus('Data Limite para Assinar Termo de Compromisso')

    class Meta:
        verbose_name = 'Inscrição para Auxílio de Serviço de Internet'
        verbose_name_plural = 'Inscrições para Auxílio de Serviço de Internet'

    def __str__(self):
        return 'Inscrição de Auxílio de Serviço de Internet'

    def get_situacao(self):
        return get_situacao(self)

    def get_tipo_auxilio(self):
        return 'INT'

    def get_nome_admin(obj):
        return 'inscricaointernet'

    def get_parecer(self):
        return get_parecer(self)

    def pendente_assinatura(self):
        return self.situacao == PENDENTE_ASSINATURA

    def pode_atualizar_documentacao(self):
        return pode_atualizar_documentacao(self)

    def get_observacoes(self):
        return get_observacoes(self)

    def pode_assinar_termo(self):
        return pode_assinar_termo(self)

    def tem_dados_bancarios(self):
        return tem_dados_bancarios(self)

    def get_inscricao_aluno(self):
        return get_inscricao_aluno(self)

    def pode_encerrar(self):
        return pode_encerrar(self)


class InscricaoDispositivo(models.ModelPlus):
    SITUACAO_EQUIPAMENTO_CHOICES = (
        ('NÃO possuo equipamentos (tablet ou computador).', 'NÃO possuo equipamentos (tablet ou computador).'),
        (
            'Possuo equipamento (tablet ou computador), mas com configuração inferior às descritas como básicas neste Edital.',
            'Possuo equipamento (tablet ou computador), mas com configuração inferior às descritas como básicas neste Edital.',
        ),
        (
            'Na minha residência existe um equipamento (tablet ou computador) com as configurações básicas descritas neste Edital, mas é compartilhado ou pertence a outro membro da família.',
            'Na minha residência existe um equipamento (tablet ou computador) com as configurações básicas descritas neste Edital, mas é compartilhado ou pertence a outro membro da família.',
        ),
        (
            'Possuo equipamento (tablet ou computador) com configurações básicas adequadas conforme descritas neste Edital ou de capacidade superior.',
            'Possuo equipamento (tablet ou computador) com configurações básicas adequadas conforme descritas neste Edital ou de capacidade superior.',
        ),
    )
    NAO_INFORMADO = 'Não Informado'
    AGUARDANDO_DOCUMENTOS = 'Aguardando documentos'
    PENDENTE_VALIDACAO = 'Pendente de validação'
    CONCLUIDA = 'Concluída'
    SITUACAO_PRESTACAO_CHOICES = (
        (AGUARDANDO_DOCUMENTOS, AGUARDANDO_DOCUMENTOS),
        (PENDENTE_VALIDACAO, PENDENTE_VALIDACAO),
        (CONCLUIDA, CONCLUIDA),
    )

    SITUACAO_PRESTACAO_CHOICES_FORM = (
        ('', '-----------------'),
        (AGUARDANDO_DOCUMENTOS, AGUARDANDO_DOCUMENTOS),
        (PENDENTE_VALIDACAO, PENDENTE_VALIDACAO),
        (CONCLUIDA, CONCLUIDA),
    )

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data_cadastro = models.DateTimeField('Data da Inscrição', auto_now_add=True)
    ultima_atualizacao = models.DateTimeField('Última Atualização', null=True)
    situacao_equipamento = models.CharFieldPlus('Declaro quanto ao equipamento que', choices=SITUACAO_EQUIPAMENTO_CHOICES, max_length=1000)
    justificativa_solicitacao = models.CharFieldPlus('Justificativa para Solicitação', max_length=5000)
    valor_solicitacao = models.DecimalFieldPlus('Valor da Solicitação de Auxílio (Valor Máximo: R$ 1.500,00)', decimal_places=2, max_digits=6)
    situacao = models.CharFieldPlus('Situação', max_length=100, choices=SITUACAO_CHOICES, default=PENDENTE_ASSINATURA)
    assinado_pelo_responsavel = models.BooleanField('Assinado pelo Responsável', default=False)
    assinado_pelo_responsavel_em = models.DateTimeFieldPlus('Assinado pelo Responsável em', null=True)
    parecer = models.CharFieldPlus('Parecer', max_length=100, choices=PARECER_CHOICES, default=SEM_PARECER)
    data_parecer = models.DateTimeField('Data do Parecer', null=True)
    autor_parecer = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Autor do Parecer',
        related_name='autor_parecer_auxiliodispositivo',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    valor_concedido = models.DecimalFieldPlus('Valor Concedido', decimal_places=2, max_digits=6, null=True)
    documentacao_pendente = models.CharFieldPlus('Indique qual documentação esse estudante deve anexar', max_length=2000, null=True)
    data_limite_envio_documentacao = models.DateFieldPlus('Indique a data limite para que o estudante anexe essa documentação', null=True)

    termo_compromisso_assinado = models.BooleanField('Termo de Compromisso Assinado', default=False)
    termo_compromisso_assinado_em = models.DateTimeFieldPlus('Termo de Compromisso Assinado em', null=True)
    fim_auxilio = models.DateTimeFieldPlus('Fim do Auxílio', null=True)
    documentacao_atualizada_em = models.DateTimeFieldPlus('Documentação Atualizada em', null=True)
    data_limite_assinatura_termo = models.DateTimeFieldPlus('Data Limite para Assinar Termo de Compromisso')
    arquivo_prestacao_contas = models.PrivateFileField(
        verbose_name='Prestação de Contas', max_length=255, upload_to='auxilioemergencial/inscricao/documentos', null=True
    )
    prestacao_contas_cadastrada_em = models.DateTimeFieldPlus('Prestação de contas cadastrada em', null=True)
    prestacao_contas_cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Prestação de Contas cadastrada por',
        related_name='prestacaocontas_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    prestacao_contas_atualizada_em = models.DateTimeFieldPlus('Prestação de contas atualizada em', null=True)
    prestacao_contas_atualizada_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Prestação de Contas atualizada por',
        related_name='prestacaocontas_atualizada_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    situacao_prestacao_contas = models.CharFieldPlus('Situação da Prestação de Contas', choices=SITUACAO_PRESTACAO_CHOICES, default=NAO_INFORMADO)
    arquivo_gru = models.PrivateFileField(verbose_name='Arquivo GRU', max_length=255, upload_to='auxilioemergencial/inscricao/documentos', null=True)
    arquivo_gru_cadastrado_em = models.DateTimeFieldPlus('Arquivo GRU cadastrado em', null=True)
    arquivo_gru_cadastrado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Arquivo GRU cadastrado por', related_name='arquivogru_por', null=True, blank=True, on_delete=models.CASCADE
    )
    comprovante_gru = models.PrivateFileField(
        verbose_name='Comprovante GRU', max_length=255, upload_to='auxilioemergencial/inscricao/documentos', null=True
    )
    comprovante_gru_cadastrado_em = models.DateTimeFieldPlus('Comprovante GRU cadastrado em', null=True)
    comprovante_gru_cadastrado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Comprovante GRU cadastrado por',
        related_name='comprovantegru_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    pendencia_prestacao_contas = models.CharFieldPlus('Indique qual documentação esse estudante deve anexar', max_length=2000, null=True)
    data_limite_envio_prestacao_contas = models.DateFieldPlus('Indique a data limite para que o estudante anexe essa documentação', null=True)
    pendencia_cadastrada_em = models.DateTimeFieldPlus('Prestação de contas cadastrada em', null=True)
    pendencia_cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Pendências cadastrada por', related_name='pendencias_por', null=True, blank=True, on_delete=models.CASCADE
    )

    prestacao_concluida_em = models.DateTimeFieldPlus('Prestação de contas concluída em', null=True)
    prestacao_concluida_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Prestação concluída por',
        related_name='prestacao_concluida_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = 'Inscrição de Auxílio para Aquisição de Dispositivo Eletrônico'
        verbose_name_plural = 'Inscrições de Auxílio para Aquisição de Dispositivo Eletrônico'
        permissions = (('pode_adicionar_prestacao_contas', 'Pode Adicionar Prestação de Contas'),)

    def __str__(self):
        return 'Inscrição de Auxílio para Aquisição de Dispositivo Eletrônico'

    def get_situacao(self):
        return get_situacao(self)

    def get_tipo_auxilio(self):
        return 'DIS'

    def get_nome_admin(obj):
        return 'inscricaodispositivo'

    def get_parecer(self):
        return get_parecer(self)

    def pendente_assinatura(self):
        return self.situacao == PENDENTE_ASSINATURA

    def pode_atualizar_documentacao(self):
        return pode_atualizar_documentacao(self)

    def get_observacoes(self):
        return get_observacoes(self)

    def pode_assinar_termo(self):
        return pode_assinar_termo(self)

    def tem_dados_bancarios(self):
        return tem_dados_bancarios(self)

    def get_inscricao_aluno(self):
        return get_inscricao_aluno(self)

    def pode_encerrar(self):
        return pode_encerrar(self)

    def pode_cadastrar_prestacao_contas(self):
        return pode_cadastrar_prestacao_contas(self)

    def get_situacao_prestacao_contas(self):
        return get_situacao_prestacao_contas(self)

    def get_inscricoes_anteriores(self):
        return get_inscricoes_anteriores(self)


class InscricaoMaterialPedagogico(models.ModelPlus):
    AGUARDANDO_DOCUMENTOS = 'Aguardando documentos'
    PENDENTE_VALIDACAO = 'Pendente de validação'
    CONCLUIDA = 'Concluída'
    NAO_INFORMADO = 'Não Informado'
    SITUACAO_PRESTACAO_CHOICES = (
        (AGUARDANDO_DOCUMENTOS, AGUARDANDO_DOCUMENTOS),
        (PENDENTE_VALIDACAO, PENDENTE_VALIDACAO),
        (CONCLUIDA, CONCLUIDA),
    )

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data_cadastro = models.DateTimeField('Data da Inscrição', auto_now_add=True)
    ultima_atualizacao = models.DateTimeField('Última Atualização', null=True)
    descricao_material = models.CharFieldPlus('Material didático pedagógico que deseja solicitar', max_length=2000)
    especificacao_material = models.CharFieldPlus('Especificações do material didático pedagógico solicitado', max_length=2000)
    valor_solicitacao = models.DecimalFieldPlus('Valor da Solicitação de Auxílio (Valor Máximo: R$ 400,00)', decimal_places=2, max_digits=6)
    justificativa_solicitacao = models.CharFieldPlus('Justificativa para Solicitação', max_length=5000)
    situacao = models.CharFieldPlus('Situação', max_length=100, choices=SITUACAO_CHOICES, default=PENDENTE_ASSINATURA)
    assinado_pelo_responsavel = models.BooleanField('Assinado pelo Responsável', default=False)
    assinado_pelo_responsavel_em = models.DateTimeFieldPlus('Assinado pelo Responsável em', null=True)
    parecer = models.CharFieldPlus('Parecer', max_length=100, choices=PARECER_CHOICES, default=SEM_PARECER)
    data_parecer = models.DateTimeField('Data do Parecer', null=True)
    autor_parecer = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Autor do Parecer',
        related_name='autor_parecer_auxiliodidatico',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    documentacao_pendente = models.CharFieldPlus('Indique qual documentação esse estudante deve anexar', max_length=2000, null=True)
    data_limite_envio_documentacao = models.DateFieldPlus('Indique a data limite para que o estudante anexe essa documentação', null=True)
    valor_concedido = models.DecimalFieldPlus('Valor Concedido', decimal_places=2, max_digits=6, null=True)

    termo_compromisso_assinado = models.BooleanField('Termo de Compromisso Assinado', default=False)
    termo_compromisso_assinado_em = models.DateTimeFieldPlus('Termo de Compromisso Assinado em', null=True)
    fim_auxilio = models.DateTimeFieldPlus('Fim do Auxílio', null=True)
    documentacao_atualizada_em = models.DateTimeFieldPlus('Documentação Atualizada em', null=True)
    data_limite_assinatura_termo = models.DateTimeFieldPlus('Data Limite para Assinar Termo de Compromisso')
    arquivo_prestacao_contas = models.PrivateFileField(
        verbose_name='Prestação de Contas', max_length=255, upload_to='auxilioemergencial/inscricao/documentos', null=True
    )
    prestacao_contas_cadastrada_em = models.DateTimeFieldPlus('Prestação de contas cadastrada em', null=True)
    prestacao_contas_cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Prestação de Contas cadastrada por',
        related_name='prestacaocontasmaterial_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    prestacao_contas_atualizada_em = models.DateTimeFieldPlus('Prestação de contas atualizada em', null=True)
    prestacao_contas_atualizada_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Prestação de Contas atualizada por',
        related_name='prestacaocontasmaterial_atualizada_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    situacao_prestacao_contas = models.CharFieldPlus('Situação da Prestação de Contas', choices=SITUACAO_PRESTACAO_CHOICES, default=NAO_INFORMADO)
    arquivo_gru = models.PrivateFileField(verbose_name='Arquivo GRU', max_length=255, upload_to='auxilioemergencial/inscricao/documentos', null=True)
    arquivo_gru_cadastrado_em = models.DateTimeFieldPlus('Arquivo GRU cadastrado em', null=True)
    arquivo_gru_cadastrado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Arquivo GRU cadastrado por',
        related_name='arquivogru_material_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    comprovante_gru = models.PrivateFileField(
        verbose_name='Comprovante GRU', max_length=255, upload_to='auxilioemergencial/inscricao/documentos', null=True
    )
    comprovante_gru_cadastrado_em = models.DateTimeFieldPlus('Comprovante GRU cadastrado em', null=True)
    comprovante_gru_cadastrado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Comprovante GRU cadastrado por',
        related_name='comprovantegru_material_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    pendencia_prestacao_contas = models.CharFieldPlus('Indique qual documentação esse estudante deve anexar', max_length=2000, null=True)
    data_limite_envio_prestacao_contas = models.DateFieldPlus('Indique a data limite para que o estudante anexe essa documentação', null=True)
    pendencia_cadastrada_em = models.DateTimeFieldPlus('Prestação de contas cadastrada em', null=True)
    pendencia_cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Pendências cadastrada por',
        related_name='pendencias_material_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    prestacao_concluida_em = models.DateTimeFieldPlus('Prestação de contas concluída em', null=True)
    prestacao_concluida_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Prestação concluída por',
        related_name='prestacaomaterial_concluida_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = 'Inscrição de Auxílio para Material Didático Pedagógico'
        verbose_name_plural = 'Inscrições de Auxílio para Material Didático Pedagógico'

    def __str__(self):
        return 'Inscrição de Auxílio para Material Didático Pedagógico'

    def get_situacao(self):
        return get_situacao(self)

    def get_tipo_auxilio(self):
        return 'MAT'

    def get_nome_admin(obj):
        return 'inscricaomaterialpedagogico'

    def get_parecer(self):
        return get_parecer(self)

    def pendente_assinatura(self):
        return self.situacao == PENDENTE_ASSINATURA

    def pode_atualizar_documentacao(self):
        return pode_atualizar_documentacao(self)

    def get_observacoes(self):
        return get_observacoes(self)

    def pode_assinar_termo(self):
        return pode_assinar_termo(self)

    def tem_dados_bancarios(self):
        return tem_dados_bancarios(self)

    def get_inscricao_aluno(self):
        return get_inscricao_aluno(self)

    def pode_encerrar(self):
        return pode_encerrar(self)

    def pode_cadastrar_prestacao_contas(self):
        return pode_cadastrar_prestacao_contas(self)

    def get_situacao_prestacao_contas(self):
        return get_situacao_prestacao_contas(self)

    def get_inscricoes_anteriores(self):
        return get_inscricoes_anteriores(self)


class InscricaoAlunoConectado(models.Model):
    SERVICO_INTERNET_CHOICES = (
        ('Sim', 'Sim'),
        ('Não', 'Não'),
        ('Não, compartilho a do(a) vizinho(a)', 'Não, compartilho a do(a) vizinho(a)'),
    )
    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data_cadastro = models.DateTimeField('Data da Inscrição', auto_now_add=True)
    ultima_atualizacao = models.DateTimeField('Última Atualização', null=True)

    casa_possui_servico_internet = models.CharFieldPlus(
        'Na casa que você mora possui algum serviço de internet wifi?', max_length=100, choices=SERVICO_INTERNET_CHOICES
    )
    foi_contemplado_servico_internet = models.BooleanField(
        'Você foi contemplado(a) com o auxílio emergencial para contratação de serviço de internet?', default=False
    )
    localidade_possui_cobertura = models.BooleanField('A localidade que você mora é coberta pelas operadoras Claro ou Oi?', default=False)
    justificativa_solicitacao = models.CharFieldPlus('Justificativa para Solicitação', max_length=5000)
    situacao = models.CharFieldPlus('Situação', max_length=100, choices=SITUACAO_CHOICES, default=PENDENTE_ASSINATURA)
    assinado_pelo_responsavel = models.BooleanField('Assinado pelo Responsável', default=False)
    assinado_pelo_responsavel_em = models.DateTimeFieldPlus('Assinado pelo Responsável em', null=True)
    parecer = models.CharFieldPlus('Parecer', max_length=100, choices=PARECER_CHOICES, default=SEM_PARECER)
    data_parecer = models.DateTimeField('Data do Parecer', null=True)
    autor_parecer = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Autor do Parecer', related_name='autor_parecer_alunoconectado', null=True, blank=True, on_delete=models.CASCADE
    )
    documentacao_pendente = models.CharFieldPlus('Indique qual documentação esse estudante deve anexar', max_length=2000, null=True)
    data_limite_envio_documentacao = models.DateFieldPlus('Indique a data limite para que o estudante anexe essa documentação', null=True)
    valor_concedido = models.DecimalFieldPlus('Valor Concedido', decimal_places=2, max_digits=6, null=True)

    termo_compromisso_assinado = models.BooleanField('Termo de Compromisso Assinado', default=False)
    termo_compromisso_assinado_em = models.DateTimeFieldPlus('Termo de Compromisso Assinado em', null=True)
    fim_auxilio = models.DateTimeFieldPlus('Fim do Auxílio', null=True)
    documentacao_atualizada_em = models.DateTimeFieldPlus('Documentação Atualizada em', null=True)
    data_limite_assinatura_termo = models.DateTimeFieldPlus('Data Limite para Assinar Termo de Compromisso')

    class Meta:
        verbose_name = 'Inscrição de Auxílio para o Projeto Alunos Conectados'
        verbose_name_plural = 'Inscrições de Auxílio para o Projeto Alunos Conectados'

    def __str__(self):
        return 'Inscrição de Auxílio para o Projeto Alunos Conectados'

    def get_situacao(self):
        return get_situacao(self)

    def get_tipo_auxilio(self):
        return 'CHP'

    def get_nome_admin(obj):
        return 'inscricaoalunoconectado'

    def get_parecer(self):
        return get_parecer(self)

    def pendente_assinatura(self):
        return self.situacao == PENDENTE_ASSINATURA

    def pode_atualizar_documentacao(self):
        return pode_atualizar_documentacao(self)

    def get_observacoes(obj):
        texto = ''
        if obj.parecer == PENDENTE_DOCUMENTACAO:
            if obj.data_limite_envio_documentacao >= datetime.date.today():
                texto = f'O Serviço Social do seu Campus solicita que você anexe a seguinte documentação complementar: <strong>{obj.documentacao_pendente}</strong>. Caso não anexe a documentação solicitada até a data <strong>{format_(obj.data_limite_envio_documentacao)}</strong>, sua inscrição será invalidada. Qualquer dúvida contate o Serviço Social do seu Campus.<br><br>'
            else:
                texto = f'A documentação complementar: <strong>{obj.documentacao_pendente}</strong>, solicitada pelo Serviço Social, <strong>não foi enviada</strong>. A data limite para o envio era <strong>{format_(obj.data_limite_envio_documentacao)}</strong>.<br><br>'
        return mark_safe(texto)

    def pode_assinar_termo(self):
        return pode_assinar_termo(self)

    def tem_dados_bancarios(self):
        return tem_dados_bancarios(self)

    def get_inscricao_aluno(self):
        return get_inscricao_aluno(self)

    def pode_encerrar(obj):
        return obj.parecer == 'Deferido' and not obj.fim_auxilio


class DocumentoAluno(models.Model):
    COMPROVANTE_RESIDENCIA = 'Comprovante de Residência'
    COMPROVANTE_RENDA = 'Comprovante de Renda'
    DOCUMENTACAO_COMPLEMENTAR = 'Documentação Complementar'
    PARECER = 'Parecer emitido pelo NAPNE e/ou ETEP'
    AUSENCIA_RENDA = 'Declaração de ausência de renda da família'
    TERMO_COMPROMISSO = 'Termo de Compromisso'

    TIPO_CHOICES = (
        (COMPROVANTE_RENDA, COMPROVANTE_RENDA),
        (COMPROVANTE_RESIDENCIA, COMPROVANTE_RESIDENCIA),
        (DOCUMENTACAO_COMPLEMENTAR, DOCUMENTACAO_COMPLEMENTAR),
        (PARECER, PARECER),
        (AUSENCIA_RENDA, AUSENCIA_RENDA),
        (TERMO_COMPROMISSO, TERMO_COMPROMISSO),
    )

    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', max_length=255, upload_to='auxilioemergencial/inscricao/documentos')
    data_cadastro = models.DateTimeField('Data', auto_now_add=True, null=True, blank=True)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável pela Cadastro', on_delete=models.CASCADE, null=True)
    integrante_familiar = models.ForeignKeyPlus(
        IntegranteFamiliar, verbose_name='Integrante Familiar', null=True, blank=True, on_delete=models.SET_NULL
    )
    tipo = models.CharFieldPlus('Tipo do Documento', max_length=50, null=True, choices=TIPO_CHOICES)

    class Meta:
        verbose_name = 'Documentos da Inscrição do Aluno'
        verbose_name_plural = 'Documentos das Inscrições dos Alunos'

    def __str__(self):
        return 'Documento do Aluno'
