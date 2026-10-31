"""Libsass compiler for django-pipeline.

Speedups development and/or production when compiling sass assets. No need of
ruby sass anymore.
"""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import sass
from django.conf import settings
from pipeline.compilers import CompilerBase


class LibSassCompiler(CompilerBase):
    """Compiler that uses libsass."""

    output_extension = 'css'

    def match_file(self, filename: str) -> bool:
        """Check files extension to use them."""
        return filename.endswith(('.scss', '.sass'))

    def compile_file(self, infile: str, outfile: str, outdated: bool = False, force: bool = False) -> None:
        """Compila o sass e troca o ``outfile`` atomicamente.

        Não reescreve se o css estiver em dia: requests concorrentes (live_server com threads, várias
        suítes no mesmo checkout) liam o ``outfile`` truncado quando ele era aberto com ``'w'`` a cada compilação.
        """
        if not (outdated or force or self._parcial_mais_nova(infile, outfile)):
            return
        css = sass.compile(filename=infile) if settings.DEBUG else sass.compile(filename=infile, output_style='compressed')
        # Prefixo '.': sobra de uma falha fica fora do collectstatic (ignora '.*').
        with NamedTemporaryFile('w', encoding='utf-8', dir=os.path.dirname(outfile), prefix='.', suffix='.tmp', delete=False) as tmp:
            try:
                tmp.write(css)
            except BaseException:
                os.remove(tmp.name)
                raise
        os.chmod(tmp.name, 0o644)  # NamedTemporaryFile cria 0600; o open(..., 'w') antigo herdava 0644 da umask.
        os.replace(tmp.name, outfile)

    @staticmethod
    def _parcial_mais_nova(infile: str, outfile: str) -> bool:
        """Indica se algum ``.scss``/``.sass`` importável pelo ``infile`` é mais novo que o ``outfile``.

        ``is_outdated`` do pipeline só olha o mtime do ``infile``; editar uma parcial (``variables.scss``) não recompilaria.
        """
        # ponytail: varre o diretório avô do infile, pois os imports sobem no máximo um nível ('../default/', '../themes/').
        # Import que suba mais que isso escapa da varredura; aí resolver os @import recursivamente.
        try:
            limite = os.path.getmtime(outfile)
        except OSError:
            return True
        raiz = Path(infile).resolve().parent.parent
        return any(fonte.stat().st_mtime > limite for fonte in raiz.rglob('*') if fonte.suffix in ('.scss', '.sass'))
