import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from rsc import dashboard, views
from rsc.models import Arquivo, Avaliacao, ProcessoAvaliador, ProcessoRSC
from rsc.views import _aplicar_campo_arquivo


class TestPodeReenviarEmail:
    def test_aguardando_aceite_pode(self):
        pa = ProcessoAvaliador(status=ProcessoAvaliador.AGUARDANDO_ACEITE)
        assert pa.pode_reenviar_email() is True

    @pytest.mark.parametrize(
        'status',
        [
            ProcessoAvaliador.EM_ESPERA,
            ProcessoAvaliador.AVALIACAO_FINALIZADA,
            ProcessoAvaliador.EXCEDEU_TEMPO_ACEITE,
            ProcessoAvaliador.EXCEDEU_TEMPO_AVALIACAO,
            ProcessoAvaliador.REJEITADO_PELO_AVALIADOR,
        ],
    )
    def test_outras_situacoes_nao_podem(self, status):
        pa = ProcessoAvaliador(status=status)
        assert pa.pode_reenviar_email() is False

    def test_em_avaliacao_sem_avaliacao_iniciada_pode(self):
        pa = ProcessoAvaliador(status=ProcessoAvaliador.EM_AVALIACAO)
        mock_processo = MagicMock()
        mock_avaliador = MagicMock()
        mock_filter_result = MagicMock()
        mock_filter_result.exists.return_value = False
        with (
            patch.object(ProcessoAvaliador, 'processo', new_callable=PropertyMock) as mock_processo_prop,
            patch.object(ProcessoAvaliador, 'avaliador', new_callable=PropertyMock) as mock_avaliador_prop,
            patch('rsc.models.Avaliacao.objects.filter', return_value=mock_filter_result) as mock_filter,
        ):
            mock_processo_prop.return_value = mock_processo
            mock_avaliador_prop.return_value = mock_avaliador
            assert pa.pode_reenviar_email() is True
            mock_filter.assert_called_once_with(processo=mock_processo, avaliador=mock_avaliador, status=Avaliacao.EM_AVALIACAO)

    def test_em_avaliacao_com_avaliacao_iniciada_nao_pode(self):
        pa = ProcessoAvaliador(status=ProcessoAvaliador.EM_AVALIACAO)
        mock_processo = MagicMock()
        mock_avaliador = MagicMock()
        mock_filter_result = MagicMock()
        mock_filter_result.exists.return_value = True
        with (
            patch.object(ProcessoAvaliador, 'processo', new_callable=PropertyMock) as mock_processo_prop,
            patch.object(ProcessoAvaliador, 'avaliador', new_callable=PropertyMock) as mock_avaliador_prop,
            patch('rsc.models.Avaliacao.objects.filter', return_value=mock_filter_result),
        ):
            mock_processo_prop.return_value = mock_processo
            mock_avaliador_prop.return_value = mock_avaliador
            assert pa.pode_reenviar_email() is False


