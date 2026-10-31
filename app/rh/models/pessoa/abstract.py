import re

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation

from comum.utils import get_setor, get_uo
from djtools.db import models


class AbstractRelacionamento(models.ModelPlus):
    matricula = models.CharFieldPlus('Matrícula', max_length=30, db_index=True, unique=True)
    pessoa_fisica = models.ForeignKeyPlus(
        'rh.PessoaFisica', db_index=True, null=False, blank=False, related_name='%(class)s_set', related_query_name='%(class)s_set', default=None
    )
    vinculos = GenericRelation(
        'comum.Vinculo', related_query_name='%(class)s_set', object_id_field='id_relacionamento', content_type_field='tipo_relacionamento'
    )
    setor = models.ForeignKeyPlus(
        'rh.Setor',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='setores_%(class)s',
        related_query_name='setores_%(class)s',
        verbose_name='Setor SUAP',
        help_text='Este setor poderá ser modificado manualmente pelos responsáveis pelo RH',
    )

    email_academico = models.EmailField('Email Acadêmico', blank=True)
    email_google_classroom = models.EmailField('Email do Google Classroom', blank=True)

    class Meta:
        abstract = True

    def get_vinculo(self):
        # self.vinculos.all() usa o cache de prefetch_related('vinculos') quando a queryset o traz,
        # evitando N+1 nas listagens que acessam as properties (email_pessoal/foto/raca/...).
        # A GenericRelation `vinculos` já é escopada por content_type+id_relacionamento e o
        # unique_together de Vinculo garante ≤1 vínculo por papel — daí o [0].
        vinculos = list(self.vinculos.all())
        return vinculos[0] if vinculos else None

    @property
    def email_notificacao(self) -> str:
        v = self.get_vinculo()
        return v.email_notificacao if v else ''

    @property
    def email_pessoal(self) -> str:
        v = self.get_vinculo()
        return v.email_pessoal if v else ''

    @property
    def raca(self):
        v = self.get_vinculo()
        return v.raca if v else None

    @property
    def povo_indigena(self):
        v = self.get_vinculo()
        return v.povo_indigena if v else None

    @property
    def deficiencia(self):
        v = self.get_vinculo()
        return v.deficiencia if v else None

    @property
    def sistema_origem(self):
        v = self.get_vinculo()
        return v.sistema_origem if v else ''

    @property
    def setores_adicionais(self):
        # ponytail: None-guard omitido — get_vinculo() sem vínculo cai no __getattr__
        # fallback p/ pessoa_fisica.setores_adicionais; tripwire explícito só no RemoveField (S1.4)
        return self.get_vinculo().setores_adicionais

    _DEFAULT_FOTO = '/static/comum/img/default.jpg'

    @property
    def foto(self):
        v = self.get_vinculo()
        return v.foto if v else None

    def get_foto_url(self) -> str:
        v = self.get_vinculo()
        return v.get_foto_url() if v else self._DEFAULT_FOTO

    def get_foto_75x100_url(self) -> str:
        v = self.get_vinculo()
        return v.get_foto_75x100_url() if v else self._DEFAULT_FOTO

    def get_foto_150x200_url(self) -> str:
        v = self.get_vinculo()
        return v.get_foto_150x200_url() if v else self._DEFAULT_FOTO

    def get_foto_url_publica(self, tamanho: str | None = None) -> str:
        v = self.get_vinculo()
        return v.get_foto_url_publica(tamanho) if v else f'{settings.SITE_URL}{self._DEFAULT_FOTO}'

    def get_foto_75x100_url_publica(self) -> str:
        return self.get_foto_url_publica('75x100')

    def get_foto_150x200_url_publica(self) -> str:
        return self.get_foto_url_publica('150x200')


class FuncionariosDoMeuSetorManager(models.Manager):
    def get_queryset(self):
        setor = get_setor()
        return super().get_queryset().filter(setor__id__in=setor.ids_descendentes)


