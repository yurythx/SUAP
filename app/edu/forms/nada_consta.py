from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from djtools import forms
from edu.models import (
    ConfiguracaoNadaConsta,
    CursoCampus,
    NadaConsta,
)
from rh.models import Servidor, Setor, UnidadeOrganizacional


class ItemConfiguracaoNadaConstaFormset(forms.models.BaseInlineFormSet):
    def clean(self):
        if hasattr(self, 'cleaned_data'):
            tipos_nada_consta = []
            for item in self.cleaned_data:
                if len(item) > 0:
                    possui_exigencia = False
                    if 'tipo_nada_consta' in item:
                        if item['tipo_nada_consta'] in tipos_nada_consta:
                            raise ValidationError('Um Tipo de Nada Consta pode ser vinculado apenas uma vez à Configuração de Nada Consta.')
                        tipos_nada_consta.append(item['tipo_nada_consta'])
                    if item.get('exigido_transferencia_curso'):
                        possui_exigencia = True
                        continue
                    if item.get('exigido_transferencia_intercampus'):
                        possui_exigencia = True
                        continue
                    if item.get('exigido_transferencia_externa'):
                        possui_exigencia = True
                        continue
                    if item.get('exigido_trancamento_curso'):
                        possui_exigencia = True
                        continue
                    if item.get('exigido_cancelamento_curso'):
                        possui_exigencia = True
                        continue
                    if item.get('exigido_emissao_diploma'):
                        possui_exigencia = True
                        continue
                    if not possui_exigencia:
                        raise ValidationError('Marque pelo menos um tipo de procedimento que será exigido em cada Item de Nada Consta.')


class ConfiguracaoNadaConstaForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoNadaConsta
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['uo'].queryset = UnidadeOrganizacional.objects.campi()

    def clean_modalidades(self):
        modalidades = self.cleaned_data['modalidades']
        uo = self.cleaned_data['uo']
        qs = ConfiguracaoNadaConsta.objects.filter(uo=uo, ativo=True, modalidades__in=modalidades)
        if self.instance.id:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise ValidationError('A mesma modalidade não pode ser vinculada a mais de uma Configuração de Nada Consta do campus.')
        return modalidades


class InformarResponsaveisNadaConstaForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoNadaConsta
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fieldsets = []
        for item in self.instance.get_itens():
            setores_responsaveis = f'setores_responsaveis{item.pk}'
            self.fields[setores_responsaveis] = forms.MultipleModelChoiceFieldPlus(
                Setor.objects, label='Setores Responsáveis', required=False, initial=item.setores_responsaveis.values_list('pk', flat=True)
            )
            self.fields[setores_responsaveis].queryset = self.fields[setores_responsaveis].queryset.filter(uo=self.instance.uo)

            servidores_responsaveis = f'servidores_responsaveis{item.pk}'
            self.fields[servidores_responsaveis] = forms.MultipleModelChoiceFieldPlus(
                Servidor.objects, label='Servidores Responsáveis', required=False, initial=item.servidores_responsaveis.values_list('pk', flat=True)
            )
            self.fields[servidores_responsaveis].queryset = self.fields[servidores_responsaveis].queryset.filter(setor__uo=self.instance.uo)

            prazo_para_atendimento = f'prazo_para_atendimento{item.pk}'
            self.fields[prazo_para_atendimento] = forms.IntegerField(
                label='Prazo para Atendimento', help_text='Em dias úteis', initial=item.prazo_para_atendimento
            )

            prazo_validade = f'prazo_validade{item.pk}'
            self.fields[prazo_validade] = forms.IntegerField(
                label='Prazo de Validade', help_text='Validade do nada consta em dias corridos.', initial=item.prazo_validade
            )

            fields = [
                setores_responsaveis,
                servidores_responsaveis,
                prazo_para_atendimento,
                prazo_validade,
            ]
            if self.request.user.has_perm('comum.is_administrador_academico'):
                avaliado_coordenacao_curso = f'avaliado_coordenacao_curso{item.pk}'
                self.fields[avaliado_coordenacao_curso] = forms.BooleanField(
                    label='Avaliado pela Coordenação de Curso', required=False, initial=item.avaliado_coordenacao_curso
                )

                cursos = f'cursos{item.pk}'
                self.fields[cursos] = forms.MultipleModelChoiceFieldPlus(
                    CursoCampus.objects,
                    label='Cursos',
                    required=False,
                    initial=item.cursos.values_list('pk', flat=True),
                    help_text='Informe somente se o item de nada consta for exigido para um conjunto específico de cursos do campus.',
                )
                self.fields[cursos].queryset = self.fields[cursos].queryset.filter(
                    diretoria__setor__uo=self.instance.uo, modalidade__in=self.instance.modalidades.values_list('pk', flat=True)
                )

                fields.extend([avaliado_coordenacao_curso, cursos])

            self.fieldsets.append(
                (item.tipo_nada_consta.descricao, {'fields': fields}),
            )

    def save(self, *args, **kwargs):
        for item in self.instance.get_itens():
            setores_responsaveis = f'setores_responsaveis{item.pk}'
            servidores_responsaveis = f'servidores_responsaveis{item.pk}'
            prazo_para_atendimento = f'prazo_para_atendimento{item.pk}'
            prazo_validade = f'prazo_validade{item.pk}'
            item.setores_responsaveis.set(self.cleaned_data[setores_responsaveis])
            item.servidores_responsaveis.set(self.cleaned_data[servidores_responsaveis])
            item.prazo_para_atendimento = self.cleaned_data[prazo_para_atendimento]
            item.prazo_validade = self.cleaned_data[prazo_validade]
            if self.request.user.has_perm('comum.is_administrador_academico'):
                avaliado_coordenacao_curso = f'avaliado_coordenacao_curso{item.pk}'
                cursos = f'cursos{item.pk}'
                item.avaliado_coordenacao_curso = self.cleaned_data[avaliado_coordenacao_curso]
                item.cursos.set(self.cleaned_data[cursos])
            item.save()


class AvaliarNadaConstaForm(forms.ModelFormPlus):
    quitado = forms.BooleanRequiredField(label='Quitado', required=True)
    justificativa_avaliacao = forms.CharFieldPlus(
        required=False, label='Justiticativa da Avaliação', help_text='Preenchimento obrigatório da justificativa em caso de não quitação.'
    )

    class Meta:
        model = NadaConsta
        fields = 'quitado', 'justificativa_avaliacao'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.justificativa_solicitacao:
            self.INFO = mark_safe(f'Justificativa da Solicitação: <br><br><i>{self.instance.justificativa_solicitacao}</i>')

    def clean_justificativa_avaliacao(self):
        justificativa_avaliacao = self.cleaned_data['justificativa_avaliacao']
        nao_quitado = 'quitado' in self.cleaned_data and self.cleaned_data['quitado'] is False
        if nao_quitado and not justificativa_avaliacao:
            raise ValidationError('Informe a justificativa pela qual o nada consta não está sendo aprovado/deferido.')
        return justificativa_avaliacao

    def processar(self):
        self.instance.avaliar(self.request.user)


class RevogarNadaConstaForm(forms.ModelFormPlus):
    class Meta:
        model = NadaConsta
        fields = ('justificativa_revogacao',)

    def processar(self):
        self.instance.revogar(self.request.user)


class ReplicarConfiguracaoNadaConstaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Replicar Configuração de Nada Consta'
    uos = forms.MultipleModelChoiceFieldPlus(
        UnidadeOrganizacional.objects.campi().all(),
        label='Campi',
        required=True,
        help_text='Informe os campi para os quais você deseja replicar esta configuração de nada consta',
    )

    def processar(self, configuracao_nada_consta):
        configuracao_nada_consta.replicar(self.cleaned_data['uos'])