class TestReenviarEmail:
    @patch('rsc.models.send_mail')
    @patch('rsc.models.send_notification')
    @patch('rsc.models.utils.substituir_marcacoes', return_value='corpo')
    @patch('rsc.models.ConfiguracaoRSC.objects')
    def test_aguardando_aceite_usa_email_convite(self, mock_conf, mock_subst, mock_notif, mock_mail):
        config = MagicMock()
        config.email_professor_sorteado = 'TEMPLATE_CONVITE'
        config.dias_para_avaliacao = 15
        mock_conf.first.return_value = config

        # Create a mock processo
        mock_processo = MagicMock()
        mock_processo.servidor.pessoa_fisica.nome = 'Docente Avaliado'

        # Create a mock avaliador
        mock_avaliador = MagicMock()
        mock_avaliador.vinculo.user.get_profile.return_value.nome = 'Avaliador X'
        mock_avaliador.email_contato = 'avaliador@ifrn.edu.br'

        pa = ProcessoAvaliador(status=ProcessoAvaliador.AGUARDANDO_ACEITE)

        with (
            patch.object(ProcessoAvaliador, 'processo', new_callable=PropertyMock) as mock_proc_prop,
            patch.object(ProcessoAvaliador, 'avaliador', new_callable=PropertyMock) as mock_aval_prop,
            patch.object(pa, 'data_limite', return_value='10/06/2026'),
        ):
            mock_proc_prop.return_value = mock_processo
            mock_aval_prop.return_value = mock_avaliador
            email_destino = pa.reenviar_email()

        assert mock_subst.call_args[0][0] == 'TEMPLATE_CONVITE'
        mock_mail.assert_called_once()
        mock_notif.assert_called_once()
        assert email_destino == 'avaliador@ifrn.edu.br'

    @patch('rsc.models.send_mail')
    @patch('rsc.models.send_notification')
    @patch('rsc.models.utils.substituir_marcacoes', return_value='corpo')
    @patch('rsc.models.ConfiguracaoRSC.objects')
    def test_em_avaliacao_usa_email_lembrete(self, mock_conf, mock_subst, mock_notif, mock_mail):
        config = MagicMock()
        config.email_lembrete_avaliacao = 'TEMPLATE_LEMBRETE'
        config.dias_para_avaliacao = 15
        mock_conf.first.return_value = config

        # Create a mock processo
        mock_processo = MagicMock()
        mock_processo.servidor.pessoa_fisica.nome = 'Docente Avaliado'

        # Create a mock avaliador
        mock_avaliador = MagicMock()
        mock_avaliador.vinculo.user.get_profile.return_value.nome = 'Avaliador X'
        mock_avaliador.email_contato = 'avaliador@ifrn.edu.br'

        pa = ProcessoAvaliador(status=ProcessoAvaliador.EM_AVALIACAO)

        with (
            patch.object(ProcessoAvaliador, 'processo', new_callable=PropertyMock) as mock_proc_prop,
            patch.object(ProcessoAvaliador, 'avaliador', new_callable=PropertyMock) as mock_aval_prop,
            patch.object(pa, 'data_limite', return_value='10/06/2026'),
            patch.object(pa, 'pode_reenviar_email', return_value=True),
        ):
            mock_proc_prop.return_value = mock_processo
            mock_aval_prop.return_value = mock_avaliador
            pa.reenviar_email()

        assert mock_subst.call_args[0][0] == 'TEMPLATE_LEMBRETE'
        mock_mail.assert_called_once()
        mock_notif.assert_called_once()

    @patch('rsc.models.ConfiguracaoRSC.objects')
    def test_situacao_invalida_levanta(self, mock_conf):
        mock_conf.first.return_value = MagicMock()
        pa = ProcessoAvaliador(status=ProcessoAvaliador.AVALIACAO_FINALIZADA)

        with pytest.raises(Exception, match='Não é possível reenviar e-mail'):
            pa.reenviar_email()

    @patch('rsc.models.send_mail')
    @patch('rsc.models.send_notification')
    @patch('rsc.models.utils.substituir_marcacoes', return_value='corpo')
    @patch('rsc.models.ConfiguracaoRSC.objects')
    def test_nao_altera_prazos(self, mock_conf, mock_subst, mock_notif, mock_mail):
        config = MagicMock()
        config.email_professor_sorteado = 'TEMPLATE_CONVITE'
        config.dias_para_avaliacao = 15
        mock_conf.first.return_value = config

        mock_processo = MagicMock()
        mock_processo.servidor.pessoa_fisica.nome = 'Docente Avaliado'
        mock_avaliador = MagicMock()
        mock_avaliador.vinculo.user.get_profile.return_value.nome = 'Avaliador X'
        mock_avaliador.email_contato = 'avaliador@ifrn.edu.br'

        pa = ProcessoAvaliador(status=ProcessoAvaliador.AGUARDANDO_ACEITE)
        pa.data_convite = datetime.datetime(2026, 5, 1, 10, 0)
        pa.data_aceite = None

        with (
            patch.object(ProcessoAvaliador, 'processo', new_callable=PropertyMock) as mock_proc_prop,
            patch.object(ProcessoAvaliador, 'avaliador', new_callable=PropertyMock) as mock_aval_prop,
            patch.object(pa, 'data_limite', return_value='10/06/2026'),
        ):
            mock_proc_prop.return_value = mock_processo
            mock_aval_prop.return_value = mock_avaliador
            pa.reenviar_email()

        assert pa.data_convite == datetime.datetime(2026, 5, 1, 10, 0)
        assert pa.data_aceite is None


