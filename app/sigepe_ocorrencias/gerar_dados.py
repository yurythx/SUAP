from ponto.models import Frequencia
from datetime import datetime
import tqdm
import csv
import os
from django.conf import settings
from django.core.files import File
from pgd2.models import PlanoIndividualTrabalho, SolicitacaoAdesaoServidor
from sigepe_ocorrencias.models import PacoteOcorrenciaSigepe, OcorrenciaSigepe, RegistroAcaoSigepeOcorrencia
from comum.models import Configuracao, Vinculo
from sigepe_ocorrencias.utils import get_vinculos_servidores_com_aux_transporte_com_frequencia

import calendar


class GeracaoOcorrenciaSigepe:
    # https://suap.ifrn.edu.br/demandas/visualizar/2012/?tab=dod
    # https://suap.ifrn.edu.br/demandas/visualizar/2233/?tab=dod

    pacote_ocorrencia = None
    user = None

    TIPO_ARQUIVO_ENVIO = 1
    TIPO_ARQUIVO_REENVIO = 2

    def _get_conteudo_ocorrencias(self, atualizacao=False):
        conteudo = []
        ocorrencias = OcorrenciaSigepe.objects.filter(pacote_ocorrencia=self.pacote_ocorrencia).order_by('id')
        if atualizacao:
            ocorrencias = ocorrencias.filter(erro_envio__isnull=False)
        for dado in ocorrencias:
            conteudo.append(dado.get_linha_formato_csv_formato_lista(usa_serador=False))
        return conteudo

    def _get_relatorio_frequencia_dias(self, vinculo):
        data_inicio = datetime(self.pacote_ocorrencia.ano, self.pacote_ocorrencia.mes, 1).date()
        ultimo_dia = calendar.monthrange(self.pacote_ocorrencia.ano, self.pacote_ocorrencia.mes)[1]
        data_fim = datetime(self.pacote_ocorrencia.ano, self.pacote_ocorrencia.mes, ultimo_dia).date()

        relatorio_pessoa = Frequencia.relatorio_ponto_pessoa(
            vinculo=vinculo,
            data_ini=data_inicio,
            data_fim=data_fim,
            calcular_se_estah_no_pgd=False,
            trata_inconsistencias=False,
            trata_compensacoes=False,
            show_grafico=False,
        )

        return relatorio_pessoa.get('dias')

    def _gerar_ocorrencias_aux_transporte(self):
        try:
            vinculos = get_vinculos_servidores_com_aux_transporte_com_frequencia(self.pacote_ocorrencia.ano, self.pacote_ocorrencia.mes)
            ocorrencias_create = []
            for vinculo in tqdm.tqdm(vinculos):
                dias = self._get_relatorio_frequencia_dias(vinculo)
                for dia in dias:
                    tipo_ocorrencia = None

                    tem_registro_de_ponto = dia.get('horarios')
                    estah_no_pgd2_no_dia = SolicitacaoAdesaoServidor.estah_no_pgd_hoje(vinculo.relacionamento, dia.get('dia'))[0]
                    modalidade = PlanoIndividualTrabalho.get_modalidade_execucao_servidor_na_data(vinculo.relacionamento, dia.get('dia'))

                    # Só gera ocorrência para servidor que
                    # - Nao esta liberado do dia
                    # - E BATEU PONTO ou ESTÁ EM PGD
                    if not dia.get('liberado'):
                        if tem_registro_de_ponto or (estah_no_pgd2_no_dia and modalidade):
                            # Regras de cada ocorrência
                            # - https://www.gov.br/servidor/pt-br/acesso-a-informacao/gestao-de-pessoas/manual-de-procedimentos/manual-de-procedimentos-gestor-sigepe-ocorrencia-versao-9.pdf

                            # Ocorrência 1004: sem PGD, tem registro de ponto (deslocamento)
                            # - Deve ser utilizada por todos os agentes públicos que se deslocarem de sua
                            #   residência para os locais de trabalho, conforme previsto na IN SRT/MGI nº 71/2025.
                            if not estah_no_pgd2_no_dia and tem_registro_de_ponto:
                                tipo_ocorrencia = 1004

                            # Ocorrência 1005: com PGD, tem registro de ponto (deslocamento)
                            # - Deve ser utilizada por todos os agentes públicos que trabalham em qualquer modalidade de
                            #   PGD (Presencial, Teletrabalho Integral, Teletrabalho Parcial ou Exterior) e que se deslocarem
                            #   de sua residência para os locais de trabalho, conforme previsto na IN SRT/MGI nº 71/2025.
                            if not tipo_ocorrencia and (estah_no_pgd2_no_dia and modalidade and tem_registro_de_ponto):
                                tipo_ocorrencia = 1005

                            # Ocorrência 1002: com PGD, sem registro de ponto (para os TODOS os dias do mês que não tiver 1005)
                            # - Deve ser utilizada para registrar os dias de trabalho dos agentes públicos que aderiram ao
                            #   Programa de Gestão e Desempenho na modalidade de teletrabalho parcial(incluindo
                            #   teletrabalho por turno), realizando suas atividades de forma remota.
                            if not tipo_ocorrencia and (estah_no_pgd2_no_dia and modalidade == 2 and not tem_registro_de_ponto):
                                tipo_ocorrencia = 1002

                            if tipo_ocorrencia:
                                ocorrencia = OcorrenciaSigepe()
                                ocorrencia.pacote_ocorrencia = self.pacote_ocorrencia
                                ocorrencia.tem_auxilio_transporte_neste_dia = True
                                ocorrencia.vinculo = vinculo
                                ocorrencia.tipo_ocorrencia = tipo_ocorrencia
                                ocorrencia.tem_efeito_financeiro = 'SIM'
                                ocorrencia.data_inicio = dia.get('dia')
                                ocorrencia.data_fim = dia.get('dia')
                                ocorrencias_create.append(ocorrencia)

            if ocorrencias_create:
                OcorrenciaSigepe.objects.bulk_create(ocorrencias_create)

        except Exception as e:
            log = f'Erro no processamento da ocorrência de aux transporte: {e!s}'
            return False, log

        return True, None

    def _gerar_ocorrencias_pgd_exterior(self):
        try:
            servidores = SolicitacaoAdesaoServidor.get_servidores_em_pgd_exterior()
            for serv in tqdm.tqdm(servidores):
                data_inicio, data_fim = SolicitacaoAdesaoServidor.get_periodo_servidor_em_pgd_exterior(serv)
                ocorrencia = OcorrenciaSigepe()
                ocorrencia.pacote_ocorrencia = self.pacote_ocorrencia
                ocorrencia.tem_auxilio_transporte_neste_dia = False
                ocorrencia.vinculo = serv.get_vinculo()
                ocorrencia.tipo_ocorrencia = 1003
                ocorrencia.tem_efeito_financeiro = 'NÃO'
                ocorrencia.data_inicio = data_inicio
                ocorrencia.data_fim = data_fim
                ocorrencia.save()

        except Exception as e:
            log = f'Erro no processamento da ocorrência de pgd exterior: {e!s}'
            return False, log

        return True, None

    def _gerar_ocorrencias(self):
        gerado_com_sucesso, log = self._gerar_ocorrencias_aux_transporte()
        if not gerado_com_sucesso:
            return gerado_com_sucesso, log
        return self._gerar_ocorrencias_pgd_exterior()

    def _upload_arquivo(self, nome_arquivo):
        caminho_arquivo = os.path.join(settings.TEMP_DIR, nome_arquivo)
        with open(caminho_arquivo, 'rb') as arquivo:
            self.pacote_ocorrencia.arquivo_envio_nome = nome_arquivo
            self.pacote_ocorrencia.arquivo_envio_arquivo = File(arquivo, name=nome_arquivo)
            self.pacote_ocorrencia.save()

    def _gerar_arquivos_ocorrencias(self, atualizacao=False):
        nome_arquivo, log = '', ''
        try:
            conteudo = self._get_conteudo_ocorrencias(atualizacao=atualizacao)
            sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')

            nome_arquivo = f'{sigla_instituicao}_{self.pacote_ocorrencia.id}_{self.pacote_ocorrencia.mes}{self.pacote_ocorrencia.ano}_OCORRENCIAS.csv'
            caminho_arquivo = os.path.join(settings.TEMP_DIR, nome_arquivo)

            with open(caminho_arquivo, mode='w', newline='', encoding='utf-8') as arquivo:
                writer = csv.writer(arquivo, delimiter=';')
                writer.writerows(conteudo)

            self._upload_arquivo(nome_arquivo)

            if atualizacao:
                ocorrencias = OcorrenciaSigepe.objects.filter(pacote_ocorrencia=self.pacote_ocorrencia).order_by('id')
                ocorrencias = ocorrencias.filter(erro_envio__isnull=False)
                ocorrencias.update(erro_envio=None)

            return True, None
        except Exception as e:
            log = f'Erro na geração dos arquivos de ocorrência ({nome_arquivo}): {e!s}'

        return False, log

    def _gerar_arquivo_envio(self, atualizacao=False):
        try:
            if not atualizacao:
                # Apaga anteriores do pacote
                self.pacote_ocorrencia.arquivo_envio_nome = None
                self.pacote_ocorrencia.arquivo_envio_arquivo = None
                self.pacote_ocorrencia.arquivo_retorno_arquivo = None
                self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_GERAR_ARQUIVO_ENVIO
                self.pacote_ocorrencia.save()
                OcorrenciaSigepe.objects.filter(pacote_ocorrencia=self.pacote_ocorrencia).delete()
            else:
                self.pacote_ocorrencia.arquivo_envio_nome = None
                self.pacote_ocorrencia.arquivo_envio_arquivo = None
                self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_ATUALIZACAO_ARQUIVO_ENVIO
                self.pacote_ocorrencia.save()
                self._atualizar_ocorrencias()
                if not self._tem_erros():
                    self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.FINALIZADO
                    self.pacote_ocorrencia.save()
                    RegistroAcaoSigepeOcorrencia.registrar_acao(
                        pacote_ocorrencia=self.pacote_ocorrencia,
                        observacao='Pacote de ocorrências foi finalizado por não haver erros no último arquivo de retorno',
                        user=self.user,
                    )
                    return True

            # Gerar ocorrencias
            gerado_com_sucesso, log = self._gerar_ocorrencias()
            if gerado_com_sucesso:
                gerado_com_sucesso, log = self._gerar_arquivos_ocorrencias(atualizacao=atualizacao)
                if gerado_com_sucesso:
                    self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_ARQUIVO_RETORNO
                    obs_registro_acao = 'Ocorrências geradas'
                    if atualizacao:
                        self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_ARQUIVO_RETORNO
                        obs_registro_acao = 'Ocorrências atualizadas'
                    self.pacote_ocorrencia.save()
                    RegistroAcaoSigepeOcorrencia.registrar_acao(
                        pacote_ocorrencia=self.pacote_ocorrencia, observacao=obs_registro_acao, user=self.user
                    )

            if not gerado_com_sucesso:
                self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.CADASTRADO
                obs_registro_acao = f'Erro na geração das ocorrências: {log}'
                if atualizacao:
                    self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_ARQUIVO_RETORNO
                    obs_registro_acao = f'Erro na atualização das ocorrências: {log}'
                RegistroAcaoSigepeOcorrencia.registrar_acao(pacote_ocorrencia=self.pacote_ocorrencia, observacao=obs_registro_acao, user=self.user)
                self.pacote_ocorrencia.save()
        except Exception as e:
            self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.CADASTRADO
            obs_registro_acao = f'Erro na geração das ocorrências: {e!s}'
            if atualizacao:
                self.pacote_ocorrencia.situacao = PacoteOcorrenciaSigepe.AGUARDANDO_ARQUIVO_RETORNO
                obs_registro_acao = f'Erro na atualização das ocorrências: {e!s}'
            self.pacote_ocorrencia.save()
            RegistroAcaoSigepeOcorrencia.registrar_acao(pacote_ocorrencia=self.pacote_ocorrencia, observacao=obs_registro_acao, user=self.user)
        return True

    def _atualizar_ocorrencias(self):
        self._zerar_erros()
        path = self.pacote_ocorrencia.arquivo_retorno_arquivo.path
        with open(path) as f:
            lista_ocorrencias_atualizar = []
            reader = csv.reader(f, delimiter=';')
            for row in reader:
                retorno = row[-1]
                data_inicio = row[-3]
                data_fim = row[-2]
                matricula = row[1]
                if retorno != 'OK':
                    data_inicio = datetime.strptime(data_inicio, '%d/%m/%Y').date()
                    data_fim = datetime.strptime(data_fim, '%d/%m/%Y').date()
                    vinculo = Vinculo.objects.ativos().filter(tipo_relacionamento__model='servidor', user__username=matricula).first()
                    ocorrencia = OcorrenciaSigepe.objects.filter(
                        pacote_ocorrencia=self.pacote_ocorrencia, vinculo=vinculo, data_inicio=data_inicio, data_fim=data_fim
                    ).first()
                    ocorrencia.erro_envio = retorno
                    lista_ocorrencias_atualizar.append(ocorrencia)

            OcorrenciaSigepe.objects.bulk_update(lista_ocorrencias_atualizar, ['erro_envio'])

    def _zerar_erros(self):
        OcorrenciaSigepe.objects.filter(pacote_ocorrencia=self.pacote_ocorrencia).update(erro_envio=None)

    def _tem_erros(self):
        return OcorrenciaSigepe.objects.filter(pacote_ocorrencia=self.pacote_ocorrencia, erro_envio__isnull=False).exists()

    def gerar(self, pacote_ocorrencia, tipo_arquivo, user):
        self.user = user
        self.pacote_ocorrencia = pacote_ocorrencia
        if tipo_arquivo == self.TIPO_ARQUIVO_ENVIO:
            self._gerar_arquivo_envio()
        if tipo_arquivo == self.TIPO_ARQUIVO_REENVIO:
            self._gerar_arquivo_envio(atualizacao=True)
