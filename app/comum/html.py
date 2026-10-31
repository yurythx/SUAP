from collections import OrderedDict

from django.db import models
from django.utils.safestring import mark_safe

from comum.models import ReuniaoOrgaoColegiado
from djtools.html.calendarios import CalendarioMix, CalendarioMixEvento, CalendarioMixEventoAtualizacao, CalendarioMixTipoEvento


class ModelView:
    """Adicionar lógica de apresentação/formatação de dados a uma instância de modelo para
    evitar, por exemplo, métodos no modelo que retornem conteúdo HTML ou classes CSS,
    assuntos próprios da camada de Template.
    """

    def __init__(self, model_instance: models.Model):
        self._model_instance = model_instance

    def __getattribute__(self, name):
        try:
            # 1º tenta ler o atributo na instância da subclasse de ModelView
            return super().__getattribute__(name)
        except AttributeError:
            # 2º tenta ler o atributo na instância do modelo
            return getattr(self._model_instance, name)


class ReuniaoOrgaoColegiadoView(ModelView):
    @staticmethod
    def get_colegiados_css_class() -> dict[int, str]:
        return dict(
            [
                [ReuniaoOrgaoColegiado.ORGAO_CODIR, 'success'],
                [ReuniaoOrgaoColegiado.ORGAO_CONSUP, 'info'],
                [ReuniaoOrgaoColegiado.ORGAO_CONSEPEX, 'extra2'],
            ]
        )

    def get_colegiado_display_html(self):
        css_class = self.get_colegiados_css_class().get(self.colegiado, '')

        return mark_safe(f"""
            <span class="status status-{css_class}">
                {self.get_colegiado_display()}
            </span>
        """)