class TestReenviarEmailAvaliadorView:
    @patch('rsc.views.httprr')
    @patch('rsc.views.get_object_or_404')
    def test_situacao_valida_envia_e_redireciona(self, mock_get, mock_httprr, rf):
        pa = MagicMock()
        pa.pode_reenviar_email.return_value = True
        pa.reenviar_email.return_value = 'fulano@ifrn.edu.br'
        mock_get.return_value = pa
        mock_httprr.return_value = 'redirect-ok'

        request = rf.get('/rsc/reenviar_email_avaliador/1/')
        request.user = MagicMock(is_authenticated=True)

        from rsc.views import reenviar_email_avaliador

        result = reenviar_email_avaliador(request, processo_avaliador_id=1)

        pa.reenviar_email.assert_called_once()
        assert result == 'redirect-ok'
        assert mock_httprr.call_args[0][0] == '/admin/rsc/processoavaliador/'
        assert 'fulano@ifrn.edu.br' in mock_httprr.call_args[0][1]

    @patch('rsc.views.httprr')
    @patch('rsc.views.get_object_or_404')
    def test_situacao_invalida_nao_envia(self, mock_get, mock_httprr, rf):
        pa = MagicMock()
        pa.pode_reenviar_email.return_value = False
        mock_get.return_value = pa
        mock_httprr.return_value = 'redirect-erro'

        request = rf.get('/rsc/reenviar_email_avaliador/1/')
        request.user = MagicMock(is_authenticated=True)

        from rsc.views import reenviar_email_avaliador

        result = reenviar_email_avaliador(request, processo_avaliador_id=1)

        pa.reenviar_email.assert_not_called()
        assert result == 'redirect-erro'
        assert mock_httprr.call_args.kwargs.get('tag') == 'error'

    @patch('rsc.views.get_object_or_404')
    def test_sem_permissao_bloqueia(self, mock_get, rf):
        request = rf.get('/rsc/reenviar_email_avaliador/1/')
        request.user = MagicMock(is_authenticated=True)
        request.user.has_perm.return_value = False

        from rsc.views import reenviar_email_avaliador

        with pytest.raises(PermissionDenied):
            reenviar_email_avaliador(request, processo_avaliador_id=1)

        mock_get.assert_not_called()


class TestTemAlgumAvaliadorAtivo:
    """Regra de início das avaliações: basta 1 avaliador ativo (interno OU externo).

    Antes, o processo só saía de 'validado' para 'aguardando aceite' com a banca
    completa (1 interno + 2 externos). Agora inicia assim que o primeiro avaliador
    é cadastrado — a conclusão (3 avaliações finalizadas) permanece inalterada.
    """

    def _processo(self):
        # Bypassa o __init__ (que acessa o banco via ConfiguracaoRSC.objects.first()).
        return ProcessoRSC.__new__(ProcessoRSC)

    def test_com_avaliador_ativo_retorna_true(self):
        processo = self._processo()
        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        with patch('rsc.models.ProcessoAvaliador.objects.filter', return_value=mock_qs) as mock_filter:
            assert processo.tem_algum_avaliador_ativo() is True
            # uma única query, resolvida por .exists()
            mock_filter.assert_called_once()
            mock_qs.exists.assert_called_once()
            assert mock_filter.call_args.kwargs['processo'] is processo

    def test_sem_avaliador_ativo_retorna_false(self):
        processo = self._processo()
        mock_qs = MagicMock()
        mock_qs.exists.return_value = False
        with patch('rsc.models.ProcessoAvaliador.objects.filter', return_value=mock_qs):
            assert processo.tem_algum_avaliador_ativo() is False

    def test_filtra_pelos_status_de_avaliador_ativo(self):
        processo = self._processo()
        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        with patch('rsc.models.ProcessoAvaliador.objects.filter', return_value=mock_qs) as mock_filter:
            processo.tem_algum_avaliador_ativo()
            assert set(mock_filter.call_args.kwargs['status__in']) == {
                ProcessoAvaliador.AGUARDANDO_ACEITE,
                ProcessoAvaliador.EM_AVALIACAO,
                ProcessoAvaliador.AVALIACAO_FINALIZADA,
            }


class TestDashboardHelpers:
    def test_parse_data_limite_valido(self):
        assert dashboard._parse_data_limite('10/06/2026') == datetime.date(2026, 6, 10)

    def test_parse_data_limite_invalido(self):
        assert dashboard._parse_data_limite('xx') is None
        assert dashboard._parse_data_limite(None) is None

    def test_dias_restantes_futuro(self):
        pa = MagicMock()
        futuro = datetime.date.today() + datetime.timedelta(days=5)
        pa.data_limite.return_value = futuro.strftime('%d/%m/%Y')
        assert dashboard.dias_restantes(pa) == 5

    def test_dias_restantes_excecao_retorna_none(self):
        pa = MagicMock()
        pa.data_limite.side_effect = Exception('sem data_convite')
        assert dashboard.dias_restantes(pa) is None

    def test_contagem_para_meses(self):
        dados = dashboard._contagem_para_meses({1: 3, 12: 5})
        assert len(dados) == 12
        assert dados[0] == ['Jan', 3]
        assert dados[5] == ['Jun', 0]
        assert dados[11] == ['Dez', 5]

    def test_situacao_para_dados_ignora_zeros(self):
        contagem = {ProcessoRSC.STATUS_APROVADO: 2, ProcessoRSC.STATUS_EM_AVALIACAO: 4, ProcessoRSC.STATUS_REPROVADO: 0}
        dados = dashboard._situacao_para_dados(contagem)
        labels = [item[0] for item in dados]
        assert len(dados) == 2
        assert 'Deferido' in labels
        assert 'Em avaliação' in labels
        assert all(item[1] > 0 for item in dados)


