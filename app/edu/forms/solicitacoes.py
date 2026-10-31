from djtools import forms


class RejeitarSolicitacaoUsuarioForm(forms.FormPlus):
    SUBMIT_LABEL = 'Rejeitar Solicitação do Usuário'
    razao_indeferimento = forms.CharField(widget=forms.Textarea(), required=True, label='Razão do Indeferimento')
    fieldsets = (('', {'fields': ('razao_indeferimento',)}),)


class AtenderSolicitacaoProrrogacaoEtapaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Atender Solicitação do Usuário'
    data_prorrogacao = forms.DateFieldPlus(label='Data limite da Prorrogação', required=True)