class CalendarioReuniaoOrgaoColegiadoHTML:
    calendario_dados: ReuniaoOrgaoColegiado.CalendarioReuniaoOrgaoColegiado
    calendario_instance: CalendarioMix

    def __init__(
        self,
        calendario_dados: ReuniaoOrgaoColegiado.CalendarioReuniaoOrgaoColegiado,
        formato=CalendarioMix.FORMATO_ANUAL,
        legenda=CalendarioMix.LEGENDA_NAO_EXIBIR,
    ):
        self.calendario_dados = calendario_dados
        self.formato = formato
        self.legenda = legenda
        self.calendario_instance = None
        self._set_calendario_instance()

    def _set_calendario_instance(self):
        colegiados_css_class = ReuniaoOrgaoColegiadoView.get_colegiados_css_class()

        evento_codir = CalendarioMixTipoEvento(
            id='CODIR', descricao='CODIR', css_class=colegiados_css_class.get(ReuniaoOrgaoColegiado.ORGAO_CODIR, '')
        )
        evento_consup = CalendarioMixTipoEvento(
            id='CONSUP', descricao='CONSUP', css_class=colegiados_css_class.get(ReuniaoOrgaoColegiado.ORGAO_CONSUP, '')
        )
        evento_consepex = CalendarioMixTipoEvento(
            id='CONSEPEX', descricao='CONSEPEX', css_class=colegiados_css_class.get(ReuniaoOrgaoColegiado.ORGAO_CONSEPEX, '')
        )
        evento_varios = CalendarioMixTipoEvento(id='varias_reunioes', descricao='Várias Reuniões no Dia', css_class='warning')
        evento_conflito = CalendarioMixTipoEvento(id='conflito_horarios', descricao='Conflito de Horários', css_class='extra6')
        evento_invalido = CalendarioMixTipoEvento(id='invalido', descricao='Evento Inválido', css_class='conflito')

        cal = CalendarioMix(
            formato=CalendarioMix.FORMATO_MENSAL if self.formato == CalendarioMix.FORMATO_MENSAL else CalendarioMix.FORMATO_ANUAL,
            legenda=self.legenda,
        )

        cal.adicionar_tipo_evento(evento_codir)
        cal.adicionar_tipo_evento(evento_consup)
        cal.adicionar_tipo_evento(evento_consepex)
        if self.formato == CalendarioMix.FORMATO_ANUAL:
            cal.adicionar_tipo_evento(evento_varios)
        cal.adicionar_tipo_evento(evento_conflito)

        for mes_info in self.calendario_dados.reunioes_por_ano.values():
            for reunioes in mes_info.values():
                for reuniao in reunioes:
                    evento_id = f'{reuniao.id}'

                    evento_data_inicio = reuniao.data_inicio
                    evento_data_fim = reuniao.data_fim

                    if evento_data_inicio < self.calendario_dados.data_inicio:
                        evento_data_inicio = self.calendario_dados.data_inicio
                    if evento_data_fim > self.calendario_dados.data_fim:
                        evento_data_fim = self.calendario_dados.data_fim

                    evento_descricao = f'{reuniao.titulo}'

                    if self.formato == CalendarioMix.FORMATO_MENSAL:
                        evento_descricao = f"""
                            <strong>{reuniao.hora_inicio.strftime('%H:%M')} - {reuniao.hora_fim.strftime('%H:%M')}</strong>
                            {evento_descricao}
                        """

                    if self.formato == CalendarioMix.FORMATO_ANUAL:
                        evento_descricao = f"""
                            {evento_descricao}
                            (das {reuniao.hora_inicio.strftime('%H:%M')} às {reuniao.hora_fim.strftime('%H:%M')})
                        """

                    evento_tipo = evento_invalido

                    if reuniao.colegiado == ReuniaoOrgaoColegiado.ORGAO_CODIR:
                        evento_tipo = evento_codir
                    if reuniao.colegiado == ReuniaoOrgaoColegiado.ORGAO_CONSUP:
                        evento_tipo = evento_consup
                    if reuniao.colegiado == ReuniaoOrgaoColegiado.ORGAO_CONSEPEX:
                        evento_tipo = evento_consepex

                    cal.adicionar_evento(
                        CalendarioMixEvento(
                            id=evento_id,
                            tipo_evento_id=evento_tipo.id,
                            data_inicio=evento_data_inicio,
                            data_fim=evento_data_fim,
                            descricao=evento_descricao,
                            url=f'/comum/orgaos_colegiados_detalhar_reuniao/{reuniao.id}/',
                        )
                    )

        dias_varias_reunioes = OrderedDict()  # {dia: [reuniao, reuniao, ...]}
        dias_conflito_horarios = OrderedDict()  # {dia: [reuniao, reuniao, ...]}

        for dia, reunioes_no_dia in self.calendario_dados.reunioes_por_dia.items():
            if len(reunioes_no_dia) > 1:
                dias_varias_reunioes[dia] = reunioes_no_dia
            for reuniao_no_dia in reunioes_no_dia:
                for outra_reuniao_no_dia in reunioes_no_dia:
                    if outra_reuniao_no_dia.id != reuniao_no_dia.id:
                        if (
                            outra_reuniao_no_dia.hora_inicio <= reuniao_no_dia.hora_fim
                            and outra_reuniao_no_dia.hora_fim >= reuniao_no_dia.hora_inicio
                        ):
                            if dia not in dias_conflito_horarios:
                                dias_conflito_horarios[dia] = []
                            dias_conflito_horarios[dia].extend([reuniao_no_dia, outra_reuniao_no_dia])

        if self.formato == CalendarioMix.FORMATO_ANUAL:
            for dia, reunioes in dias_varias_reunioes.items():
                for reuniao in reunioes:
                    evento_id = f'{reuniao.id}'
                    cal.atualizar_evento(evento_id, CalendarioMixEventoAtualizacao(descricao='', css_class=evento_varios.css_class), dia, dia)

        for dia, reunioes in dias_conflito_horarios.items():
            for reuniao in reunioes:
                evento_id = f'{reuniao.id}'
                cal.atualizar_evento(evento_id, CalendarioMixEventoAtualizacao(descricao='', css_class=evento_conflito.css_class), dia, dia)

        self.calendario_instance = cal

    def __str__(self):
        return str(self.calendario_instance)
