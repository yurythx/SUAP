from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import ProgrammingError
from django.db.models import Exists, OuterRef

from djtools.db import models

from .servidor import Servidor

# No SIAPE o código do cargo é uma chave composta: os 3 primeiros dígitos são o código do
# grupo de cargo emprego e os 3 últimos, o código do cargo dentro do grupo. O importador
# depende dessa composição em dois pontos (ver rh/importador.py):
#   - importar_cargo_emprego: deriva o grupo de codigo[:3];
#   - importar_servidor1....: resolve o cargo do servidor concatenando os dois códigos do arquivo.
# Cargos cadastrados manualmente que NÃO existem no SIAPE usam código local não numérico,
# garantindo colisão zero com o espaço de códigos do SIAPE (100% numérico).
TAMANHO_CODIGO_GRUPO_SIAPE = 3
TAMANHO_CODIGO_CARGO_SIAPE = 6


class GrupoCargoEmprego(models.ModelPlus):
    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    sigla = models.CharField(max_length=10)
    categoria = models.CharField(
        max_length=30,
        null=True,
        choices=[['docente', 'Docente'], ['tecnico_administrativo', 'Técnico-Administrativo']],
        default='tecnico_administrativo',
    )
    excluido = models.BooleanField(default=False)

    class Meta:
        db_table = 'grupo_cargo_emprego'
        verbose_name = 'Grupo de Cargo Emprego'
        verbose_name_plural = 'Grupos de Cargo Emprego'

    def __str__(self) -> str:
        return self.nome


class CargoEmpregoUtilizadosManager(models.Manager):
    def get_queryset(self):
        try:
            servidores_existentes = Servidor.objects.filter(cargo_emprego=OuterRef('pk'))
            return super().get_queryset().filter(Exists(servidores_existentes))
        except ProgrammingError:
            return super().get_queryset()


