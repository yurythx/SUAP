from __future__ import annotations

import re
from collections.abc import Sequence
import xlsxwriter


class XLSXCrosstabExporter:
    """
    Exporta uma lista de 'tabelas' (p.ex., instâncias de TabelaBidimensional)
    para um arquivo XLSX, criando uma guia por tabela.

    Cada tabela deve prover:
      - descricao: str
      - colunas: list[str]
      - registros: list[dict[int, object]]  # índices 0..N conforme cabeçalho

    Uso:
        exporter = XLSXCrosstabExporter([t1, t2, t3])
        with tempfile.NamedTemporaryFile(suffix='.xlsx', mode='w+b', delete=False) as tmp:
            exporter.write(tmp)  # grava no arquivo
            caminho = tmp.name
    """

    def __init__(self, tabelas: Sequence[object]):
        self.tabelas = list(tabelas)

    # --- sanitização e unicidade dos nomes de abas ---

    @staticmethod
    def _sanitize_sheet_name(name: str) -> str:
        # Excel não aceita: : \ / ? * [ ]
        # Limite de 31 caracteres.
        s = re.sub(r'[:\\/?*\[\]]', '-', (name or '').strip())
        s = s.replace('\n', ' ')
        return s[:31] or 'Tabela'

    def _unique_sheet_names(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for t in self.tabelas:
            base = self._sanitize_sheet_name(getattr(t, 'descricao', '') or 'Tabela')
            candidate = base
            i = 1
            while candidate in seen:
                suffix = f' ({i})'
                candidate = (base[: (31 - len(suffix))] + suffix)[:31]
                i += 1
            seen.add(candidate)
            result.append(candidate)
        return result

    # --- escrita do workbook ---

    def write(self, fileobj) -> None:
        """
        Grava o XLSX no file-like recebido (NamedTemporaryFile é aceito).
        """
        wb = xlsxwriter.Workbook(fileobj)

        fmt_header = wb.add_format({'bold': True, 'bg_color': '#F2F2F2', 'border': 1})
        fmt_cell = wb.add_format({'border': 1})

        sheet_names = self._unique_sheet_names()

        for tabela, sheet_name in zip(self.tabelas, sheet_names, strict=False):
            ws = wb.add_worksheet(sheet_name)

            colunas = list(getattr(tabela, 'colunas', []))
            registros = list(getattr(tabela, 'registros', []))

            # Cabeçalho
            for c, nome in enumerate(colunas):
                ws.write(0, c, nome, fmt_header)

            # Linhas (registros como dict indexado por inteiros 0..N)
            for r, reg in enumerate(registros, start=1):
                for c in range(len(colunas)):
                    ws.write(r, c, reg.get(c, ''), fmt_cell)

            # Largura automática simples (heurística)
            for c in range(len(colunas)):
                ws.set_column(c, c, 18)

        wb.close()
