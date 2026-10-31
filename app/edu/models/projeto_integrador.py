import math
from django.db import transaction
from djtools.db import models
from edu.models import AtividadePraticaProfissional, LogModel
from edu import perms
from edu.managers import ProjetoIntegradorManager


class ProjetoIntegrador(LogModel):
    # Dados gerais
    diario = models.ForeignKeyPlus('edu.diario', verbose_name='Diário')
    tema = models.CharFieldPlus(verbose_name='Tema')
    participantes = models.ManyToManyFieldPlus('edu.matriculadiario', verbose_name='Participantes', blank=True)
    professores = models.ManyToManyFieldPlus('edu.professor', verbose_name='Professores', blank=True)

    # Dados da Banca
    data_hora_defesa = models.DateFieldPlus(verbose_name='Data', null=True, blank=True)
    presidente_banca = models.ForeignKeyPlus('comum.vinculo', verbose_name='Presidente da Banca', null=True, blank=True, related_name='pi1')
    membros_banca = models.ManyToManyFieldPlus('comum.vinculo', verbose_name='Membros da Banca', related_name='pi2', blank=True)
    arquivo = models.FileField(
        verbose_name='Arquivo digitalizado', upload_to='projetos_integradores', null=True, blank=True, help_text='Entrega parcial do projeto'
    )
    obs = models.TextField(verbose_name='Observações da avaliação', null=True, blank=True)

    # Dados da Segunda Banca
    data_hora_defesa2 = models.DateFieldPlus(verbose_name='Data', null=True, blank=True)
    presidente_banca2 = models.ForeignKeyPlus('comum.vinculo', verbose_name='Presidente da Banca', null=True, blank=True, related_name='pi3')
    membros_banca2 = models.ManyToManyFieldPlus('comum.vinculo', verbose_name='Membros da Banca', related_name='pi4', blank=True)
    arquivo2 = models.FileField(
        verbose_name='Arquivo Digitalizado', upload_to='projetos_integradores', null=True, blank=True, help_text='Entrega final do projeto'
    )
    obs2 = models.TextField(verbose_name='Observações da Avaliação', null=True, blank=True)

    # Dados da Terceira Banca
    data_hora_defesa3 = models.DateFieldPlus(verbose_name='Data', null=True, blank=True)
    presidente_banca3 = models.ForeignKeyPlus('comum.vinculo', verbose_name='Presidente da Banca', null=True, blank=True, related_name='pi5')
    membros_banca3 = models.ManyToManyFieldPlus('comum.vinculo', verbose_name='Membros da Banca', related_name='pi6', blank=True)
    arquivo3 = models.FileField(
        verbose_name='Arquivo Digitalizado', upload_to='projetos_integradores', null=True, blank=True, help_text='Entrega final do projeto'
    )
    obs3 = models.TextField(verbose_name='Observações da Avaliação', null=True, blank=True)

    # Dados da Quarta Banca
    data_hora_defesa4 = models.DateFieldPlus(verbose_name='Data', null=True, blank=True)
    presidente_banca4 = models.ForeignKeyPlus('comum.vinculo', verbose_name='Presidente da Banca', null=True, blank=True, related_name='pi7')
    membros_banca4 = models.ManyToManyFieldPlus('comum.vinculo', verbose_name='Membros da Banca', related_name='pi8', blank=True)
    arquivo4 = models.FileField(
        verbose_name='Arquivo Digitalizado', upload_to='projetos_integradores', null=True, blank=True, help_text='Entrega final do projeto'
    )
    obs4 = models.TextField(verbose_name='Observações da Avaliação', null=True, blank=True)

    finalizado = models.BooleanField(verbose_name='Finalizado', default=False)

    objects = models.Manager()
    locals = ProjetoIntegradorManager()

    class Meta:
        verbose_name = 'Projeto Integrador'
        verbose_name_plural = 'Projetos Integradores'

    def __str__(self):
        return f'Projeto integrador da disciplina {self.diario.componente_curricular.componente}'

    def get_avaliacoes(self):
        return self.avaliacaoprojetointegrador_set.order_by('id')

    def get_atividades(self):
        return self.atividadeprojetointegrador_set.order_by('data_prevista_inicio')

    def get_absolute_url(self):
        return f'/edu/projetointegrador/{self.pk}/'

    def get_progresso_atividades(self):
        qtd_atividades_realizadas = (
            AvaliacaoAtividadeProjetoIntegrador.objects.filter(atividade_projeto_integrador__projeto_integrador=self)
            .order_by('atividade_projeto_integrador')
            .values_list('atividade_projeto_integrador', flat=True)
            .distinct()
            .count()
        )
        qtd_atividades = self.atividadeprojetointegrador_set.count()
        return int(qtd_atividades_realizadas * 100.0 / qtd_atividades) if qtd_atividades else 100

    def pode_visualizar(self, user):
        pks = []
        pks.extend(self.professores.values_list('vinculo', flat=True))
        pks.extend(self.diario.professordiario_set.values_list('professor__vinculo', flat=True))
        pks.extend(self.participantes.values_list('matricula_periodo__aluno__vinculos', flat=True))
        return user.get_vinculo().id in pks or perms.realizar_procedimentos_academicos(user, self.diario.turma.curso_campus)

    def is_professor(self, user):
        vinculo = user.get_vinculo()
        return self.professores.filter(vinculo=vinculo).exists() or self.diario.professordiario_set.filter(professor__vinculo=vinculo).exists()

    def pode_gerenciar(self, user):
        return not self.finalizado and self.is_professor(user)

    def get_situacao_display(self):
        return 'Finalizado' if self.finalizado else 'Em Andamento'

    def can_change(self, user=None):
        if user and user.is_superuser:
            return True
        return not self.finalizado and self.pode_visualizar(user)

    def is_pendente_avaliacao(self):
        if self.avaliacaoprojetointegrador_set.exists():
            qs1 = self.avaliacaoprojetointegrador_set.filter(nota__isnull=True)
            qs2 = self.avaliacaoprojetointegrador_set.filter(nota2__isnull=True)
            if self.diario.componente_curricular.qtd_avaliacoes == 1:
                return qs1.exists()
            return qs1.exists() or qs2.exists()
        return True

    def is_avaliacao_concluida(self):
        return not self.is_pendente_avaliacao()

    def get_ids_participantes_sem_registro(self):
        pks = []
        pks.extend(
            AvaliacaoAtividadeProjetoIntegrador.objects.filter(atividade_projeto_integrador__projeto_integrador=self).values_list(
                'participante', flat=True
            )
        )
        pks.extend(self.avaliacaoprojetointegrador_set.exclude(nota__isnull=True, nota2__isnull=True).values_list('participante', flat=True))
        return list(self.participantes.exclude(pk__in=set(pks)).values_list('pk', flat=True))

    def checar_avaliacoes(self):
        if self.avaliacaoprojetointegrador_set.count() != self.participantes.count():
            for participante in self.participantes.all():
                if not self.avaliacaoprojetointegrador_set.filter(participante=participante).exists():
                    self.avaliacaoprojetointegrador_set.create(participante=participante)

    def processar(self, finalizado):
        self.finalizado = finalizado
        self.save()
        for avaliacao in self.get_avaliacoes():
            avaliacao.processar_pratica_profissional(finalizado)