class TestAplicarCampoArquivo:
    def test_qtd_valida(self):
        a = SimpleNamespace()
        assert _aplicar_campo_arquivo(a, 'qtd', '5') is True
        assert a.qtd_itens == 5

    def test_qtd_vazia_ignora(self):
        a = SimpleNamespace(qtd_itens=9)
        assert _aplicar_campo_arquivo(a, 'qtd', '') is False
        assert a.qtd_itens == 9

    def test_qtd_invalida_ignora(self):
        a = SimpleNamespace(qtd_itens=9)
        assert _aplicar_campo_arquivo(a, 'qtd', 'abc') is False
        assert a.qtd_itens == 9

    def test_data_valida(self):
        a = SimpleNamespace()
        assert _aplicar_campo_arquivo(a, 'data', '2020-03-01') is True
        assert a.data_referencia == datetime.date(2020, 3, 1)

    def test_data_invalida_ignora(self):
        a = SimpleNamespace(data_referencia=None)
        assert _aplicar_campo_arquivo(a, 'data', '2020-13-99') is False
        assert a.data_referencia is None

    def test_descricao_preenchida(self):
        a = SimpleNamespace()
        assert _aplicar_campo_arquivo(a, 'descricao', 'texto') is True
        assert a.descricao == 'texto'

    def test_descricao_so_espacos_ignora(self):
        a = SimpleNamespace(descricao='antigo')
        assert _aplicar_campo_arquivo(a, 'descricao', '   ') is False
        assert a.descricao == 'antigo'

    def test_nota_valida(self):
        a = SimpleNamespace()
        assert _aplicar_campo_arquivo(a, 'nota', '12.5') is True
        assert a.nota_pretendida == 12.5

    def test_campo_desconhecido_ignora(self):
        a = SimpleNamespace()
        assert _aplicar_campo_arquivo(a, 'xpto', 'v') is False


class TestSalvarProcessoRscTolerante:
    def _post(self, data):
        req = RequestFactory().post('/', data)
        req.user = MagicMock()
        return req

    def test_descricao_vazia_nao_derruba_salvamento(self):
        processo = MagicMock()
        processo.avaliado_pode_editar.return_value = True
        processo.avaliado_pode_ajustar.return_value = False
        processo.get_data_referencia_retroativa.return_value = None
        dados = {
            'introducao_relatorio_descritivo': '',
            'conclusao_relatorio_descritivo': '',
            'itinerario_formacao_txt': '',
            'atuacao_docente_txt': '',
            'producao_cademica_txt': '',
            'prestacao_servicos_txt': '',
            'atividade_adm_txt': '',
            'titulos_homenagens_txt': '',
            'rsc1': '',
            'rsc2': '',
            'rsc3': '',
            'Arquivo_3_descricao': '',  # vazia: não pode mais derrubar o salvamento
        }
        arquivo = MagicMock()
        arquivo.pk = 3
        req = self._post(dados)
        with (
            patch('rsc.views.get_object_or_404', return_value=processo),
            patch('rsc.views.soh_dono'),
            patch('rsc.views.is_ajax', return_value=True),
            patch('rsc.views.Arquivo.objects.filter', return_value=[arquivo]),
        ):
            resp = views.salvar_processo_rsc(req, 1)
        assert json.loads(resp.content)['ok'] is True
        arquivo.save.assert_not_called()  # descrição vazia é ignorada, sem gravar

    def test_campo_preenchido_persiste_no_loop_tolerante(self):
        processo = MagicMock()
        processo.avaliado_pode_editar.return_value = True
        processo.avaliado_pode_ajustar.return_value = False
        processo.get_data_referencia_retroativa.return_value = None
        arquivo = MagicMock()
        arquivo.pk = 7
        dados = {
            'introducao_relatorio_descritivo': '',
            'conclusao_relatorio_descritivo': '',
            'itinerario_formacao_txt': '',
            'atuacao_docente_txt': '',
            'producao_cademica_txt': '',
            'prestacao_servicos_txt': '',
            'atividade_adm_txt': '',
            'titulos_homenagens_txt': '',
            'rsc1': '',
            'rsc2': '',
            'rsc3': '',
            'Arquivo_7_qtd': '5',  # preenchido: deve ser aplicado e persistido
        }
        req = self._post(dados)
        with (
            patch('rsc.views.get_object_or_404', return_value=processo),
            patch('rsc.views.soh_dono'),
            patch('rsc.views.is_ajax', return_value=True),
            patch('rsc.views.Arquivo.objects.filter', return_value=[arquivo]),
        ):
            resp = views.salvar_processo_rsc(req, 1)
        assert json.loads(resp.content)['ok'] is True
        assert arquivo.qtd_itens == 5
        arquivo.save.assert_called()
        assert arquivo.qtd_itens == 5
        arquivo.save.assert_called()