class CargoEmprego(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome', 'nome_amigavel']

    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    nome_amigavel = models.CharField('Nome amigável', max_length=40, blank=True, null=False)
    descricao_sumaria = models.TextField(verbose_name='Descrição Sumária do Cargo', blank=True)
    grupo_cargo_emprego = models.ForeignKeyPlus(GrupoCargoEmprego, on_delete=models.CASCADE)
    sigla_escolaridade = models.CharField(max_length=2)
    excluido = models.BooleanField(default=False)
    cargo_suap = models.BooleanField('Cargo SUAP', default=False, help_text='Esse cargo pode ser gerenciado dentro do SUAP?')
    cargo_siape = models.BooleanField(
        'Cargo SIAPE', default=True, help_text='Esse cargo já foi confirmado por uma extração da tabela de cargos do SIAPE?'
    )

    # Managers
    objects = models.Manager()
    utilizados = CargoEmpregoUtilizadosManager()

    class Meta:
        db_table = 'cargo_emprego'
        ordering = ['nome']
        verbose_name = 'Cargo Emprego'
        verbose_name_plural = 'Cargos de Emprego'

    def __str__(self) -> str:
        return f'{self.nome} ({self.grupo_cargo_emprego.sigla}) - {self.codigo}'

    @property
    def eh_codigo_siape(self) -> bool:
        """Indica se o código ocupa o espaço de códigos do SIAPE (numérico)."""
        return bool(self.codigo) and self.codigo.isdigit()

    def clean(self) -> None:
        """Garante a coerência do código com o contrato do SIAPE.

        Duas formas de código são aceitas:
        - numérico: precisa ter exatamente 6 dígitos e os 3 primeiros precisam ser o código
          do grupo, senão o importador não consegue resolver o cargo do servidor;
        - local (contém caractere não numérico): usado por cargos que não existem no SIAPE.
          Nunca colide com o espaço do SIAPE e, por isso, nunca é resolvido pelo importador.

        Raises:
            ValidationError: quando o código está vazio, tem formato inválido, tem prefixo
                divergente do grupo ou é local em um cargo marcado como confirmado pelo SIAPE.
        """
        super().clean()
        self.codigo = (self.codigo or '').strip().upper()

        if not self.cargo_suap and not self._state.adding:
            # Registro sob o contrato do importador: o código é dele, não do formulário.
            # Sem esta saída, um cargo legado com código fora do padrão travaria qualquer
            # edição no admin — inclusive de um campo exclusivo do SUAP, como nome_amigavel —
            # e como `codigo` fica readonly nesses registros, o erro nem viraria mensagem de
            # campo: o ModelForm levantaria ValueError por não achar o campo no formulário.
            return

        if not self.codigo:
            raise ValidationError({'codigo': 'Informe o código do cargo.'})

        if not self.eh_codigo_siape:
            if self.cargo_siape:
                raise ValidationError(
                    {'codigo': 'Cargos confirmados pelo SIAPE precisam de código numérico. Desmarque "Cargo SIAPE" ou informe o código do SIAPE.'}
                )
            return

        if len(self.codigo) != TAMANHO_CODIGO_CARGO_SIAPE:
            raise ValidationError(
                {'codigo': f'O código do SIAPE tem {TAMANHO_CODIGO_CARGO_SIAPE} dígitos (3 do grupo + 3 do cargo). Informado: {len(self.codigo)}.'}
            )

        try:
            grupo = self.grupo_cargo_emprego
        except ObjectDoesNotExist:
            # grupo não informado: o próprio campo já acusa o erro de obrigatoriedade
            return

        codigo_grupo = grupo.codigo or ''
        if self.codigo[:TAMANHO_CODIGO_GRUPO_SIAPE] != codigo_grupo:
            raise ValidationError(
                {
                    'codigo': (
                        f'Os {TAMANHO_CODIGO_GRUPO_SIAPE} primeiros dígitos precisam ser o código do grupo '
                        f'"{self.grupo_cargo_emprego}" ({codigo_grupo or "sem código"}).'
                    )
                }
            )


class CargoEmpregoArea(models.ModelPlus):
    SEARCH_FIELDS = ['descricao', 'cargo_emprego__nome']

    cargo_emprego = models.ForeignKeyPlus(CargoEmprego, on_delete=models.CASCADE)
    descricao = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Área do Cargo Emprego'
        verbose_name_plural = 'Áreas dos Cargos de Emprego'

    def __str__(self) -> str:
        return f'{self.cargo_emprego.nome} - {self.descricao}'


def cargo_cadastrado_para_pendencia() -> Exists:
    """Subquery que indica se já existe cargo com o código da pendência.

    Exposta no módulo para o admin anotar a listagem com ela e não pagar uma consulta
    por linha.

    Returns:
        A expressão `Exists` correlacionada pelo campo `codigo`.
    """
    return Exists(CargoEmprego.objects.filter(codigo=OuterRef('codigo')))


class CargoEmpregoPendenteQuery(models.QuerySet):
    def resolvidas(self) -> CargoEmpregoPendenteQuery:
        return self.filter(cargo_cadastrado_para_pendencia())

    def nao_resolvidas(self) -> CargoEmpregoPendenteQuery:
        return self.exclude(cargo_cadastrado_para_pendencia())


class CargoEmpregoPendente(models.ModelPlus):
    """Código de cargo que veio no arquivo de servidores do SIAPE sem cargo correspondente no SUAP.

    Registrado pelo importador sempre que a resolução do cargo do servidor falha. Serve para a
    Gestão de Pessoas saber exatamente qual código cadastrar: cadastrando o cargo com esse mesmo
    código, a extração seguinte religa os servidores automaticamente.

    A pendência não guarda estado de resolução: ela é considerada resolvida quando existe um
    CargoEmprego com o mesmo código, o que evita linha obsoleta.
    """

    SEARCH_FIELDS = ['codigo', 'grupo_codigo']

    codigo = models.CharFieldPlus('Código do Cargo no SIAPE', max_length=10, unique=True)
    grupo_codigo = models.CharFieldPlus('Código do Grupo no SIAPE', max_length=10)
    qtd_servidores = models.IntegerField('Servidores Afetados', default=0)
    primeira_ocorrencia = models.DateTimeFieldPlus('Primeira Ocorrência', auto_now_add=True)
    ultima_ocorrencia = models.DateTimeFieldPlus('Última Ocorrência', auto_now=True)

    objects = models.Manager.from_queryset(CargoEmpregoPendenteQuery)()

    class Meta:
        db_table = 'cargo_emprego_pendente'
        ordering = ['-ultima_ocorrencia', 'codigo']
        verbose_name = 'Cargo Emprego Pendente de Cadastro'
        verbose_name_plural = 'Cargos de Emprego Pendentes de Cadastro'

    def __str__(self) -> str:
        return f'{self.codigo} ({self.qtd_servidores} servidor(es))'

    @property
    def grupo_cargo_emprego(self) -> GrupoCargoEmprego | None:
        """Grupo correspondente ao prefixo do código, quando já existir no SUAP."""
        return GrupoCargoEmprego.objects.filter(codigo=self.grupo_codigo).first()

    @property
    def resolvida(self) -> bool:
        """Indica se o cargo já foi cadastrado no SUAP com esse código."""
        return CargoEmprego.objects.filter(codigo=self.codigo).exists()