class AtividadeProjetoIntegrador(LogModel):
    projeto_integrador = models.ForeignKeyPlus(ProjetoIntegrador, verbose_name='Projeto Integrador')
    nome = models.CharField(verbose_name='Nome')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    data_prevista_inicio = models.DateFieldPlus(verbose_name='Data prevista do início')
    data_prevista_termino = models.DateFieldPlus(verbose_name='Data prevista do término')
    data_encerramento = models.DateFieldPlus(verbose_name='Data do Encerramento', null=True)
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Atividade de Projeto Integrador'
        verbose_name_plural = 'Atividades de Projeto Integrador'


class AvaliacaoAtividadeProjetoIntegrador(LogModel):
    SITUACAO_CHOICES = [
        [1, 'Realizada integralmente'],
        [2, 'Realizada parcialmente'],
        [3, 'Não realizada'],
    ]
    atividade_projeto_integrador = models.ForeignKeyPlus(AtividadeProjetoIntegrador, verbose_name='Atividade de Projeto Integrador')

    participante = models.ForeignKeyPlus('edu.matriculadiario', verbose_name='Participante')
    situacao = models.IntegerField(verbose_name='Situação', choices=SITUACAO_CHOICES)

    class Meta:
        verbose_name = 'Avaliação de Atividade de Projeto Integrador'
        verbose_name_plural = 'Avaliações de Atividade de Projeto Integrador'


