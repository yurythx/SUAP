import datetime

from tinymce.models import HTMLField
from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.utils.safestring import mark_safe

from comum.utils import get_sigla_reitoria
from djtools.db import models
from djtools.db.models import Q
from djtools.utils import datas_entre, get_datetime_now, periodos_sucessivos
from rh.managers import SetorManager
from suap import nomenclatura

from ..carreira import Funcao, ServidorFuncaoHistorico
from .area_vinculacao import AreaVinculacao
from .setor_jornada_historico import SetorJornadaHistorico
from .tipo_uo import TipoUnidadeOrganizacional
from .uo import UnidadeOrganizacional

_SETOR_TREE_STAMP_KEY = 'rh:setor_tree_stamp'


class Setor(models.ModelPlus):
    SEARCH_FIELDS = ['sigla', 'codigo', 'nome', 'codigo_siorg']
    PUBLIC_SEARCH = True
    AUTOCOMPLETE_MIN_CHARS = 2

    _SETOR_MAP: dict = {}  # pk → Setor (select_related uo); aquecido uma vez, invalidado no save
    _CHILDREN: dict = {}  # pk → [child_pk, ...]; derivado de _SETOR_MAP
    _RAIZ_SUAP: Setor | None = None  # raiz SUAP em cache; invalidado no save
    _LOCAL_STAMP: int | None = None  # stamp do Redis quando o mapa foi construído

    codigo = models.CharField(
        'Código SIAPE',
        max_length=9,
        unique=True,
        null=True,
        blank=True,
        help_text='Caso o setor tenha este campo em branco será considerado setor SUAP',
    )
    uo = models.ForeignKeyPlus(
        'rh.UnidadeOrganizacional',
        null=True,
        blank=True,
        editable=False,
        on_delete=models.CASCADE,
        related_name='setor_set',
        verbose_name=nomenclatura.campus,
        db_column='uo_id',
    )
    superior = models.ForeignKeyPlus('self', null=True, blank=True, verbose_name='Setor Superior', on_delete=models.CASCADE)
    sigla = models.CharField(max_length=15)
    nome = models.CharField(max_length=100)
    excluido = models.BooleanField(
        verbose_name='Excluído', default=False, help_text='Setores excluídos não farão parte das buscas e não devem possuir servidores'
    )
    setores_compartilhados = models.ManyToManyField('self')
    codigo_siorg = models.CharField(max_length=10, blank=True, verbose_name='Código SIORG')

    areas_vinculacao = models.ManyToManyFieldPlus(AreaVinculacao, verbose_name='Áreas de Vinculação', blank=True)
    equivalencia_codigo = models.CharField(
        'Código de Equivalência',
        max_length=9,
        unique=True,
        null=True,
        blank=True,
        help_text='Código do setor SIAPE que é equivalente a este setor SUAP.',
    )

    objects = SetorManager()
    # objects = SetoresSuapAtivosManager()
    # todos = SetorManager()
    # suap = SetoresSuapManager()
    # siape = SetoresSiapeManager()

    data_criacao = models.DateFieldPlus(verbose_name='Data de Criação', null=True, blank=True)
    horario_funcionamento = models.TextField(verbose_name='Horário de Funcionamento', null=True, blank=True)
    bases_legais_internas = HTMLField(verbose_name='Bases Legais Internas', null=True, blank=True)
    bases_legais_externas = HTMLField(verbose_name='Bases Legais Externas', null=True, blank=True)

    if 'documento_eletronico' in settings.INSTALLED_APPS:
        portaria_criacao = models.ForeignKeyPlus(
            'documento_eletronico.DocumentoTexto', verbose_name='Portaria ou documento legal de criação', null=True, on_delete=models.SET_NULL
        )
    email = models.EmailField(verbose_name='E-mail', null=True, blank=True)

    class Meta:
        db_table = 'setor'
        ordering = ['sigla']
        verbose_name = 'Setor'
        verbose_name_plural = 'Setores'

        # Definindo o manager principal. É esse manager que será usado, por default, em todas as consultas do Django,
        # como por exemplo nas rotinas de dump e em fields de ModelForms. Essa definição é muito mais prática e segura
        # do que a abordagem do Django de usar o primeiro manager definido na classe.
        # Observar migration do RH - 0104_auto_20190123_1947.py.
        # https://docs.djangoproject.com/pt-br/2.1/topics/db/managers/#default-managers
        # default_manager_name = "todos"
        # FIXME: essa definição de um manager default=objects quebrou o manager de setores SIAPE utilizado no histórico de função do servidor, pois o admin carregava apenas setores suap ativos como instâncias válidas, não sendo possível salvar uma instância de setor SIAPE.

        permissions = (
            ('pode_gerenciar_setor_telefone', 'Pode gerenciar telefones de setores'),
            ('pode_gerenciar_setor_jornada_historico', 'Pode gerenciar carga horária de setores'),
        )

    def save(self, *args, **kwargs):
        """
        O método foi sobrescrito para preencher automaticamente o campo ``uo``.
        O critério para definir um setor SUAP é ter o campo codigo nulo. Porém, codigo
        é tipo texto e o Django preenche o codigo com uma string vazia quando um
        superusuario edita setores SUAP
        """
        self.uo = self._get_uo()
        if not self.codigo:
            self.codigo = None
        Setor._invalidate_tree_cache()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        Setor._invalidate_tree_cache()
        super().delete(*args, **kwargs)

    @classmethod
    def _invalidate_tree_cache(cls) -> None:
        """Limpa o mapa de processo e notifica outros workers via Redis."""
        cls._SETOR_MAP = {}
        cls._CHILDREN = {}
        cls._RAIZ_SUAP = None
        cls._LOCAL_STAMP = None
        cls._bump_tree_stamp()

    @classmethod
    def _bump_tree_stamp(cls) -> None:
        """Incrementa o stamp global no Redis para sinalizar mudança de hierarquia."""
        try:
            cache.incr(_SETOR_TREE_STAMP_KEY)
        except ValueError:
            cache.set(_SETOR_TREE_STAMP_KEY, 1, timeout=None)

    @classmethod
    def _get_remote_stamp(cls) -> int:
        """Lê o stamp global com cache local de 0,5 s para evitar round-trips excessivos."""
        stamp = cache.get(_SETOR_TREE_STAMP_KEY, local_ttl=30)
        return stamp if stamp is not None else 0

    def __str__(self):
        return self.sigla

    def get_absolute_url(self):
        return f'/rh/setor/{self.pk:d}/'

    def get_ext_combo_template(self):
        return self.get_caminho_as_html()

    @property
    def eh_siape(self):
        return bool(self.codigo)

    @property
    def eh_suap(self):
        return not self.eh_siape

    @classmethod
    def get_setores_por_profundidade(cls, raiz_por_ultimo=True) -> list[Setor]:
        """
        Retorna uma lista com todos os setores, ordenados por profundidade.
        Caso raiz_por_ultimo seja True, o setor raiz (profundidade 0) será o
        último da lista. Caso contrário, será o primeiro.

        Esta abordagem otimizada busca todos os setores de uma vez e calcula
        a profundidade em memória para evitar o problema de N+1 queries.
        """
        # 1. Busca todos os setores em uma única consulta
        todos_setores = list(cls.objects.suap_ativos().select_related('superior'))

        # 2. Cria um mapa de ID -> objeto para acesso rápido aos pais
        setores_map = {setor.id: setor for setor in todos_setores}

        # 3. Dicionário para cachear os resultados de profundidade (memoization)
        cache_profundidade = {}

        def calcular_profundidade(setor):
            # Se a profundidade já foi calculada, retorna do cache
            if setor.id in cache_profundidade:
                return cache_profundidade[setor.id]

            # Condição de parada: se não há superior, a profundidade é 0 (raiz)
            if not setor.superior_id:
                cache_profundidade[setor.id] = 0
                return 0

            # Pega o objeto do pai a partir do mapa (sem nova consulta DB)
            pai = setores_map.get(setor.superior_id)
            if not pai:  # Segurança para dados inconsistentes
                return 0

            # A profundidade é 1 + a profundidade do pai (recursão)
            profundidade = 1 + calcular_profundidade(pai)
            cache_profundidade[setor.id] = profundidade
            return profundidade

        # 4. Calcula e anexa a profundidade a cada objeto da lista
        for setor in todos_setores:
            setor.profundidade = calcular_profundidade(setor)

        # 5. Ordena a lista de objetos pela profundidade calculada, do maior para o menor
        lista_ordenada = sorted(todos_setores, key=lambda s: s.profundidade, reverse=raiz_por_ultimo)

        return lista_ordenada

    @classmethod
    def raiz_suap(cls) -> Setor:
        """Retorna o setor raiz ativo no SUAP (in-memory via _SETOR_MAP)."""
        Setor._ensure_map()
        if cls._RAIZ_SUAP is not None:
            return cls._RAIZ_SUAP

        cls._RAIZ_SUAP = cls.objects.suap_ativos().get(
            sigla=get_sigla_reitoria()
        )  # Garante que o setor raiz SUAP existe e é único, levantando exceção caso contrário
        return cls._RAIZ_SUAP

    def _get_uo(self):
        """
        Irá buscar o valor do campo ``uo`` recursivamente da hierarquia de
        setores. O retorno desta função deve ser igual ao valor do campo ``uo``.
        """
        setor_atual = self
        while setor_atual is not None:
            resultado = UnidadeOrganizacional.objects.filter(setor_id=setor_atual.pk or 0)
            if resultado:
                return resultado[0]
            setor_atual = setor_atual.superior
        return None

    @classmethod
    def _build_setor_map(cls) -> None:
        """Carrega todos os setores em ``_SETOR_MAP`` e ``_CHILDREN`` com uma única query.

        ``_SETOR_MAP`` mapeia pk → Setor (``select_related('uo')``).
        ``_CHILDREN`` mapeia pk → lista de pks dos filhos diretos.
        O cache é invalidado em ``save()`` quando a hierarquia muda.
        """
        setor_map = {}
        children: dict[int, list[int]] = {}
        for s in cls.objects.select_related('uo').all():
            setor_map[s.pk] = s
            if s.superior_id is not None:
                children.setdefault(s.superior_id, []).append(s.pk)
        cls._SETOR_MAP = setor_map
        cls._CHILDREN = children

    @classmethod
    def _ensure_map(cls) -> None:
        remote_stamp = cls._get_remote_stamp()
        if remote_stamp != cls._LOCAL_STAMP:
            cls._build_setor_map()
            cls._LOCAL_STAMP = remote_stamp

    @property
    def filhos(self) -> list[Setor]:
        Setor._ensure_map()
        return [Setor._SETOR_MAP[pk] for pk in Setor._CHILDREN.get(self.pk, []) if pk in Setor._SETOR_MAP]

    @property
    def descendentes(self) -> list[Setor]:
        """Retorna o setor e todos os seus descendentes usando BFS em memória.

        Returns:
            list[Setor]: O próprio setor seguido de todos os seus descendentes.
        """
        Setor._ensure_map()
        result: list[Setor] = []
        stack = [self.pk]
        while stack:
            pk = stack.pop()
            s = Setor._SETOR_MAP.get(pk)
            if s is not None:
                result.append(s)
                stack.extend(Setor._CHILDREN.get(pk, []))
        return result

    @classmethod
    def ids_subarvore(cls, ids_raizes) -> list[int]:
        """Retorna os ids de toda a subárvore a partir de ``ids_raizes``.

        Usa ``_CHILDREN`` em memória para evitar queries repetidas ao banco.

        Args:
            ids_raizes: Iterável de ids que definem as raízes da subárvore.

        Returns:
            list[int]: Ids das raízes e de todos os seus descendentes;
            lista vazia quando ``ids_raizes`` é vazio.
        """
        ids = list(ids_raizes)
        if not ids:
            return []
        cls._ensure_map()
        result: set[int] = set()
        stack = list(ids)
        while stack:
            pk = stack.pop()
            if pk not in result:
                result.add(pk)
                stack.extend(cls._CHILDREN.get(pk, []))
        return list(result)

    @property
    def ids_descendentes(self) -> list[int]:
        """Retorna os ids do setor e de todos os seus descendentes.

        Returns:
            list[int]: ids da subárvore enraizada em ``self``.
        """
        return [s.id for s in self.descendentes]

    def get_codigo_siorg(self):
        if self.codigo_siorg:
            return self.codigo_siorg
        setor = self.superior
        while setor is not None:
            if setor.codigo_siorg:
                return setor.codigo_siorg
            setor = setor.superior
        return None

    # ---------------------------------------------------------------------
    # Lista de Servidores do Setor
    # ---------------------------------------------------------------------
    def get_servidores(self, recursivo=True):
        from ..carreira import Servidor

        if recursivo:
            return Servidor.objects.ativos().filter(setor__in=self.descendentes)
        else:
            return Servidor.objects.ativos().filter(setor=self)

    def qtd_servidores(self, recursivo=False):
        from ..carreira import Servidor

        if recursivo:
            return Servidor.objects.ativos_permanentes().filter(setor__in=self.descendentes).count()
        else:
            return Servidor.objects.ativos_permanentes().filter(setor=self).count()

    def get_servidores_por_periodo(self, data_inicial=None, data_final=None, recursivo=True):
        from ..carreira import ServidorSetorHistorico

        if (data_inicial is None) and (data_final is None):
            #
            # returna a lista atual de servidores baseado no atributo 'setor' de 'Servidor'
            #
            return self.get_servidores(recursivo)
        else:
            if data_inicial is None:
                #
                # foi passado um período com apenas a data final informada
                #
                return []
            else:
                #
                # nesse ponto, temos um período com data inicial e data final informados
                # seleciona os servidores que estavam no setor (OU descendentes) no período informado
                #
                setores = [self]
                if recursivo:
                    setores += self.descendentes

                if not data_final:
                    data_final = datetime.date.today()
                #
                # selecionar os servidores envolvidos via históricos de setor
                #

                qs_1 = ServidorSetorHistorico.objects.filter(
                    setor__in=setores, data_inicio_no_setor__lte=data_final, data_fim_no_setor__gte=data_inicial
                )  # inicio fora e termino dentro do período (incluindo extremidades)

                qs_2 = ServidorSetorHistorico.objects.filter(setor__in=setores, data_inicio_no_setor__lte=data_final, data_fim_no_setor__isnull=True)

                historicos_setor = (
                    (qs_1 | qs_2)
                    .exclude(servidor__data_fim_servico_na_instituicao__lt=data_inicial)
                    .distinct()
                    .order_by('servidor__pessoa_fisica__nome')
                )

                servidores = []
                for historico_setor in historicos_setor:
                    if historico_setor.servidor not in servidores:
                        servidores.append(historico_setor.servidor)

                return servidores

    def get_vinculos(self, recursivo=True):
        from comum.models import Vinculo

        if recursivo:
            return Vinculo.objects.filter(setor__in=self.descendentes)
        else:
            return Vinculo.objects.filter(setor=self)

    def get_funcionarios(self, recursivo=True):
        from comum.models import Vinculo

        if recursivo:
            return Vinculo.objects.funcionarios().filter(setor__in=self.descendentes)
        else:
            return Vinculo.objects.funcionarios().filter(setor=self)

    @property
    def setor_eh_campus(self):
        return hasattr(self, 'unidadeorganizacional')

    @property
    def eh_orgao_colegiado(self):
        tipo_orgao = TipoUnidadeOrganizacional.objects.filter(descricao='Conselhos e Órgãos Colegiados').first()
        if self.setor_eh_campus:
            return self.unidadeorganizacional.tipo == tipo_orgao
        return False

    def get_caminho(self, ordem_descendente=True) -> list[Setor]:
        """Retorna a hierarquia de setores desde a raiz até o setor atual.

        Percorre a árvore de setores usando ``_SETOR_MAP`` em memória.

        Args:
            ordem_descendente: Quando ``True``, retorna do raiz para o setor;
                caso contrário, do setor para a raiz.

        Returns:
            list[Setor]: Lista ordenada de setores no caminho hierárquico.
        """
        Setor._ensure_map()
        caminho: list[Setor] = []
        pk = self.pk
        while pk is not None:
            s = Setor._SETOR_MAP.get(pk)
            if s is None:
                break
            caminho.append(s)
            pk = s.superior_id
        return list(reversed(caminho)) if ordem_descendente else caminho

    def get_caminho_setor(self, setor):
        """
        Retorna a lista de setores que fazem a hierarquia do setor desde o setor informado
        """
        caminho = [self]
        if self != setor and self.id in self.ids_descendentes:
            setor_atual = self.superior
            while setor_atual != setor:
                caminho.append(setor_atual)
                setor_atual = setor_atual.superior
            caminho.append(setor_atual)
        caminho.reverse()
        return caminho

    def get_caminho_as_html(self):
        """Retorna o caminho hierárquico do setor como HTML renderizável.

        Destaca visualmente setores que possuem ``UnidadeOrganizacional``
        vinculada.

        Returns:
            SafeString: String HTML segura com o caminho formatado.
        """
        caminho = self.get_caminho()
        caminho_html = []
        for s in caminho:
            eh_uo = s.uo_id is not None and s.uo.setor_id == s.pk
            if eh_uo:
                s_repr = f'<span class="admin-setor-uo" title="{s.nome}">{s}</span>'
            elif s == caminho[-1]:
                s_repr = f'<span class="admin-setor" title="{s.nome}">{s} ({s.nome})</span>'
            else:
                s_repr = f'<span title="{s.nome}">{s}</span>'
            caminho_html.append(s_repr)
        return mark_safe(' &rarr; '.join(caminho_html))

    def pode_gerar_carteira_funcional(self):
        """
        Define se podem ser geradas carteiras funcionais do setor.
        """
        from ..carreira import Servidor

        servidores = Servidor.objects.filter(setor=self)
        setor_pode_gerar = True
        for servidor in servidores:
            if not servidor.pode_gerar_carteira_funcional():
                setor_pode_gerar = False
                break
        return setor_pode_gerar

    @classmethod
    def get_setores_vazios(cls):
        """
        Deve retornar queryset de setores que não tem ninguém. Cada setorX desse
        queryset deve satisfazer as 3 condições:
        - Ninguém lotado no setorX (FK setor do funcionario)
        - Ninguém onde setorX é um dos setores adicionais
        - Ninguém de algum setor que tenha o setorX compartilhado.
        Resumindo, é o setor que ninguém é responsável por receber processos.
        """
        setores = (
            Setor.objects.suap_ativos()
            .filter(setores_servidor__isnull=True, setores_prestadorservico__isnull=True)
            .exclude(
                vinculos_setor_adicional__isnull=False
            )  # ponytail: setores_adicionais migrados p/ Vinculo (era pessoa__setores_adicionais__id=F('id'))
            .exclude(setores_compartilhados=F('id'))
            .exclude(compartilhamentosetorpessoa__setor_dono__id=F('id'))
            .exclude(compartilhamentoprocessoeletronicopoderchefe_setor_dono_set__setor_dono__id=F('id'))
        )
        return setores

    @property
    def chefes(self):
        """Retorna os servidores com função do setor"""
        from ..carreira import Servidor

        hoje = get_datetime_now().date()
        # Subquery para obter IDs dos servidores com função de chefia no setor
        chefes_ids = (
            ServidorFuncaoHistorico.objects.filter(
                setor_suap=self,
                funcao__codigo__in=Funcao.get_codigos_funcao_chefia(),
            )
            .filter(Q(data_fim_funcao__gte=hoje) | Q(data_fim_funcao__isnull=True))
            .values_list('servidor_id', flat=True)
        )

        # Filtrar apenas servidores ativos com os IDs obtidos
        return Servidor.objects.filter(ativo=True, id__in=chefes_ids)

    def obter_chefes_hieraquicamente(self):
        """Retorna os servidores com função do setor, buscando no setor superior se necessário"""
        from ..carreira import Servidor

        chefes_do_setor = self.chefes
        if chefes_do_setor.exists():
            return chefes_do_setor
        return self.superior.obter_chefes_hieraquicamente() if self.superior else Servidor.objects.none()

    def historico_funcao(self, data_inicial=None, data_final=None):
        """histórico de funções exercidas no Setor em um período
        procura a interseção entre período informado e os períodos das funções
        """
        hoje = get_datetime_now().date()

        if not data_inicial:
            data_inicial = hoje
        if not data_final:
            data_final = hoje

        # data de inicio da funcao dentro do período informado
        historico_funcao = ServidorFuncaoHistorico.objects.filter(
            data_inicio_funcao__gte=data_inicial,
            data_inicio_funcao__lte=data_final,
        )

        # data de inicio da funcao antes do período informado e data fim da função depois da data inicio do período
        historico_funcao = historico_funcao | ServidorFuncaoHistorico.objects.filter(
            data_inicio_funcao__lt=data_inicial,
            data_fim_funcao__gte=data_inicial,
        )

        # data de inicio da funcao antes do período informado e sem data fim
        historico_funcao = historico_funcao | ServidorFuncaoHistorico.objects.filter(
            data_inicio_funcao__lt=data_inicial,
            data_fim_funcao__isnull=True,
        )

        # data de fim da funcao deve está dentro do período informado
        historico_funcao = historico_funcao | ServidorFuncaoHistorico.objects.filter(
            data_fim_funcao__gte=data_final,
            data_fim_funcao__lte=data_final,
        )

        historico_funcao = historico_funcao.filter(setor_suap=self, funcao__codigo__in=Funcao.get_codigos_funcao_chefia())

        return historico_funcao.distinct()

    @staticmethod
    def historico_funcao_setores(setores: list, data_inicio: datetime.date | None = None, data_fim: datetime.date | None = None):
        """histórico de funções exercidas nos setores em um período
        procura a interseção entre período informado e os períodos das funções
        """
        data_inicio_periodo = data_inicio or datetime.date.today()
        data_fim_periodo = data_fim or datetime.date.today()

        # data de inicio da funcao dentro do período informado
        historico_funcao = ServidorFuncaoHistorico.objects.filter(
            data_inicio_funcao__gte=data_inicio_periodo,
            data_inicio_funcao__lte=data_fim_periodo,
        )

        # data de inicio da funcao antes do período informado e data fim da função depois da data inicio do período
        historico_funcao = historico_funcao | ServidorFuncaoHistorico.objects.filter(
            data_inicio_funcao__lt=data_inicio_periodo,
            data_fim_funcao__gte=data_inicio_periodo,
        )

        # data de inicio da funcao antes do período informado e sem data fim
        historico_funcao = historico_funcao | ServidorFuncaoHistorico.objects.filter(
            data_inicio_funcao__lt=data_inicio_periodo,
            data_fim_funcao__isnull=True,
        )

        # data de fim da funcao deve está dentro do período informado
        historico_funcao = historico_funcao | ServidorFuncaoHistorico.objects.filter(
            data_fim_funcao__gte=data_fim_periodo,
            data_fim_funcao__lte=data_fim_periodo,
        )

        historico_funcao = historico_funcao.filter(
            setor_suap__in=setores, funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), servidor__ativo=True
        )

        return historico_funcao.distinct()

    def get_funcoes_no_periodo(self, data_inicio: datetime.date, data_fim: datetime.date | None = None) -> dict:
        funcoes_historico_por_dia: dict[datetime.date, list[ServidorFuncaoHistorico]] = {}

        data_fim_periodo = data_fim or datetime.date.today()

        historico_funcao = self.historico_funcao(data_inicio, data_fim)

        for historico in historico_funcao.distinct():
            for dia in datas_entre(historico.data_inicio_funcao, historico.data_fim_funcao or data_fim_periodo):
                if data_inicio <= dia <= data_fim_periodo:
                    if dia not in funcoes_historico_por_dia:
                        funcoes_historico_por_dia[dia] = []
                    funcoes_historico_por_dia[dia].append(historico)  # pode ser que haja mais de uma função ao mesmo tempo no setor

        return funcoes_historico_por_dia

    @staticmethod
    def get_funcoes_no_periodo_setores(setores: list, data_inicio: datetime.date, data_fim: datetime.date | None = None) -> dict:
        funcoes_historico_por_dia: dict[datetime.date, list[ServidorFuncaoHistorico]] = {}

        data_fim_periodo = data_fim or datetime.date.today()

        historico_funcao = Setor.historico_funcao_setores(setores, data_inicio, data_fim)

        for historico in historico_funcao.distinct():
            for dia in datas_entre(historico.data_inicio_funcao, historico.data_fim_funcao or data_fim_periodo):
                if data_inicio <= dia <= data_fim_periodo:
                    if dia not in funcoes_historico_por_dia:
                        funcoes_historico_por_dia[dia] = []
                    funcoes_historico_por_dia[dia].append(historico)  # pode ser que haja mais de uma função ao mesmo tempo nos setores

        return funcoes_historico_por_dia

    # jornada de trabalho do setor em uma determinada data
    def jornada_trabalho_por_periodo_dict(self, data_inicio, data_fim):
        qs_1 = SetorJornadaHistorico.objects.filter(setor=self, data_inicio_da_jornada__lte=data_fim, data_fim_da_jornada__gte=data_inicio)
        qs_2 = SetorJornadaHistorico.objects.filter(setor=self, data_inicio_da_jornada__lte=data_fim, data_fim_da_jornada__isnull=True)
        qs = (qs_1 | qs_2).distinct()
        jornadas = {}
        for jornada_historico in qs:
            data_inicio_jornada = jornada_historico.data_inicio_da_jornada
            data_fim_jornada = jornada_historico.data_fim_da_jornada
            if data_inicio_jornada <= data_inicio:
                data_inicio_jornada = data_inicio
            if not data_fim_jornada or data_fim_jornada >= data_fim:
                data_fim_jornada = data_fim
            for dia in datas_entre(data_inicio_jornada, data_fim_jornada):
                jornadas[dia] = jornada_historico.jornada_trabalho

        return jornadas

    def get_jornadas_setor_por_data(self, data=None):
        if data is None:
            data = datetime.date.today()

        qs_1 = SetorJornadaHistorico.objects.filter(setor=self, data_inicio_da_jornada__lte=data, data_fim_da_jornada__gte=data)
        qs_2 = SetorJornadaHistorico.objects.filter(setor=self, data_inicio_da_jornada__lte=data, data_fim_da_jornada__isnull=True)
        return (qs_1 | qs_2).distinct()

    def get_jornada_trabalho(self, data=None):
        qs = self.get_jornadas_setor_por_data(data)
        return qs.first()

    def jornada_trabalho(self, data=None):
        jornada = self.get_jornada_trabalho(data)
        return jornada.jornada_trabalho if jornada else None

    def tipo_jornada_trabalho_por_data(self, data=None):
        jornada = self.jornada_trabalho(data)
        return 'Flexibilizada' if jornada and jornada.nome == '30 HORAS SEMANAIS' else 'Padrão'

    # mensagens referentes a situação dos períodos cadastrados para o setor
    def jornada_trabalho_pendencias(self):
        periodos = []
        for periodo in SetorJornadaHistorico.objects.filter(setor=self).order_by('data_inicio_da_jornada'):
            periodos.append((periodo.data_inicio_da_jornada, periodo.data_fim_da_jornada))

        if periodos:
            #
            # se a data final do último período for nula, usa a data de 'hoje' de modo a processar períodos "fechados"
            #
            ultimo_periodo = periodos[-1:][0]
            data_inicial = ultimo_periodo[0]
            data_final = ultimo_periodo[1]
            if not data_final:
                periodos.pop()  # remove o último período
                if data_inicial < datetime.date.today():
                    periodos.append((data_inicial, datetime.date.today()))  # adiciona o último período com data final igual a hoje
                else:
                    periodos.append((data_inicial, data_inicial))  # último período com data inicial ainda no futuro

            periodos_mensagens_pendencias = periodos_sucessivos(periodos)
            mensagens_periodos = periodos_mensagens_pendencias[1]
        else:
            mensagens_periodos = ('Sem histórico de jornada de trabalho.',)

        return mensagens_periodos

    def salvar_areas_vinculacao_recursivamente(self, areas_vinculacao):
        for setor_filho in self.filhos:
            setor_filho.areas_vinculacao.clear()
            for area_vinculacao in areas_vinculacao:
                setor_filho.areas_vinculacao.add(area_vinculacao)
            setor_filho.salvar_areas_vinculacao_recursivamente(areas_vinculacao)

    def telefones(self, sem_ramal=False):
        out = []
        for st in self.setortelefone_set.all():
            valor = st
            if sem_ramal:
                valor = st.numero
            out.append(f'{valor}')
        if out:
            return ', '.join(out)
        return ''
