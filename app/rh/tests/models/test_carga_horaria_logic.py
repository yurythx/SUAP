from rh.models import CargaHorariaReduzida, HorarioSemanal, JornadaTrabalho, Servidor


class TestFormatCh:
    """Testes para o método estático CargaHorariaReduzida.format_ch."""

    def test_inteiro_40_retorna_40_00(self):
        """Horas inteiras (40.0) → '40:00'."""
        assert CargaHorariaReduzida.format_ch(40.0) == '40:00'

    def test_meia_hora_retorna_40_30(self):
        """Horas com meia hora (40.5) → '40:30'."""
        assert CargaHorariaReduzida.format_ch(40.5) == '40:30'

    def test_valor_pequeno_0_5_retorna_0_30(self):
        """Valor pequeno (0.5) → '0:30'."""
        assert CargaHorariaReduzida.format_ch(0.5) == '0:30'

    def test_zero_retorna_0_00(self):
        """Zero (0.0) → '0:00'."""
        assert CargaHorariaReduzida.format_ch(0.0) == '0:00'

    def test_negativo_retorna_0_00(self):
        """Valor negativo → '0:00' (apenas positivos são formatados)."""
        assert CargaHorariaReduzida.format_ch(-1.0) == '0:00'

    def test_minutos_um_digito_8_25_retorna_8_15(self):
        """Valor com minutos de um dígito (8.25) → '8:15'."""
        assert CargaHorariaReduzida.format_ch(8.25) == '8:15'

    def test_minutos_zero_8_0_retorna_8_00(self):
        """Valor com minutos zero (8.0) → '8:00'."""
        assert CargaHorariaReduzida.format_ch(8.0) == '8:00'

    def test_muito_pequeno_5_min_retorna_0_05(self):
        """Valor muito pequeno (~5 min) → '0:05'."""
        assert CargaHorariaReduzida.format_ch(0.08333) == '0:05'


class TestHorarioSemanalFormatCh:
    """Testes para as propriedades format_ch de HorarioSemanal."""

    def test_seg_format_ch_40_retorna_40_00(self):
        """seg=40.0 → seg_format_ch == '40:00'."""
        horario = HorarioSemanal(seg=40.0, ter=0, qua=0, qui=0, sex=0, jornada_semanal='0')
        assert horario.seg_format_ch == '40:00'

    def test_ter_format_ch_38_5_retorna_38_30(self):
        """ter=38.5 → ter_format_ch == '38:30'."""
        horario = HorarioSemanal(seg=0, ter=38.5, qua=0, qui=0, sex=0, jornada_semanal='0')
        assert horario.ter_format_ch == '38:30'

    def test_jornada_semanal_format_ch_40_retorna_40_00(self):
        """jornada_semanal='40' → jornada_semanal_format_ch == '40:00'."""
        horario = HorarioSemanal(seg=0, ter=0, qua=0, qui=0, sex=0, jornada_semanal='40')
        assert horario.jornada_semanal_format_ch == '40:00'


class TestCargaHorariaDisponivelChoice:
    """Testes para CargaHorariaReduzida.get_carga_horaria_disponivel_choice (teto semanal pela jornada do servidor)."""

    @staticmethod
    def _maximo(nome_jornada: str) -> float:
        processo = CargaHorariaReduzida(servidor=Servidor(jornada_trabalho=JornadaTrabalho(nome=nome_jornada)))
        return processo.get_carga_horaria_disponivel_choice()[-1][0]

    def test_jornada_conhecida_usa_o_teto_dela(self):
        """'30 HORAS SEMANAIS' → teto de 30h semanais."""
        assert self._maximo('30 HORAS SEMANAIS') == 30.0

    def test_jornada_fora_da_lista_assume_40h_em_vez_de_estourar(self):
        """Nome de jornada desconhecido não pode levantar TypeError (None * 5): assume 40h semanais."""
        assert self._maximo('JORNADA FORA DA LISTA') == 40.0
