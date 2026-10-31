import io
import shlex
from contextlib import redirect_stderr, redirect_stdout

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.urls import reverse

from djtools import forms
from djtools.utils.response import httprr, rtr

from rsc_tae.manutencao_comandos import COMANDOS_MANUTENCAO, comando_por_chave
from rsc_tae.models import ExecucaoManutencaoRSCTae


class ExecutarComandoManutencaoForm(forms.FormPlus):
    """Form da tela de manutenção: escolhe um command da allowlist e informa os argumentos."""

    METHOD = 'POST'
    SUBMIT_LABEL = 'Executar'

    comando = forms.ChoiceField(label='Comando')
    argumentos = forms.CharFieldPlus(
        label='Argumentos',
        required=False,
        help_text='Ex.: 1 --membro-matricula 1234 (sem --commit = simulação; adicione --commit para aplicar).',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Value = chave (referência opaca); o nome real do command não vai para o HTML.
        # O ChoiceField já rejeita chaves fora da allowlist.
        # A opção vazia inicial obriga a escolha explícita: sem ela o navegador já vem com o
        # primeiro command selecionado e um submit distraído o executaria.
        self.fields['comando'].choices = [('', '-- Selecionar --'), *((c['chave'], c['label']) for c in COMANDOS_MANUTENCAO)]


def _vinculo_ou_none(request):
    try:
        return request.user.get_vinculo()
    except Exception:
        return None


@rtr('rsc_tae/manutencao.html')
@login_required
def manutencao(request):
    """Tela de manutenção (superuser): executa commands da allowlist e mostra o retorno."""
    if not request.user.is_superuser:
        raise PermissionDenied('Acesso restrito a superusuários.')

    form = ExecutarComandoManutencaoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entrada = comando_por_chave(form.cleaned_data['comando'])
        if entrada is None:
            return httprr(reverse('rsc_tae:manutencao'), 'Comando não permitido.', tag='error')
        return _executar_comando(request, entrada['nome'], form.cleaned_data['argumentos'])

    exec_id = request.GET.get('exec')
    resultado = ExecucaoManutencaoRSCTae.objects.filter(pk=exec_id).first() if exec_id else None
    execucoes = ExecucaoManutencaoRSCTae.objects.select_related('executado_por_vinculo__pessoa')[:30]
    return {
        'title': 'Manutenção — RSC-TAE',
        'form': form,
        'comandos': COMANDOS_MANUTENCAO,
        'resultado': resultado,
        'execucoes': execucoes,
    }


def _executar_comando(request, comando, argumentos):
    voltar = reverse('rsc_tae:manutencao')
    argumentos = (argumentos or '').strip()
    try:
        args = shlex.split(argumentos)
    except ValueError as erro:
        return httprr(voltar, f'Argumentos inválidos: {erro}', tag='error')

    saida = io.StringIO()
    sucesso = True
    try:
        with redirect_stdout(saida), redirect_stderr(saida):
            call_command(comando, *args, stdout=saida, stderr=saida)
    except Exception as erro:
        sucesso = False
        saida.write(f'\n[ERRO] {type(erro).__name__}: {erro}')

    execucao = ExecucaoManutencaoRSCTae.objects.create(
        comando=comando,
        argumentos=argumentos,
        executado_por_vinculo=_vinculo_ou_none(request),
        sucesso=sucesso,
        saida=saida.getvalue(),
    )
    mensagem = 'Execução concluída.' if sucesso else 'A execução falhou — veja a saída.'
    return httprr(f'{voltar}?exec={execucao.pk}', mensagem, tag='success' if sucesso else 'error')