class AvaliacaoProjetoIntegrador(LogModel):
    projeto_integrador = models.ForeignKeyPlus(ProjetoIntegrador, verbose_name='Projeto Integrador')
    participante = models.ForeignKeyPlus('edu.matriculadiario', verbose_name='Participante')
    nota = models.NotaField(verbose_name='Nota', null=True, blank=True)
    nota2 = models.NotaField(verbose_name='Nota', null=True, blank=True)
    nota3 = models.NotaField(verbose_name='Nota', null=True, blank=True)
    nota4 = models.NotaField(verbose_name='Nota', null=True, blank=True)

    class Meta:
        verbose_name = 'Avaliação de Projeto Integrador'
        verbose_name_plural = 'Avaliações de Projeto Integrador'

    def get_media_final(self):
        qtd_avaliacoes = self.projeto_integrador.diario.componente_curricular.qtd_avaliacoes
        if None not in (self.nota, self.nota2, self.nota3, self.nota4)[0:qtd_avaliacoes]:
            return math.ceil(sum((self.nota, self.nota2, self.nota3, self.nota4)[0:qtd_avaliacoes]) / qtd_avaliacoes * 1.0)
        return None

    def get_ch(self):
        return self.projeto_integrador.diario.componente_curricular.ch_projeto_integrador or 0

    def get_id_modalidade_pratica_profissional(self):
        return self.projeto_integrador.diario.componente_curricular.modalidade_pratica_profissional_projeto_integrador_id

    def is_aprovado(self):
        media_final = self.get_media_final()
        if media_final is None:
            return None
        return media_final >= 60

    def get_situacao(self):
        aprovado = self.is_aprovado()
        if aprovado is None:
            return ('Cursando', 'info')
        return ('Aprovado', 'success') if aprovado else ('Reprovado', 'error')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        AtividadePraticaProfissional.remover_registro(self.id, type(self))
        super().delete(*args, **kwargs)

    def processar_pratica_profissional(self, finalizar):
        modalidade_id = self.get_id_modalidade_pratica_profissional()
        if modalidade_id is None:
            return
        if not AtividadePraticaProfissional.pode_registrar(self.participante.matricula_periodo.aluno, modalidade_id):
            return
        atividade = AtividadePraticaProfissional.get(self.id, type(self))
        media = self.get_media_final()
        if finalizar:
            media = 0 if media is None else media
            ch = self.get_ch()
            if atividade:
                AtividadePraticaProfissional.registrar_conclusao(atividade, ch, media)
            else:
                AtividadePraticaProfissional.registrar_inicio_e_conclusao(
                    modalidade_id,
                    self.id,
                    type(self),
                    self.participante.matricula_periodo_id,
                    ch,
                    self.projeto_integrador.get_absolute_url(),
                    str(self.projeto_integrador),
                    media,
                )
        elif not finalizar and atividade:
            atividade.desfazer_conclusao(self.id, type(self))
        elif media is None and atividade is None:
            AtividadePraticaProfissional.registrar_inicio(
                modalidade_id,
                self.id,
                type(self),
                self.participante.matricula_periodo_id,
                self.projeto_integrador.get_absolute_url(),
                str(self.projeto_integrador),
            )
