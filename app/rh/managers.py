from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from model_utils.managers import InheritanceManager

if TYPE_CHECKING:
    from rh.deduplicacao.entrada import Politica
    from rh.models import PessoaFisica


class UnidadeOrganizacionalQuery(models.QuerySet):
    """
    Exibe todas unidades organizacionais com código(SIAPE) e que estejam ativas
    """

    def siape(self):
        eh_setor_suap = settings.TIPO_ARVORE_SETORES == 'SUAP'
        return self.filter(setor__codigo__isnull=False, setor__excluido=False) if eh_setor_suap else self.filter(setor__excluido=False)

    """
        Quando a configuração de setores for SUAP:
        - Exibe as unidades organizacionais que não tem código vinculado e estão ativas
        Quando a configuração doas setores for SIAPE:
        - Exibe todas unidades organizacionais ativas
    """

    def suap(self):
        eh_setor_suap = settings.TIPO_ARVORE_SETORES == 'SUAP'
        return self.filter(setor__codigo__isnull=True, setor__excluido=False) if eh_setor_suap else self.filter(setor__excluido=False)

    """
        Exibe as Unidades Organizacionais ativas dos tipos EAD, Campus Produtivo e Campus não produtivos, ou seja, exclui
        Conselhos/Comissões e Reitoria
    """

    def campi(self):
        UnidadeOrganizacional = apps.get_model('rh', 'unidadeorganizacional')
        return self.suap().filter(
            tipo__in=[
                UnidadeOrganizacional.TIPO_CAMPUS_EAD,
                UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO,
                UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO,
            ]
        )

    """
        Exibe as Unidades Organizacionais ativas dos tipos EAD, Campus Produtivo, Campus não produtivos e Reitoria, ou
        seja, exclui Conselhos/Comissões
    """

    def uo(self):
        UnidadeOrganizacional = apps.get_model('rh', 'unidadeorganizacional')
        eh_setor_suap = settings.TIPO_ARVORE_SETORES == 'SUAP'
        choices_uo = [
            UnidadeOrganizacional.TIPO_CAMPUS_EAD,
            UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO,
            UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO,
            UnidadeOrganizacional.TIPO_REITORIA,
        ]
        return self.suap().filter(tipo__in=choices_uo) if eh_setor_suap else self.filter()


class UnidadeOrganizacionalManager(models.Manager):
    def siape(self):
        return self.get_queryset().siape()

    def suap(self):
        return self.get_queryset().suap()

    def campi(self):
        return self.get_queryset().campi()

    def uo(self):
        return self.get_queryset().uo()

    def get_queryset(self):
        return UnidadeOrganizacionalQuery(self.model, using=self._db).select_related('setor')


class SetorQuery(models.QuerySet):
    """
    Exibe todos os setores com código(SIAPE) e que estejam ativas
    """

    def siape(self):
        eh_setor_siape = settings.TIPO_ARVORE_SETORES == 'SIAPE'
        return self.filter() if eh_setor_siape else self.filter(codigo__isnull=False)

    """
        Quando a configuração de setores for SUAP:
        - Exibe os setores que não tem código vinculado e estão ativas
        Quando a configuração doas setores for SIAPE:
        - Exibe todos setores ativas
    """

    def suap(self):
        eh_setor_siape = settings.TIPO_ARVORE_SETORES == 'SIAPE'
        return self.filter() if eh_setor_siape else self.filter(codigo__isnull=True)

    def suap_ativos(self):
        return self.suap().filter(excluido=False)

    def ativos(self):
        return self.filter(excluido=False)


class SetorManager(models.Manager):
    def siape(self):
        return self.get_queryset().siape()

    def suap(self):
        return self.get_queryset().suap()

    def suap_ativos(self):
        return self.get_queryset().suap_ativos()

    def ativos(self):
        return self.get_queryset().ativos()

    def get_queryset(self):
        return SetorQuery(self.model, using=self._db)


class PessoaQueryset(models.QuerySet):
    def servidores(self):
        return self.pessoas_fisicas().filter(pessoafisica__eh_servidor=True)

    def prestadores(self):
        return self.pessoas_fisicas().filter(pessoafisica__eh_prestador=True)

    def alunos(self):
        return self.pessoas_fisicas().filter(pessoafisica__eh_aluno=True)

    def com_usuario(self):
        return self.pessoas_fisicas().filter(vinculo__user__isnull=False)

    def pessoas_fisicas(self):
        return self.filter(pessoafisica__isnull=False)

    def pessoas_juridicas(self):
        return self.filter(pessoajuridica__isnull=False)


