from collections import OrderedDict
from datetime import timedelta
from djtools.db import models


class PCA(models.ModelPlus):
    SEARCH_FIELDS = ['servidor__pessoa_fisica__nome', 'servidor__matricula']

    servidor = models.ForeignKeyPlus('rh.Servidor', null=False, blank=False, on_delete=models.CASCADE)
    servidor_matricula_crh = models.CharField(max_length=8, null=False, blank=False)  # CO-CRH-PCA - é o mesmo dado de rh.Servidor.matricula_crh
    servidor_vaga_pca = models.CharField(max_length=7, null=False, blank=False)  # CO-VAGA-SIAPE-PCA - é o mesmo dado de rh.Servidor.codigo_vaga
    # ligacao pca --> posicionamentos
    codigo_pca = models.CharField(
        max_length=11, null=False, blank=False, unique=True, db_index=True
    )  # CH-PCA - é o mesmo dado de rh.PosicionamentoPCA.codigo_pca_posicionamento
    # cargo
    cargo_pca = models.ForeignKeyPlus('rh.CargoEmprego', null=False, blank=False, on_delete=models.CASCADE)  # CH-CARGO-PCA

    # entrada
    forma_entrada_pca = models.ForeignKeyPlus(
        'rh.FormaProvimentoVacancia', related_name='forma_entrada', null=True, on_delete=models.CASCADE
    )  # CO-FORMA-ENTRADA-PCA
    data_entrada_pca = models.DateFieldPlus(null=False, blank=False, db_index=True)  # DA-ENTRADA-PCA
    texto_entrada_pca = models.CharField(max_length=60, blank=True)  # TX-ENTRADA-PCA
    # vacância
    forma_vacancia_pca = models.ForeignKeyPlus(
        'rh.FormaProvimentoVacancia', related_name='forma_vacancia', null=True, on_delete=models.CASCADE
    )  # CO-FORMA-VACANCIA-PCA
    data_vacancia_pca = models.DateFieldPlus(blank=True)  # DA-VACANCIA-PCA
    texto_vacancia_pca = models.CharField(max_length=60, blank=True)  # TX-VACANCIA-PCA

    class Meta:
        ordering = ['-data_entrada_pca']
        verbose_name = 'Provimento de Cargo'
        verbose_name_plural = 'Provimentos de Cargos'

    def __str__(self):
        return f'Provimento de Cargo {self.servidor} - {self.data_entrada_pca.strftime("%d/%m/%Y")}'

    @property
    def inicio_exercicio_pca(self):
        # retorna uma data
        data_inicio_exercicio_pca = None
        if self.posicionamentopca_set.all().exists():
            data_inicio_exercicio_pca = (
                self.posicionamentopca_set.all().order_by('data_inicio_posicionamento_pca')[0].data_inicio_posicionamento_pca
            )  # usa o posicionamento mais antigo (índice 0)
        if data_inicio_exercicio_pca and (data_inicio_exercicio_pca - self.data_entrada_pca).days <= 15:
            return data_inicio_exercicio_pca
        return self.data_entrada_pca

    @property
    def fim_exercicio_pca(self):
        # retorna uma data
        return self.data_vacancia_pca

    @property
    def fim_exercicio_pca_or_None(self):
        data_fim = self.fim_exercicio_pca
        if (data_fim is not None) and (data_fim.year == 2500):
            data_fim = None
        return data_fim

    def tempo_servico_interrompido_pca(self, data_referencia=None):
        tempo_servico = timedelta(0)
        for regime in self.regimejuridicopca_set.all().order_by('data_inicio_regime_juridico_pca'):
            tempo_servico += regime.tempo_servico_interrompido(data_referencia)
        return tempo_servico

    def tempo_servico_pca(self, ficto=False, data_referencia=None):
        tempo_servico = timedelta(0)
        data_inicio_exercicio_descontada = False
        for regime in self.regimejuridicopca_set.all().order_by('data_inicio_regime_juridico_pca'):
            tempo_servico += regime.tempo_servico(ficto, data_referencia)
            if not data_inicio_exercicio_descontada:
                if ficto:
                    # dedução proporcional ao fator do regime jurídico
                    tempo_servico -= timedelta(
                        (self.inicio_exercicio_pca - regime.data_inicio_regime_juridico_pca).days
                        * float(regime.valor_fator_tempo_regime_juridico_pca)
                    )
                else:
                    tempo_servico -= self.inicio_exercicio_pca - regime.data_inicio_regime_juridico_pca
                data_inicio_exercicio_descontada = True
        return tempo_servico  # um timedelta que representa o tempo de servico

    @classmethod
    def montar_timeline(cls, pcas):
        timeline = OrderedDict()
        for pca in pcas:
            if pca.data_entrada_pca:
                descricao_entrada_pca = f'<h4>Entrada no PCA</h4> <dl><dt>Forma entrada: </dt><dd>{pca.forma_entrada_pca}</dd><dt>Cargo: </dt><dd>{pca.cargo_pca}</dd></dl>'
                if timeline.get(pca.data_entrada_pca):
                    if timeline[pca.data_entrada_pca].get('eventos'):
                        evento = OrderedDict()
                        evento['descricao'] = descricao_entrada_pca
                        evento['css'] = 'success'
                        timeline[pca.data_entrada_pca]['eventos'].append(evento)
                    else:
                        evento = OrderedDict()
                        evento['descricao'] = descricao_entrada_pca
                        evento['css'] = 'success'
                        timeline[pca.data_entrada_pca]['eventos'] = [evento]
                    timeline[pca.data_entrada_pca]['css'] = 'success'

                else:
                    timeline[pca.data_entrada_pca] = OrderedDict()
                    timeline[pca.data_entrada_pca]['eventos'] = []
                    evento = OrderedDict()
                    evento['descricao'] = descricao_entrada_pca
                    evento['css'] = 'success'
                    timeline[pca.data_entrada_pca]['eventos'].append(evento)
                    timeline[pca.data_entrada_pca]['css'] = 'success'

            for jornada_trabalho in pca.jornadatrabalhopca_set.all().order_by('data_inicio_jornada_trabalho_pca'):
                horas_semanais = '-'
                if jornada_trabalho.qtde_jornada_trabalho_pca:
                    if jornada_trabalho.qtde_jornada_trabalho_pca == '99':
                        horas_semanais = 'Dedicação Exclusiva'
                    else:
                        horas_semanais = f'{jornada_trabalho.qtde_jornada_trabalho_pca} h'
                descricao_jornada_trabalho = f'<h4>Início Jornada de Trabalho</h4> <dl><dt>Horas Semanais:</dt><dd>{horas_semanais}</dd></dl>'
                evento = OrderedDict({'descricao': descricao_jornada_trabalho, 'css': 'extra'})

                if timeline.get(jornada_trabalho.data_inicio_jornada_trabalho_pca):
                    if timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca].get('eventos'):
                        timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca]['eventos'].append(evento)
                    else:
                        timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca]['eventos'] = [evento]
                else:
                    timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca] = OrderedDict()
                    timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca]['eventos'] = []
                    timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca]['eventos'].append(evento)

                if not timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca].get('css'):
                    timeline[jornada_trabalho.data_inicio_jornada_trabalho_pca]['css'] = 'info'

            for regime in pca.regimejuridicopca_set.all().order_by('data_inicio_regime_juridico_pca'):
                regime_desc = '-'
                regime_nome = 'Regime jurídico'
                valor_fator = regime.valor_fator_tempo_regime_juridico_pca
                if regime.regime_juridico:
                    regime_desc = regime.regime_juridico.sigla
                    regime_nome = regime.regime_juridico.nome.capitalize()

                descricao_regime = f'<h4>Início: {regime_nome} ({regime_desc})</h4> <dl><dt>Fator:</dt><dd>{valor_fator}</dd></dl>'
                evento = OrderedDict({'descricao': descricao_regime, 'css': 'alert'})
                if timeline.get(regime.data_inicio_regime_juridico_pca):
                    if timeline[regime.data_inicio_regime_juridico_pca].get('eventos'):
                        timeline[regime.data_inicio_regime_juridico_pca]['eventos'].append(evento)
                    else:
                        timeline[regime.data_inicio_regime_juridico_pca]['eventos'] = [evento]
                else:
                    timeline[regime.data_inicio_regime_juridico_pca] = OrderedDict()
                    timeline[regime.data_inicio_regime_juridico_pca]['eventos'] = []
                    timeline[regime.data_inicio_regime_juridico_pca]['eventos'].append(evento)

                if not timeline[regime.data_inicio_regime_juridico_pca].get('css'):
                    timeline[regime.data_inicio_regime_juridico_pca]['css'] = 'alert'

            for posicionamento in pca.posicionamentopca_set.all().order_by('data_inicio_posicionamento_pca'):
                subdescricao = ''
                if posicionamento.eh_capacitacao:
                    subdescricao = "<span class='obs'>Capacitação</span>"
                descricao = (
                    f'<h4>Início de Exercício</h4><p>{posicionamento.forma_entrada}</p>'
                    if posicionamento.forma_entrada.codigo in ['009', '128']
                    else f'<h4>Mudança de Posicionamento PCA</h4><p>{posicionamento.forma_entrada}</p>{subdescricao}'
                )
                evento = OrderedDict({'descricao': descricao, 'css': 'info'})

                if timeline.get(posicionamento.data_inicio_posicionamento_pca):
                    if timeline[posicionamento.data_inicio_posicionamento_pca].get('eventos'):
                        timeline[posicionamento.data_inicio_posicionamento_pca]['eventos'].append(evento)
                    else:
                        timeline[posicionamento.data_inicio_posicionamento_pca]['eventos'] = [evento]
                else:
                    timeline[posicionamento.data_inicio_posicionamento_pca] = OrderedDict()
                    timeline[posicionamento.data_inicio_posicionamento_pca]['eventos'] = []
                    timeline[posicionamento.data_inicio_posicionamento_pca]['eventos'].append(evento)

                if not timeline[posicionamento.data_inicio_posicionamento_pca].get('css'):
                    timeline[posicionamento.data_inicio_posicionamento_pca]['css'] = 'info'

            if pca.data_vacancia_pca and pca.data_vacancia_pca.year != 2500:
                descricao_vacancia_pca = f'<h4>Vacância no PCA</h4> <dl><dt>Forma vacância:</dt><dd>{pca.forma_vacancia_pca}</dd><dt>Cargo: </dt><dd>{pca.cargo_pca}</dd></dl>'
                if timeline.get(pca.data_vacancia_pca):
                    if timeline[pca.data_vacancia_pca].get('eventos'):
                        evento = OrderedDict()
                        evento['descricao'] = descricao_vacancia_pca
                        evento['css'] = 'error'
                        timeline[pca.data_vacancia_pca]['eventos'].append(evento)
                    else:
                        evento = OrderedDict()
                        evento['descricao'] = descricao_vacancia_pca
                        evento['css'] = 'error'
                        timeline[pca.data_vacancia_pca]['eventos'] = [evento]
                else:
                    timeline[pca.data_vacancia_pca] = OrderedDict()
                    timeline[pca.data_vacancia_pca]['eventos'] = []
                    evento = OrderedDict()
                    evento['descricao'] = descricao_vacancia_pca
                    evento['css'] = 'error'
                    timeline[pca.data_vacancia_pca]['eventos'].append(evento)

                timeline[pca.data_vacancia_pca]['css'] = 'error'
        timeline = sorted(timeline.items(), key=lambda x: x[0])
        return OrderedDict(timeline)