class FuncionariosDoMeuCampusManager(models.Manager):
    def get_queryset(self):
        uo = get_uo()
        return super().get_queryset().filter(setor__uo=uo)


class AbstractFuncionario(AbstractRelacionamento):
    ativo = models.BooleanField(verbose_name='Ativo', default=True, help_text='Indica se o funcionário está ativo na instituição')
    setor_funcao = models.ForeignKeyPlus(
        'rh.Setor',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='setores_funcao_%(class)s',
        related_query_name='setores_funcao_%(class)s',
        verbose_name='Setor da Função SIAPE',
    )
    setor_lotacao = models.ForeignKeyPlus(
        'rh.Setor',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='setores_lotacao_%(class)s',
        related_query_name='setores_lotacao_%(class)s',
        verbose_name='Setor de Lotação SIAPE',
    )

    email_institucional = models.EmailField('E-mail Institucional', blank=True)

    do_meu_setor = FuncionariosDoMeuSetorManager()
    do_meu_campus = FuncionariosDoMeuCampusManager()

    class Meta:
        abstract = True

    def __getattr__(self, obj):
        if obj == 'pessoa_fisica' or obj.startswith('_'):
            return super().__getattribute__(obj)
        try:
            return super().__getattribute__(obj)
        except AttributeError:
            return getattr(self.pessoa_fisica, obj)

    def _get_search_fields_optimized_content_to_save(self):
        usernames = ''
        if self.pk:
            usernames = ''.join([item for item in self.vinculo_set.values_list('user__username', flat=True) if item])
        return '{}{}{}{}'.format(
            self.pessoa_fisica.nome or '',
            self.pessoa_fisica.cpf or '',
            usernames,
            re.sub(r'\D', '', str(self.pessoa_fisica.cpf)) or '',
        )

    @property
    def campus(self):
        return self.setor and self.setor.uo or None

    @property
    def username(self):
        return self.matricula

    # ok
    def eh_chefe_do_setor_hoje(self, setor):
        return False

    # ok
    def eh_chefe_de(self, funcionario) -> bool:
        if funcionario.setor and self.setor:
            return self.eh_chefe_do_setor_hoje(funcionario.setor)
        return False

    # ok
    def eh_do_meu_setor(self, funcionario, incluir_subsetores=True) -> bool:
        if incluir_subsetores:
            return funcionario.setor_id in self.setor.ids_descendentes
        else:
            return self.setor == funcionario.setor

    # ok
    def eh_do_meu_campus(self, funcionario) -> bool:
        if self.setor and funcionario.setor:
            return self.setor.uo_id == funcionario.setor.uo_id
        return False

    #
    # jornada de trabalho do funcionario em uma determinada data
    #
    # ok

    def jornada_trabalho_por_periodo_dict(self, setor, data_inicio, data_fim):
        return {}

    # ok
    def chefes_na_data(
        self,
        data,
        considerar_setor_no_qual_tem_funcao=False,
        chefes_setor_lotacao=False,
    ):
        from ..carreira import Funcao, Servidor, ServidorFuncaoHistorico
        from ..organizacao import Setor

        """
        Att: Há uma nova versão desse método: Servidor.get_chefes_no_periodo

        Chefe(s) do Funcionário em uma determinada data.
            - No escopo do Setor atual (default)
            - No escopo do Setor Superior em relação ao Setor no qual o funcionário está com funcão

        1) se sou o reitor, eu mando em mim
        2) não sou o reitor, então os chefes do meu setor são os meus chefes
            - se eu for um dos chefes
                - eu não posso mandar em mim
                - os demais chefes que são "substituição de chefia" também não podem mandar em mim
        3) ainda não há chefes? então, procura nos setores superiores recursivamente até achar (ou não!)
        """
        chefes_na_data = Servidor.objects.none()
        setores_na_data = []
        meu_setor = self.setor_na_data(data, chefes_setor_lotacao)
        if meu_setor:
            if settings.TIPO_ARVORE_SETORES == 'SUAP' and chefes_setor_lotacao:
                # verificando se existe a equivalência a nível de setor... se existir é só selecionar o setor suap diretamente
                setor_check_codigo = Setor.objects.suap().filter(equivalencia_codigo=meu_setor.codigo).first()
                if setor_check_codigo:
                    meu_setor = setor_check_codigo
                else:
                    # selecionando o setor suap equivalente ao setor siape de lotação
                    meu_setor_suap = Setor.objects.suap().filter(sigla=meu_setor).first()
                    # verificando se os setores são os mesmos pela equivalência da UO
                    if meu_setor_suap and meu_setor.uo.equivalente == meu_setor_suap.uo:
                        # a variável meu_setor passa a ser o setor suap de lotação
                        # essa troca é necessária, pois a chefia acontece nos setores suap
                        meu_setor = meu_setor_suap

            setores_na_data.append(meu_setor)

        if considerar_setor_no_qual_tem_funcao and hasattr(self, 'codigo_vaga'):
            minhas_funcoes_na_data = self.historico_funcao(data, data)
            for funcao in minhas_funcoes_na_data:
                if funcao.setor_suap:
                    setor_superior = funcao.setor_suap.superior
                    if setor_superior:
                        setores_na_data.append(setor_superior)

        if setores_na_data:
            sou_o_reitor = hasattr(self, 'codigo_vaga') and self.eh_reitor(data)

            if sou_o_reitor:
                chefes_na_data = Servidor.objects.filter(id=self.id)
            else:
                historico_funcao_do_setor = ServidorFuncaoHistorico.objects.none()

                for setor_na_data in setores_na_data:
                    historico_funcao_do_setor_atual = setor_na_data.historico_funcao(data, data)

                    sou_um_dos_chefes = historico_funcao_do_setor_atual.filter(servidor__id=self.id).exists()

                    if sou_um_dos_chefes:
                        # não posso me mandar !!!
                        historico_funcao_do_setor_atual = historico_funcao_do_setor_atual.exclude(servidor__id=self.id)

                        if historico_funcao_do_setor_atual.exists():
                            # retirar quem for "substituicao de chefia"
                            historico_funcao_do_setor_atual = historico_funcao_do_setor_atual.exclude(
                                funcao__codigo=Funcao.get_sigla_substituicao_chefia()
                            )

                    if not historico_funcao_do_setor_atual.exists():
                        # "sobe" na árvore dos setores
                        setor_superior = setor_na_data.superior
                        while setor_superior and not historico_funcao_do_setor_atual.exists():
                            historico_funcao_do_setor_atual = setor_superior.historico_funcao(data, data)
                            setor_superior = setor_superior.superior

                    historico_funcao_do_setor = historico_funcao_do_setor | historico_funcao_do_setor_atual

                if historico_funcao_do_setor.exists():
                    chefes_na_data = Servidor.objects.filter(id__in=historico_funcao_do_setor.values_list('servidor__id', flat=True))

        # filtrando os chefes que estão ativos
        chefes_na_data = chefes_na_data.filter(ativo=True)

        return chefes_na_data

    @property
    def telefones_institucionais(self):
        out = []
        for st in self.setor.setortelefone_set.all():
            out.append(f'{st}')
        return ', '.join(out)

    # ok
    def chefes_imediatos(self):
        from ..carreira import Servidor

        if self.setor:
            setor = self.setor

            if self.eh_chefe_do_setor_hoje(self.setor):
                if self.setor.superior:
                    setor = self.setor.superior

            while not setor.historico_funcao().exists() and setor.superior:
                setor = setor.superior

            return Servidor.objects.filter(pk__in=setor.historico_funcao().values_list('servidor_id', flat=True))
        return Servidor.objects.none()

    # ok
    def setor_na_data(self, data, chefes_setor_lotacao=False):
        return self.setor
