from djtools.db import models
from djtools.utils import send_mail
from edu.models.logs import LogModel


class PlanoEnsino(LogModel):
    diario = models.ForeignKeyPlus('edu.Diario', on_delete=models.CASCADE)
    ementa = models.TextField('Ementa', default='', blank=True)
    justificativa = models.TextField('Justificativa', default='', blank=True)
    objetivo_geral = models.TextField('Objetivo Geral', default='', blank=True)
    objetivos_especificos = models.TextField('Objetivos Específicos', default='', blank=True)
    conteudo_programatico = models.TextField('Conteúdo Programático', default='', blank=True)
    metodologia = models.TextField('Metodologia', default='', blank=True)
    informacoes_adicionais = models.TextField('Informações Adicionais', default='', blank=True)
    coordenador_curso = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Coordenador do Curso', null=True)
    data_submissao = models.DateFieldPlus('Data da Submissão', null=True)
    data_aprovacao = models.DateFieldPlus('Data da Aprovação', null=True)
    data_homologacao = models.DateFieldPlus('Data da Homologação', null=True)

    class Meta:
        verbose_name = 'Plano de Ensino'
        verbose_name_plural = 'Planos de Ensino'
        ordering = ('id',)

    def __str__(self):
        return f'Plano de Ensino - {self.diario}'

    def get_absolute_url(self):
        return f'/edu/plano_ensino_pdf/{self.pk:d}/'

    def save(self, *args, **kwargs):
        if self.coordenador_curso is None:
            self.coordenador_curso = self.diario.turma.curso_campus.coordenador
        super().save(*args, **kwargs)

    def notificar_devolucao(self, user, justificativa):
        mensagem = f"""Caro professor(a),
        O plano de ensino do diario {self.diario} foi devolvido por {user} pelo seguindo motivo:
        {justificativa}
        """
        emails = set()
        for professor_diario in self.diario.professordiario_set.all():
            emails.add(professor_diario.professor.get_vinculo().email_notificacao)
        send_mail('Devolução de Plano de Ensino', mensagem, None, list(emails))

    def devolver_para_professor(self, user, justificativa):
        self.data_submissao = None
        self.notificar_devolucao(user, justificativa)
        self.save()

    def devolver_para_coordenador(self, user, justificativa):
        self.data_aprovacao = None
        self.notificar_devolucao(user, justificativa)
        self.save()

    def can_change(self, user):
        return self.data_submissao is None and self.diario.professordiario_set.filter(professor__vinculo_id=user.get_vinculo().pk).exists()


class ReferenciaBibliograficaBasica(LogModel):
    plano_ensino = models.ForeignKeyPlus(PlanoEnsino, verbose_name='Plano de Ensino')
    referencia = models.CharFieldPlus('Referência')
    disponivel = models.BooleanField('Disponível na Biblioteca', null=True)

    class Meta:
        verbose_name = 'Referência Bibliográfica Básica'
        verbose_name_plural = 'Referências Bibliográfica Básica'
        ordering = ('id',)


class ReferenciaBibliograficaComplementar(LogModel):
    plano_ensino = models.ForeignKeyPlus(PlanoEnsino, verbose_name='Plano de Ensino')
    referencia = models.CharFieldPlus('Referência')
    disponivel = models.BooleanField('Disponível na Biblioteca', null=True)

    class Meta:
        verbose_name = 'Referência Bibliográfica Complementar'
        verbose_name_plural = 'Referências Bibliográfica Complementar'
        ordering = ('id',)
