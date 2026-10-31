from __future__ import annotations

import argparse
import ast
import logging
import tokenize
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def check_file(filename: str) -> int:
    try:
        with open(filename, 'rb') as f:
            ast.parse(f.read(), filename=filename)
    except SyntaxError:
        # Syntax nova do Python (ex.: type aliases do 3.12+) pode não ser
        # reconhecida pelo interpretador que executa o pre-commit. Nesse caso,
        # apenas emitimos um aviso e seguimos com a checagem via tokenize,
        # que não depende de syntax nova.
        logger.debug(f'{filename} - ast.parse falhou (possível syntax mais nova que o interpretador atual)')

    lines = []
    with tokenize.open(filename) as f:
        tokens = tokenize.generate_tokens(f.readline)
        line = None
        for token in tokens:
            # next token after finding statement
            # should come before the line should be changed
            if line:
                # if comment found at the same line, ignore statement
                if token.start[0] == line.start[0] and token.type == 61 and token.string == '# NOQA':
                    line = None
                    continue

                # next line from import with no previous comment
                if token.start[0] > line.start[0]:
                    lines.append(line)
                    line = None
                    continue
            # statement found
            if token.string == 'print' and token.type == 1:
                line = token
                continue

    for line in lines:
        logger.warning(f'{filename}:{line.start[0]}:{line.start[1]}: {line.string} found')

    return int(bool(lines))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', nargs='*', help='Filenames to run')
    args = parser.parse_args(argv)

    retv = 0
    for filename in args.filenames:
        if filename.endswith('.py') and not filename.startswith('.'):
            retv |= check_file(filename)
    return retv


if __name__ == '__main__':
    raise SystemExit(main())