class TestSalvarArquivoRsc:
    def _arquivo(self):
        arq = MagicMock()
        arq.id = 7
        arq.criterio.fator = 2
        arq.criterio.diretriz.peso = 3
        arq.processo.avaliado_pode_editar.return_value = True
        arq.processo.avaliado_pode_ajustar.return_value = False
        arq.processo.get_data_referencia_retroativa.return_value = None
        return arq

    def _req(self, dados):
        req = RequestFactory().post('/', dados)
        req.user = MagicMock()
        return req

    def test_arquivo_completo_salva_e_retorna_pontuacao(self):
        arq = self._arquivo()
        req = self._req({'Arquivo_7_qtd': '5', 'Arquivo_7_data': '2020-01-01', 'Arquivo_7_descricao': 'ok'})
        with patch('rsc.views.Arquivo.objects.get', return_value=arq), patch('rsc.views.soh_dono'):
            resp = views.salvar_arquivo_rsc(req, 'enc')
        out = json.loads(resp.content)
        assert out['ok'] is True
        assert out['pontuacao_arquivo'] == '30'  # 5 * 2 * 3
        arq.save.assert_called_once()

    def test_campo_faltando_retorna_erro_sem_salvar(self):
        arq = self._arquivo()
        req = self._req({'Arquivo_7_qtd': '5', 'Arquivo_7_data': '2020-01-01'})  # sem descrição
        with patch('rsc.views.Arquivo.objects.get', return_value=arq), patch('rsc.views.soh_dono'):
            resp = views.salvar_arquivo_rsc(req, 'enc')
        assert json.loads(resp.content)['ok'] is False
        arq.save.assert_not_called()

    def test_processo_ja_enviado_bloqueia(self):
        arq = self._arquivo()
        arq.processo.avaliado_pode_editar.return_value = False
        arq.processo.avaliado_pode_ajustar.return_value = False
        req = self._req({'Arquivo_7_qtd': '5', 'Arquivo_7_data': '2020-01-01', 'Arquivo_7_descricao': 'ok'})
        with patch('rsc.views.Arquivo.objects.get', return_value=arq), patch('rsc.views.soh_dono'):
            resp = views.salvar_arquivo_rsc(req, 'enc')
        assert json.loads(resp.content)['ok'] is False
        arq.save.assert_not_called()

    def test_metodo_get_nao_permitido(self):
        req = RequestFactory().get('/')
        req.user = MagicMock()
        resp = views.salvar_arquivo_rsc(req, 'enc')
        assert resp.status_code == 405


class TestArquivoTemErro:
    def _arquivo(self, qtd=1, data='2020-01-01', descricao='memorial', fator=2, nota=6):
        return SimpleNamespace(
            qtd_itens=qtd,
            data_referencia=data,
            descricao=descricao,
            nota_pretendida=nota,
            criterio=SimpleNamespace(fator=fator),
        )

    def _tem_erro(self, arquivo):
        return Arquivo.tem_erro.fget(arquivo)

    def test_item_completo_nao_tem_erro(self):
        assert self._tem_erro(self._arquivo()) is False

    def test_sem_quantidade_tem_erro(self):
        assert self._tem_erro(self._arquivo(qtd=None)) is True

    def test_sem_data_referencia_tem_erro(self):
        assert self._tem_erro(self._arquivo(data=None)) is True

    def test_descricao_vazia_tem_erro(self):
        assert self._tem_erro(self._arquivo(descricao='')) is True

    def test_descricao_so_espacos_tem_erro(self):
        assert self._tem_erro(self._arquivo(descricao='   ')) is True

    def test_sem_fator_tem_erro(self):
        assert self._tem_erro(self._arquivo(fator=None)) is True

    def test_sem_nota_pretendida_tem_erro(self):
        assert self._tem_erro(self._arquivo(nota=None)) is True
