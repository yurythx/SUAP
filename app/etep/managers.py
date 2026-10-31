from django.conf import settings
from django.db import models

from comum.models import UsuarioGrupoSetor
from comum.utils import get_sigla_reitoria, tl
from rh.models import UnidadeOrganizacional


class FiltroUnidadeOrganizacionalQuerySet(models.QuerySet):
    def __init__(self, *args, **kwargs):
        self.key = kwargs.pop('key', None)
        super().__init__(*args, **kwargs)

    def get_filtered_queryset(self):
        eh_setor_suap = settings.TIPO_ARVORE_SETORES == 'SUAP'
        if not self.key:
            if eh_setor_suap:
                self = self.filter(setor__codigo__isnull=True)
            else:
                self = self.filter()
        ids = self.get_ids()
        if ids:
            if self.key:
                filtro = {f'{self.key}__id__in': ids}
            else:
                filtro = {'id__in': ids}
            self = self.filter(**filtro)
        return self

    def get_ids(self):
        user = tl.get_user()
        ids = [None]
        if user and not user.is_anonymous:
            if user.has_perm('comum.is_etep_administrador'):
                ids = []

            elif user.has_perm('comum.is_membro_etep'):
                ids = UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, usuario_grupo__group__name='Membro ETEP').values_list(
                    'setor__uo_id', flat=True
                )

                if not ids:
                    ids = [None]
                elif UnidadeOrganizacional.objects.suap().filter(sigla=get_sigla_reitoria(), id__in=ids).exists():
                    ids = []
        return ids


class SolicitacaoAcompanhamentoQueryset(FiltroUnidadeOrganizacionalQuerySet):
    def em_acompanhamento(self):
        from etep.models import Acompanhamento

        return self.filter(acompanhamento__situacao__in=[Acompanhamento.EM_ACOMPANHAMENTO, Acompanhamento.ACOMPANHAMENTO_PRIORITARIO]).order_by('-id')

    def finalizados(self):
        from etep.models import Acompanhamento

        return self.filter(acompanhamento__situacao=Acompanhamento.ACOMPANHAMENTO_FINALIZADO).order_by('-id')

    def pendentes(self):
        return self.exclude(avaliador__id__isnull=False)

    def interessados(self):
        user = tl.get_user()
        return (
            self.em_acompanhamento()
            .filter(acompanhamento__interessado__vinculo__user=user, acompanhamento__interessado__ativado=True)
            .exclude(solicitante=user)
        )


class SolicitacaoAcompanhamentoManager(models.Manager):
    def get_queryset(self):
        from etep.models import Interessado

        user = tl.get_user()
        qs = SolicitacaoAcompanhamentoQueryset(self.model, key='aluno__curso_campus__diretoria__setor__uo', using=self._db).get_filtered_queryset()

        if user and not user.is_anonymous:
            qs = qs | self.model.objects.filter(solicitante=user)

            interessados = Interessado.locals.ativos().filter(vinculo__user_id=user.id)
            if interessados.exists():
                qs = qs | self.model.objects.filter(acompanhamento__interessado__in=interessados.values('pk'))

        return qs.distinct()

    def em_acompanhamento(self):
        return self.get_queryset().em_acompanhamento()

    def finalizados(self):
        return self.get_queryset().finalizados()

    def pendentes(self):
        return self.get_queryset().pendentes()

    def interessados(self):
        return self.get_queryset().interessados()


class AcompanhamentoQueryset(FiltroUnidadeOrganizacionalQuerySet):
    def em_acompanhamento(self):
        from etep.models import Acompanhamento

        return self.filter(situacao=Acompanhamento.EM_ACOMPANHAMENTO)

    def prioritarios(self):
        from etep.models import Acompanhamento

        return self.filter(situacao=Acompanhamento.ACOMPANHAMENTO_PRIORITARIO)

    def finalizados(self):
        from etep.models import Acompanhamento

        return self.filter(situacao=Acompanhamento.ACOMPANHAMENTO_FINALIZADO)

    def nao_finalizados(self):
        from etep.models import Acompanhamento

        return self.exclude(situacao=Acompanhamento.ACOMPANHAMENTO_FINALIZADO)


class AcompanhamentoManager(models.Manager):
    def get_queryset(self):
        from etep.models import Interessado

        user = tl.get_user()
        qs = AcompanhamentoQueryset(self.model, key='aluno__curso_campus__diretoria__setor__uo', using=self._db).get_filtered_queryset()

        if user and not user.is_anonymous:
            qs = qs | self.model.objects.filter(solicitacaoacompanhamento__solicitante=user)

            interessados = Interessado.locals.ativos().filter(vinculo__user_id=user.id)
            if interessados.exists():
                qs = qs | self.model.objects.filter(interessado__in=interessados.values('pk'))

        return qs.distinct()

    def em_acompanhamento(self):
        return self.get_queryset().em_acompanhamento()

    def prioritarios(self):
        return self.get_queryset().prioritarios()

    def finalizados(self):
        return self.get_queryset().finalizados()

    def nao_finalizados(self):
        return self.get_queryset().nao_finalizados()


class RegistroAcompanhamentoQueryset(FiltroUnidadeOrganizacionalQuerySet):
    def ciencia_pendente(self, vinculo):
        return self.filter(
            registroacompanhamentointeressado__interessado__vinculo=vinculo, registroacompanhamentointeressado__data_ciencia__isnull=True
        ).distinct()


class RegistroAcompanhamentoManager(models.Manager):
    def get_queryset(self):
        from etep.models import Interessado

        user = tl.get_user()
        qs = RegistroAcompanhamentoQueryset(
            self.model, key='acompanhamento__aluno__curso_campus__diretoria__setor__uo', using=self._db
        ).get_filtered_queryset()

        if user and not user.is_anonymous:
            qs = qs | self.model.objects.filter(usuario=user)
            interessados = Interessado.locals.ativos().filter(vinculo__user_id=user.id)
            if interessados.exists():
                qs = qs | self.model.objects.filter(registroacompanhamentointeressado__interessado__in=interessados.values('pk'))

        return qs.distinct()

    def ciencia_pendente(self, vinculo):
        return self.get_queryset().ciencia_pendente(vinculo)


class InteressadoQueryset(models.QuerySet):
    def ativos(self):
        return self.filter(ativado=True)


class InteressadoManager(models.Manager):
    def get_queryset(self):
        return InteressadoQueryset(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()


class AtividadeManager(models.Manager):
    def get_queryset(self):
        from etep.models import Atividade

        user = tl.get_user()
        qs = FiltroUnidadeOrganizacionalQuerySet(model=self.model, key='usuario__vinculo__setor__uo', using=self._db).get_filtered_queryset()
        if user and not user.has_perm('comum.is_etep_administrador'):
            qs = qs | Atividade.objects.filter(visibilidade=True)
            qs = qs.distinct()
        return qs


class DocumentoManager(models.Manager):
    def get_queryset(self):
        from etep.models import Documento

        user = tl.get_user()
        qs = FiltroUnidadeOrganizacionalQuerySet(
            model=self.model, key='atividade__usuario__vinculo__setor__uo', using=self._db
        ).get_filtered_queryset()
        if user and not user.has_perm('comum.is_etep_administrador'):
            qs = qs | Documento.objects.filter(atividade__visibilidade=True)
            qs = qs.distinct()
        return qs
