from djtools.db import models


class EstruturaPNP(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome', 'uo__nome', 'uo__sigla']

    uo = models.OneToOneFieldPlus(
        'rh.UnidadeOrganizacional',
        verbose_name='Unidade Organizacional',
        null=True,
        blank=True,
        help_text='Fica em branco quando a unidade não pôde ser identificada pelo nome informado pela PNP.',
    )
    codigo = models.CharField(max_length=255, verbose_name='Código', unique=True)
    nome = models.CharField(max_length=255, verbose_name='Nome', default='', help_text='Nome da estrutura conforme informado pela PNP.')

    class Meta:
        verbose_name = 'Estrutura PNP'
        verbose_name_plural = 'Estruturas PNP'

    def __str__(self) -> str:
        return f'{self.codigo} - {self.nome}' if self.nome else self.codigo


class EixoPNP(models.ModelPlus):
    """Eixos e subeixos tecnológicos da PNP, que os exporta numa lista única.

    O nível está implícito no código (``19`` é eixo, ``1901`` é subeixo), mas a regra de
    formação é irregular na origem — ``261`` e ``81`` também são subeixos — então a
    hierarquia não é derivada aqui. O SUAP só tem cadastro para os eixos.
    """

    SEARCH_FIELDS = ['codigo', 'nome', 'eixo_tecnologico__descricao']

    eixo_tecnologico = models.OneToOneFieldPlus(
        'edu.EixoTecnologico',
        verbose_name='Eixo Tecnológico',
        null=True,
        blank=True,
        help_text='Fica em branco quando o eixo não pôde ser identificado pelo nome informado pela PNP, o que é o caso dos subeixos.',
    )
    codigo = models.CharField(max_length=255, verbose_name='Código', unique=True)
    nome = models.CharField(max_length=255, verbose_name='Nome', default='', help_text='Nome do eixo ou subeixo conforme informado pela PNP.')

    class Meta:
        verbose_name = 'Eixo PNP'
        verbose_name_plural = 'Eixos PNP'

    def __str__(self) -> str:
        return f'{self.codigo} - {self.nome}' if self.nome else self.codigo


class AreaTematicaPNP(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome', 'area__codigo', 'area__descricao']

    area = models.OneToOneFieldPlus(
        'rh.AreaConhecimento',
        verbose_name='Área do Conhecimento',
        null=True,
        blank=True,
        help_text='Fica em branco quando a área não pôde ser identificada pelo código informado pela PNP.',
    )
    codigo = models.CharField(max_length=255, verbose_name='Código', unique=True, help_text='Código da tabela do CNPq, no formato 1.03.00.00-7.')
    nome = models.CharField(max_length=255, verbose_name='Nome', default='', help_text='Nome da área conforme informado pela PNP.')

    class Meta:
        verbose_name = 'Área Temática PNP'
        verbose_name_plural = 'Áreas Temáticas PNP'

    def __str__(self) -> str:
        return f'{self.codigo} - {self.nome}' if self.nome else self.codigo


class MatriculaPNP(models.ModelPlus):
    SEARCH_FIELDS = ['matricula', 'nome', 'cpf', 'curso', 'aluno__matricula']

    aluno = models.OneToOneFieldPlus(
        'edu.Aluno',
        verbose_name='Aluno',
        null=True,
        blank=True,
        help_text='Fica em branco quando o aluno não pôde ser identificado pelo CPF, curso e unidade informados pela PNP.',
    )
    estrutura = models.ForeignKeyPlus(
        'pnp.EstruturaPNP',
        verbose_name='Estrutura PNP',
        null=True,
        blank=True,
        help_text='Fica em branco enquanto a estrutura do código informado pela PNP não tiver sido importada.',
    )
    matricula = models.CharField(max_length=30, verbose_name='Matrícula', unique=True, help_text='Matrícula da PNP, que não corresponde à do SUAP.')
    nome = models.CharField(max_length=255, verbose_name='Nome', default='', help_text='Nome do aluno conforme informado pela PNP.')
    cpf = models.CharField(max_length=14, verbose_name='CPF', default='')
    curso = models.CharField(max_length=255, verbose_name='Curso', default='', help_text='Nome do curso conforme informado pela PNP.')
    unidade = models.CharField(max_length=255, verbose_name='Unidade', default='', help_text='Nome da unidade conforme informado pela PNP.')
    codigo_estrutura = models.CharField(max_length=255, verbose_name='Código da Estrutura', default='')

    class Meta:
        verbose_name = 'Matrícula PNP'
        verbose_name_plural = 'Matrículas PNP'

    def __str__(self) -> str:
        return f'{self.matricula} - {self.nome}' if self.nome else self.matricula


class ServidorPNP(models.ModelPlus):
    SEARCH_FIELDS = ['matricula', 'nome', 'cpf', 'unidade', 'servidor__matricula']

    servidor = models.OneToOneFieldPlus(
        'rh.Servidor',
        verbose_name='Servidor',
        null=True,
        blank=True,
        help_text='Fica em branco quando o servidor não pôde ser identificado pela matrícula informada pela PNP.',
    )
    estrutura = models.ForeignKeyPlus(
        'pnp.EstruturaPNP',
        verbose_name='Estrutura PNP',
        null=True,
        blank=True,
        help_text='Fica em branco enquanto a estrutura do código informado pela PNP não tiver sido importada.',
    )
    matricula = models.CharField(
        max_length=30,
        verbose_name='Matrícula',
        unique=True,
        help_text='Matrícula SIAPE sem os zeros à esquerda, como o SUAP a registra.',
    )
    nome = models.CharField(max_length=255, verbose_name='Nome', default='', help_text='Nome do servidor conforme informado pela PNP.')
    cpf = models.CharField(max_length=14, verbose_name='CPF', default='')
    unidade = models.CharField(max_length=255, verbose_name='Unidade', default='', help_text='Nome da unidade conforme informado pela PNP.')
    codigo_estrutura = models.CharField(max_length=255, verbose_name='Código da Estrutura', default='')

    class Meta:
        verbose_name = 'Servidor PNP'
        verbose_name_plural = 'Servidores PNP'

    def __str__(self) -> str:
        return f'{self.matricula} - {self.nome}' if self.nome else self.matricula
