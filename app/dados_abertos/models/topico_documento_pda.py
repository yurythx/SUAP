from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class TopicoDocumentoPDA(ModelPlus):
    """
    Tópicos livres que compõem o documento do PDA.
    """

    SEARCH_FIELDS = ['titulo', 'conteudo']

    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos',
        on_delete=models.CASCADE,
        related_name='topicos',
        verbose_name=_('PDA'),
    )
    titulo = models.CharFieldPlus(
        _('Título do tópico'), max_length=255, help_text=_('Ex.: Resumo, Objetivos, Metodologia, Estratégias, Canais, etc.')
    )
    conteudo = models.TextField(_('Conteúdo'), blank=True)
    ordem = models.PositiveIntegerFieldPlus(_('Ordem no documento'), default=0, help_text=_('Use para ordenar a exibição dos tópicos.'))
    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True)

    class Meta:
        verbose_name = _('Tópico do documento do PDA')
        verbose_name_plural = _('Tópicos do documento do PDA')
        ordering = ['ordem', 'id']
        unique_together = [('pda', 'titulo')]

    def __str__(self):
        return f'{self.titulo} ({self.pda})'

    def get_conteudo_formatado(self):
        """Retorna o conteúdo formatado, substituindo as marcações do PDA."""
        from django.template.loader import render_to_string

        from .marcacao_pda import MarcacaoPDA
        from ..services.matriz_priorizacao_service import build_matriz_data

        conteudo_formatado = self.conteudo

        # Busca todas as marcações cadastradas
        marcacoes = MarcacaoPDA.objects.all()

        context = {'pda': self.pda}

        for marcacao in marcacoes:
            # Monta a tag que será buscada no conteúdo
            tag_busca = marcacao.marcacao

            # Verifica se a marcação existe no conteúdo antes de processar
            if tag_busca in conteudo_formatado:
                try:
                    # Prepara o contexto com todas as variáveis necessárias
                    matriz = build_matriz_data(self.pda)
                    context.update(
                        {
                            'criterios': matriz.criterios,
                            'bases': matriz.bases,
                            'consulta_publica': matriz.consulta_publica,
                        }
                    )

                    # Renderiza o template (busca em dadosabertos/)
                    html_renderizado = render_to_string(f'dadosabertos/marcacoes/{marcacao.template_base}.html', context)

                    # Substitui a marcação pelo conteúdo renderizado
                    conteudo_formatado = conteudo_formatado.replace(tag_busca, html_renderizado)

                except Exception as e:
                    # Em caso de erro, substitui a marcação por uma mensagem de erro
                    conteudo_formatado = conteudo_formatado.replace(tag_busca, f'[ERRO ao processar marcação {marcacao.marcacao}: {e!s}]')

        return conteudo_formatado
