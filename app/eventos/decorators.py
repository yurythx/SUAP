from functools import wraps

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from djtools.utils import (
    serialization,
    tl,
)


def pode_submeter_trabalho_ao_evento(modelo_evento):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            evento_id = kwargs.get('evento_id')
            if evento_id:
                evento = get_object_or_404(modelo_evento, pk=evento_id)
                if not (evento.ativo and evento.deferido):
                    messages.error(request, 'Evento inativo ou cancelado. Você não pode submeter trabalho para este evento.')
                    return redirect('/eventos/inscricao/')
                if not evento.configuracao or not evento.estah_em_periodo_submissao():
                    messages.error(request, 'Evento fora do período de submissão de trabalhos')
                    return redirect('/eventos/inscricao/')
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def verifica_avaliador_logado(modelo_evento, modelo_avaliacao_submissao):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            participante_logado_id = request.session.get('participante_logado_id', None)
            participante_logado_eh_avaliador_de_trabalho = request.session.get('participante_logado_eh_avaliador_de_trabalho', None)
            if (not participante_logado_id) or (not participante_logado_eh_avaliador_de_trabalho):
                evento_id = kwargs.get('evento_id')
                if evento_id:
                    evento = get_object_or_404(modelo_evento, pk=evento_id)
                else:
                    avaliacao_submissao_id = kwargs.get('avaliacao_submissao_id')
                    avaliacao_submissao = get_object_or_404(modelo_avaliacao_submissao, pk=avaliacao_submissao_id)
                    evento = avaliacao_submissao.avaliador_modalidade.modalidade.evento
                messages.error(
                    request,
                    'Você não está autenticado para realizar a avaliação de trabalhos. '
                    'Certifique-se de informar seu email e chave de acesso corretamente ou '
                    'entre em contato com a administração do evento em caso de problemas.',
                )
                return redirect(reverse('autenticar_participante', args=(evento.pk,)))
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def valida_passo_inscricao(passo_anterior_requerido):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            evento_id = kwargs.get('evento_id')
            dados_inscricao_eventos = request.session.get('dados_inscricao_eventos', {})
            if (not dados_inscricao_eventos) or 'passo_anterior_requerido' not in dados_inscricao_eventos:
                messages.error(request, 'Formulário vazio. Por favor, reinicie o preenchimento do formulário. ')
                return redirect(reverse('area_publica_inscricao_passo_1', args=(evento_id,)))

            dados_inscricao_eventos = {key: serialization.deserialize(value) if value else value for key, value in dados_inscricao_eventos.items()}
            # Compara a variavel na sessao, que identifica o ultimo passo, com o passo anterior requerido
            if int(dados_inscricao_eventos['passo_anterior_requerido']) < passo_anterior_requerido:
                messages.error(request, 'Dados incompletos. Por favor, reinicie o preenchimento do formulário. ')
                return redirect(reverse('area_publica_inscricao_passo_1', args=(evento_id,)))

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def registra_atualizado_por(modelo):
    def salvar_atualizacao_por(original_save):
        @wraps(original_save)
        def atualiza_usuario(self, *args, **kwargs):
            if hasattr(self, 'ultima_atualizacao_por') and tl.get_user():
                self.ultima_atualizacao_por = tl.get_user()
            original_save(self, *args, **kwargs)

        return atualiza_usuario

    # Adiciona o decorator ao método 'save' do modelo
    modelo.save = salvar_atualizacao_por(modelo.save)
    return modelo


def trata_validation_error(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ValidationError as e:
            error_message = str(e)
            messages.error(request, error_message)
            return redirect(request.path)

    return _wrapped_view