class PessoaManager(models.Manager):
    def get_queryset(self):
        return PessoaQueryset(self.model, using=self._db)

    def servidores(self):
        return self.get_queryset().servidores()

    def prestadores(self):
        return self.get_queryset().prestadores()

    def alunos(self):
        return self.get_queryset().alunos()

    def pessoas_fisicas(self):
        return self.get_queryset().pessoas_fisicas()

    def pessoas_com_usuario(self):
        return self.get_queryset().com_usuario()

    def pessoas_juridicas(self):
        return self.get_queryset().pessoas_juridicas()


class ServidorQueryset(models.QuerySet):
    def vinculados(self):
        return self.filter(ativo=True)

    def aposentados(self):
        from rh.models import Situacao

        return self.vinculados().filter(situacao__codigo=Situacao.APOSENTADOS)

    def ativos(self):
        from rh.models import Situacao

        return self.vinculados().filter(situacao__codigo__in=Situacao.SITUACOES_ATIVOS)

    def inativos(self):
        from rh.models import Situacao

        return self.vinculados().exclude(situacao__codigo__in=Situacao.SITUACOES_ATIVOS)

    def ativos_permanentes(self):
        from rh.models import Situacao

        return self.vinculados().filter(situacao__codigo=Situacao.ATIVO_PERMANENTE)

    def cedidos(self):
        from rh.models import Situacao

        return self.vinculados().filter(situacao__codigo=Situacao.ATIVO_EM_OUTRO_ORGAO)

    def efetivos(self):
        from rh.models import Situacao

        return self.vinculados().filter(situacao__codigo__in=Situacao.SITUACOES_EFETIVOS)

    def em_exercicio(self):
        from rh.models import Situacao

        return self.vinculados().filter(situacao__codigo__in=Situacao.SITUACOES_EM_EXERCICIO_NO_INSTITUTO)

    def estagiarios(self):
        from rh.models import Situacao

        return self.vinculados().filter(situacao__codigo__in=Situacao.situacoes_siape_estagiarios())

    def tecnicos_administrativos(self):
        return self.vinculados().filter(eh_tecnico_administrativo=True)

    def docentes(self):
        return self.vinculados().filter(eh_docente=True)

    def substitutos(self):
        from rh.models import Situacao

        return self.docentes().filter(situacao__codigo=Situacao.CONT_PROF_SUBSTITUTO)

    def temporarios(self):
        from rh.models import Situacao

        return self.docentes().filter(situacao__codigo__in=Situacao.SITUACOES_TEMPORARIOS)

    def substitutos_ou_temporarios(self):
        from rh.models import Situacao

        return self.docentes().filter(situacao__codigo__in=Situacao.SITUACOES_SUBSTITUTOS_OU_TEMPORARIOS)

    def visitantes(self):
        from rh.models import Situacao

        return self.docentes().filter(situacao__codigo=Situacao.CONTR_PROF_VISITANTE)

    def docentes_permanentes(self):
        return self.docentes().ativos_permanentes()

    def docentes_cedidos(self):
        return self.docentes().cedidos()

    def sem_afastamento_hoje(self):
        hoje = datetime.date.today()
        ServidorAfastamento = apps.get_model('rh', 'servidorafastamento')
        return self.exclude(
            Q(servidorafastamento__data_inicio__lte=hoje)
            & Q(servidorafastamento__data_termino__gte=hoje)
            & Q(servidorafastamento__cancelado=False)
            & Q(
                servidorafastamento__afastamento_id__in=ServidorAfastamento.objects.exclude_afastamentos_pgd().values_list(
                    'afastamento_id', flat=True
                )
            )
        )

    def com_afastamento_hoje(self):
        hoje = datetime.date.today()
        ServidorAfastamento = apps.get_model('rh', 'servidorafastamento')
        return self.filter(
            Q(servidorafastamento__data_inicio__lte=hoje)
            & Q(servidorafastamento__data_termino__gte=hoje)
            & Q(servidorafastamento__cancelado=False)
            & Q(
                servidorafastamento__afastamento_id__in=ServidorAfastamento.objects.exclude_afastamentos_pgd().values_list(
                    'afastamento_id', flat=True
                )
            )
        )


class AreaConhecimentoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('superior')


class FuncaoQuery(models.QuerySet):
    def usadas(self):
        return self.filter(servidorfuncaohistorico__isnull=False).distinct()

    def ativos(self):
        return self.filter(excluido=False)

    def siape(self):
        return self.filter(funcao_suap=False)

    def suap(self):
        return self.filter(funcao_suap=True)


class FuncaoManager(models.Manager):
    def usadas(self):
        return self.get_queryset().usadas()

    def ativos(self):
        return self.get_queryset().ativos()

    def siape(self):
        return self.get_queryset().siape()

    def suap(self):
        return self.get_queryset().suap()

    def get_queryset(self):
        return FuncaoQuery(self.model, using=self._db)


class ServidorFuncaoHistoricoQueryset(models.QuerySet):
    def atuais(self):
        hoje = datetime.date.today()
        return self.filter(Q(data_inicio_funcao__lte=hoje), Q(data_fim_funcao__gte=hoje) | Q(data_fim_funcao__isnull=True))

    def substitutos(self):
        from rh.models import Funcao

        return self.filter(funcao__codigo=Funcao.get_sigla_substituicao_chefia())


class ServidorFuncaoHistoricoManager(models.Manager):
    def get_queryset(self):
        return ServidorFuncaoHistoricoQueryset(self.model, using=self._db)

    def atuais(self):
        return self.get_queryset().atuais()

    def substitutos(self):
        return self.get_queryset().substitutos()


class AvaliadorExternosManager(models.Manager):
    def get_queryset(self):
        from comum.models import Vinculo

        return super(self.__class__, self).get_queryset().filter(vinculo__tipo_relacionamento=ContentType.objects.get(Vinculo.PRESTADOR))


class AvaliadorInternosManager(models.Manager):
    def get_queryset(self):
        from comum.models import Vinculo

        return super(self.__class__, self).get_queryset().filter(vinculo__tipo_relacionamento=ContentType.objects.get(Vinculo.SERVIDOR))


class ServidorAfastamentoQueryset(models.QuerySet):
    def exclude_afastamentos_pgd(self):
        from comum.models import Configuracao

        afastamentos_pgd = Configuracao.get_valor_por_chave('rh', 'afastamentos_pgd')
        queryset = self.filter()
        if afastamentos_pgd:
            pks_afastamentos = [int(afastamento) for afastamento in afastamentos_pgd.split(',')]
            queryset = queryset.exclude(afastamento_id__in=pks_afastamentos)
        return queryset


class ServidorAfastamentoManager(models.Manager):
    def get_queryset(self):
        return ServidorAfastamentoQueryset(self.model, using=self._db)

    def exclude_afastamentos_pgd(self):
        return self.get_queryset().exclude_afastamentos_pgd()


class PessoaFisicaManager(InheritanceManager):
    def com_prioridade(self) -> models.QuerySet[PessoaFisica]:
        """Anota a prioridade de sobrevivência (servidor ativo > aluno ativo > prestador ativo > maior id)."""
        from django.db.models import BooleanField, Exists, OuterRef, Value

        from comum.models import PrestadorServico
        from rh.models import Servidor

        qs = self.get_queryset().annotate(
            servidor_ativo=Exists(Servidor.objects.filter(pessoa_fisica=OuterRef('pk'), ativo=True)),
            prestador_ativo=Exists(PrestadorServico.objects.filter(pessoa_fisica=OuterRef('pk'), ativo=True)),
        )
        if 'edu' not in settings.INSTALLED_APPS:
            return qs.annotate(aluno_ativo=Value(False, output_field=BooleanField()))
        from edu.models import Aluno

        return qs.annotate(aluno_ativo=Exists(Aluno.objects.filter(pessoa_fisica=OuterRef('pk'), situacao__ativo=True)))

    def obter_ou_criar(self, dados: Mapping[str, Any], politica: Politica) -> tuple[PessoaFisica, bool]:
        from rh.deduplicacao.entrada import obter_ou_criar

        return obter_ou_criar(dados, politica)
