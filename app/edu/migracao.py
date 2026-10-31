from __future__ import annotations

import abc
import csv
import datetime
import io
import os
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from comum.models import PessoaFisica
from djtools.models import Task
from djtools.utils import text_to_int
from edu.models import (
    Aluno,
    Componente,
    ComponenteCurricular,
    CursoCampus,
    Diretoria,
    Matriz,
    SituacaoMatricula,
)
from edu.models.cadastros_gerais import SituacaoMatriculaPeriodo
from edu.models.atividades import AtividadeCurricularExtensao
from edu.models.historico import (
    MatriculaDiario,
    MatriculaPeriodo,
    RegistroHistorico,
)
from edu.models.procedimentos import AproveitamentoComponente, ProcedimentoMatricula
from rh.deduplicacao.entrada import Politica, aplicar_politica, conferir_politica, verificar_documento
from rh.deduplicacao.paises import pais_do_aluno
from edu.validators import (
    validar_alunos,
    validar_componentes,
    validar_cursos,
    validar_equivalencia,
    validar_historico_aluno,
    validar_matricula,
    validar_matrizes,
    validar_procedimento_matricula,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

T = TypeVar('T')


@dataclass
class ResultadoMigracao:
    """Resultado estruturado de uma operação de validação ou importação de migração."""

    sucesso: bool
    total_processados: int
    total_validos: int
    erros: list[str] = field(default_factory=list)
    mensagem: str = ''
    arquivo_erros: str | None = None


class ProgressHandler(abc.ABC):
    """Interface abstrata para controle de progresso e log de migração."""

    @abc.abstractmethod
    def set_total(self, total: int) -> None:
        """Define o total de etapas do progresso."""

    @abc.abstractmethod
    def iterate(self, iterable: Iterable[T]) -> Iterable[T]:
        """Itera sobre a coleção atualizando o progresso a cada item."""

    @abc.abstractmethod
    def update_progress(self, step: int) -> None:
        """Avança o progresso em um número de etapas."""

    @abc.abstractmethod
    def add_log(self, message: str) -> None:
        """Registra mensagem de log da operação."""

    @abc.abstractmethod
    def finalize(
        self,
        message: str,
        redirect_url: str = '..',
        file_path: str | None = None,
        error: bool = False,
    ) -> None:
        """Finaliza a tarefa com mensagem de status e arquivo opcional."""


class TaskProgressHandler(ProgressHandler):
    """Adaptador de progresso para tarefas assíncronas do Celery/djtools."""

    def __init__(self, task: Any) -> None:
        self.task = task

    def set_total(self, total: int) -> None:
        if self.task and hasattr(self.task, 'pk'):
            Task.objects.filter(pk=self.task.pk).update(total=total)

    def iterate(self, iterable: Iterable[T]) -> Iterable[T]:
        if self.task and hasattr(self.task, 'iterate'):
            return self.task.iterate(iterable)
        return iterable

    def update_progress(self, step: int) -> None:
        if self.task and hasattr(self.task, 'update_progress'):
            self.task.update_progress(step)

    def add_log(self, message: str) -> None:
        if self.task and hasattr(self.task, 'add_log'):
            self.task.add_log(message)

    def finalize(
        self,
        message: str,
        redirect_url: str = '..',
        file_path: str | None = None,
        error: bool = False,
    ) -> None:
        if self.task and hasattr(self.task, 'finalize'):
            if file_path is not None or error:
                self.task.finalize(message, redirect_url, file_path=file_path, error=error)
            else:
                self.task.finalize(message, redirect_url)


class ConsoleProgressHandler(ProgressHandler):
    """Adaptador de progresso para execução via linha de comando (terminal/CLI)."""

    def __init__(self, stdout: Any = None, stderr: Any = None, style: Any = None) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.style = style
        self.total = 0
        self.corrente = 0

    def set_total(self, total: int) -> None:
        self.total = total
        self.corrente = 0

    def iterate(self, iterable: Iterable[T]) -> Iterable[T]:
        for item in iterable:
            self.corrente += 1
            if self.stdout and self.total > 0 and self.corrente % 50 == 0:
                self.stdout.write(f'  Progresso: {self.corrente}/{self.total} itens processados...')
            yield item

    def update_progress(self, step: int) -> None:
        self.corrente = step

    def add_log(self, message: str) -> None:
        if self.stdout:
            self.stdout.write(message)

    def finalize(
        self,
        message: str,
        redirect_url: str = '..',
        file_path: str | None = None,
        error: bool = False,
    ) -> None:
        if error:
            if self.stderr:
                msg = self.style.ERROR(message) if self.style else message
                self.stderr.write(msg)
                if file_path:
                    self.stderr.write(f'Relatório de erros gerado em: {file_path}')
        else:
            if self.stdout:
                msg = self.style.SUCCESS(message) if self.style else message
                self.stdout.write(msg)


class SilentProgressHandler(ProgressHandler):
    """Adaptador de progresso silencioso (usado em testes ou execuções batch sem output)."""

    def __init__(self) -> None:
        self.logs: list[str] = []
        self.final_message: str = ''
        self.file_path: str | None = None
        self.error: bool = False

    def set_total(self, total: int) -> None:
        pass

    def iterate(self, iterable: Iterable[T]) -> Iterable[T]:
        return iterable

    def update_progress(self, step: int) -> None:
        pass

    def add_log(self, message: str) -> None:
        self.logs.append(message)

    def finalize(
        self,
        message: str,
        redirect_url: str = '..',
        file_path: str | None = None,
        error: bool = False,
    ) -> None:
        self.final_message = message
        self.file_path = file_path
        self.error = error


class ImportacaoCSVBase:
    """Classe base do serviço de importação e validação de CSV."""

    def __init__(
        self,
        fonte_csv: str | io.StringIO | io.TextIOBase,
        apenas_validar: bool = False,
        ignorar_obrigatorios: bool = False,
        task: Any | None = None,
        progress: ProgressHandler | None = None,
    ) -> None:
        self.fonte_csv = fonte_csv
        self.apenas_validar = apenas_validar
        self.ignorar_obrigatorios = ignorar_obrigatorios
        self.task = task
        if progress is None and task is not None:
            self.progress: ProgressHandler = TaskProgressHandler(task)
        else:
            self.progress = progress or SilentProgressHandler()
        self.erros: list[str] = []
        self.registros_validos: list[dict[str, Any]] = []
        self.registros_temp: dict[str, Any] = {}
        self.total: int = 0

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        raise NotImplementedError('Subclasses devem implementar validar_linha')

    def processar_registro_temporario(self, linha: dict[str, str], registro: dict[str, Any]) -> None:
        pass

    def importar(self) -> None:
        raise NotImplementedError('Subclasses devem implementar importar')

    def obter_linhas(self) -> list[dict[str, str]]:
        """Carrega e lê as linhas do CSV a partir de string de conteúdo ou caminho de arquivo."""
        conteudo_stream: io.StringIO | io.TextIOBase
        if isinstance(self.fonte_csv, str):
            if os.path.exists(self.fonte_csv) and os.path.isfile(self.fonte_csv):
                with open(self.fonte_csv, encoding='utf-8-sig', errors='replace') as arq:
                    return list(csv.DictReader(arq, delimiter=';'))
            conteudo_stream = io.StringIO(self.fonte_csv)
        else:
            conteudo_stream = self.fonte_csv
        return list(csv.DictReader(conteudo_stream, delimiter=';'))

    def processar_linhas(self, reader: list[dict[str, str]]) -> None:
        count = 0
        for linha in self.progress.iterate(reader):
            count += 1
            registro, erros_linha = self.validar_linha(linha, self.ignorar_obrigatorios)
            if erros_linha:
                self.erros.extend([f'Linha {count}: {erro}' for erro in erros_linha])
            elif registro is not None:
                self.processar_registro_temporario(linha, registro)
                self.registros_validos.append(registro)

    def _gerar_arquivo_erros(self) -> str:
        temp_dir = getattr(settings, 'TEMP_DIR', tempfile.gettempdir())
        output = tempfile.NamedTemporaryFile(mode='w', dir=temp_dir, delete=False, suffix='.txt')
        output.write('\r\n'.join(self.erros))
        output.close()
        return output.name

    def run(self) -> ResultadoMigracao:
        reader = self.obter_linhas()
        self.total = len(reader)
        if not self.apenas_validar:
            self.total = (self.total * 2) + 1
        self.progress.set_total(self.total)

        self.processar_linhas(reader)

        if self.erros:
            arquivo_erros = self._gerar_arquivo_erros()
            msg = 'Erros de validação foram encontrados no processamento do arquivo informado.'
            self.progress.finalize(msg, '..', file_path=arquivo_erros, error=True)
            return ResultadoMigracao(
                sucesso=False,
                total_processados=len(reader),
                total_validos=0,
                erros=self.erros,
                mensagem=msg,
                arquivo_erros=arquivo_erros,
            )

        if self.apenas_validar:
            msg = f'{len(self.registros_validos)} registros validados com sucesso.'
            self.progress.finalize(msg, '..')
            return ResultadoMigracao(
                sucesso=True,
                total_processados=len(reader),
                total_validos=len(self.registros_validos),
                erros=[],
                mensagem=msg,
            )

        self.importar()
        msg = f'{len(self.registros_validos)} registros criados/atualizados com sucesso.'
        self.progress.finalize(msg, '..')
        return ResultadoMigracao(
            sucesso=True,
            total_processados=len(reader),
            total_validos=len(self.registros_validos),
            erros=[],
            mensagem=msg,
        )


class ImportadorMatrizes(ImportacaoCSVBase):
    """Importador de matrizes curriculares."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        return validar_matrizes(linha, ignorar_obrigatorios)

    def processar_registro_temporario(self, linha: dict[str, str], registro: dict[str, Any]) -> None:
        pass

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            for registro in self.progress.iterate(self.registros_validos):
                identificador = registro.pop('id', None)
                if identificador:
                    Matriz.objects.update_or_create(id=identificador, defaults=registro)
                else:
                    Matriz.objects.create(**registro)
            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e


def _calcular_ch_semanal_componente(registro: dict[str, Any]) -> tuple[int | None, int | None]:
    """Calcula a carga horária semanal (1s e 2s) de acordo com o número de avaliações."""
    qtd = registro.get('componentecurricular_qtd_avaliacoes')
    ch_creditos = registro.get('componente_ch_qtd_creditos') or 0
    ch_1s = registro.get('componentecurricular_ch_semanal_1s')
    ch_2s = registro.get('componentecurricular_ch_semanal_2s')
    segundo_sem = registro.get('componentecurricular_segundo_semestre')

    if qtd == 4 and (ch_1s is None or ch_2s is None):
        return ch_creditos // 2, ch_creditos // 2
    if qtd == 2:
        if segundo_sem:
            return None, ch_creditos
        return ch_creditos, None
    if qtd != 4:
        return ch_creditos, ch_creditos
    return ch_1s, ch_2s


class ImportadorComponentes(ImportacaoCSVBase):
    """Importador de componentes curriculares."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        return validar_componentes(linha, self.registros_temp, ignorar_obrigatorios)

    def processar_registro_temporario(self, linha: dict[str, str], registro: dict[str, Any]) -> None:
        self.registros_temp[linha['Componente.sigla_legado']] = registro

    def _criar_componente(self, registro: dict[str, Any], diretoria_id: int) -> Componente:
        defaults = {
            'descricao_historico': registro['componente_descricao'],
            'sigla_qacademico': registro.get('componente_sigla_legado', ''),
            'ativo': registro['componente_ativo'],
            'ch_qtd_creditos': registro.get('componente_ch_qtd_creditos', ''),
            'abreviatura': registro.get('componente_abreviatura', ''),
            'tipo_id': registro['componente_tipo_id'],
            'diretoria_id': diretoria_id,
        }
        componente, created = Componente.objects.update_or_create(
            descricao=registro['componente_descricao'],
            ch_hora_relogio=registro['componente_ch_hora_relogio'],
            ch_hora_aula=registro['componente_ch_hora_aula'],
            nivel_ensino_id=registro['componente_nivel_ensino_id'],
            observacao=registro['componente_observacao'],
            defaults=defaults,
        )
        if not created:
            componente.save()
        return componente

    def _criar_componente_curricular(self, componente: Componente, registro: dict[str, Any]) -> ComponenteCurricular:
        ch_1s, ch_2s = _calcular_ch_semanal_componente(registro)
        defaults = {
            'optativo': registro['componentecurricular_optativo'],
            'periodo_letivo': registro.get('componentecurricular_periodo'),
            'tipo': registro['componentecurricular_tipo_id'],
            'qtd_avaliacoes': registro['componentecurricular_qtd_avaliacoes'],
            'ch_presencial': registro['componentecurricular_ch_presencial'],
            'ch_pratica': registro['componentecurricular_ch_pratica'],
            'ch_extensao': registro['componentecurricular_ch_extensao'],
            'ch_pcc': registro['componentecurricular_ch_pcc'],
            'avaliacao_por_conceito': registro['componentecurricular_avaliacao_por_conceito'],
            'segundo_semestre': registro['componentecurricular_segundo_semestre'],
            'pode_fechar_pendencia': registro['componentecurricular_pode_fechar_pendencia'],
            'ch_semanal_1s': ch_1s,
            'ch_semanal_2s': ch_2s,
            'nucleo_id': registro['componentecurricular_nucleo_id'],
        }
        cc, _ = ComponenteCurricular.objects.update_or_create(componente=componente, matriz_id=registro['matriz_id'], defaults=defaults)
        return cc

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            dict_co_requisitos = {}
            dict_pre_requisitos = {}
            diretoria = Diretoria.objects.get(tipo=Diretoria.TIPO_SISTEMICA)
            for registro in self.progress.iterate(self.registros_validos):
                componente = self._criar_componente(registro, diretoria.id)
                cc = self._criar_componente_curricular(componente, registro)
                if registro.get('componentecurricular_co_requisitos'):
                    dict_co_requisitos[cc] = registro['componentecurricular_co_requisitos']
                if registro.get('componentecurricular_pre_requisitos'):
                    dict_pre_requisitos[cc] = registro['componentecurricular_pre_requisitos']

            for cc, co_requisitos in dict_co_requisitos.items():
                ccs = cc.matriz.componentecurricular_set.filter(componente__sigla_qacademico__in=co_requisitos)
                cc.co_requisitos.set(ccs)

            for cc, pre_requisitos in dict_pre_requisitos.items():
                ccs = cc.matriz.componentecurricular_set.filter(componente__sigla_qacademico__in=pre_requisitos)
                cc.pre_requisitos.set(ccs)

            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e


class ImportadorCursos(ImportacaoCSVBase):
    """Importador de cursos e vínculos com matrizes."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        return validar_cursos(linha, ignorar_obrigatorios)

    def processar_registro_temporario(self, linha: dict[str, str], registro: dict[str, Any]) -> None:
        pass

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            for registro in self.progress.iterate(self.registros_validos):
                codigo = registro['codigo']
                matrizes = registro.pop('matrizes', [])
                try:
                    curso_campus = CursoCampus.objects.get(codigo=codigo)
                    for key, value in registro.items():
                        setattr(curso_campus, key, value)
                    curso_campus.save()
                except CursoCampus.DoesNotExist:
                    curso_campus = CursoCampus.objects.create(**registro)
                curso_campus.matrizes.clear()
                for matriz_id in matrizes:
                    curso_campus.matrizes.add(matriz_id)
            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e


def _dados_pessoa_do_aluno(registro: dict[str, Any]) -> dict[str, Any]:
    """Dados da pessoa da linha, com o passaporte e o país que o CSV traz no registro do aluno (sem eles, o estrangeiro só com
    passaporte não tem documento). O país do aluno é edu.Pais; o da pessoa, comum.Pais: pelo nome ou pela sigla alfa-3, nunca pelo código."""
    from edu.models import Pais

    pais_aluno = Pais.objects.filter(pk=registro['pais_origem_id']).first() if registro.get('pais_origem_id') else None
    return {**registro.pop('PessoaFisica'), 'passaporte': registro.get('passaporte'), 'pais_origem': pais_do_aluno(pais_aluno)}


def _recusa_da_pessoa_do_aluno(registro: dict[str, Any]) -> str | None:
    """Sem escrita: a recusa que ``salvar_aluno`` levantaria para esta linha, como mensagem de erro de validação.

    Aluno existente: a planilha não dá à PF dele um documento que já é de outra pessoa. Aluno novo: a PF achada pelo
    documento não pode ter outro nascimento. Sem isto, a linha derrubava a importação inteira no meio (rollback).
    """
    dados = _dados_pessoa_do_aluno({**registro, 'PessoaFisica': dict(registro.get('PessoaFisica') or {})})  # cópia: o registro é gravado depois
    aluno = Aluno.objects.filter(matricula=registro.get('matricula')).first()
    try:
        if aluno:
            conferir_politica(aluno.pessoa_fisica, dados, Politica.AUTORITATIVA, preservar_documento=True)
        else:
            verificar_documento(
                cpf=dados.get('cpf'), passaporte=dados.get('passaporte'), pais=dados.get('pais_origem'), nascimento_data=dados.get('nascimento_data')
            )
    except ValidationError as erro:  # documento de outra pessoa, ou país sem ISO de quem não tem CPF
        return f'Aluno.matricula {registro.get("matricula")}: {erro.messages[0]}'
    return None


def salvar_aluno(registro: dict[str, Any]) -> Aluno:
    """Cria ou atualiza o aluno (e a pessoa física dele) de uma linha validada por ``validar_alunos``.

    Aluno novo reusa a pessoa física do documento (``obter_ou_criar``) em vez de criar outra; no aluno existente, a planilha é a
    fonte do próprio cadastro, mas não troca o documento da pessoa, que pode ser a do servidor depois da deduplicação.
    """
    aluno = Aluno.objects.filter(matricula=registro['matricula']).first()
    pessoa_fisica_data = _dados_pessoa_do_aluno(registro)
    email_notificacao = registro.get('email_qacademico') or ''
    deficiencias = registro.pop('deficiencias', [])
    outras_nees = registro.pop('outras_nees', [])

    if aluno:
        for key, value in registro.items():
            setattr(aluno, key, value)
        aluno.save()
        pessoa_fisica = aluno.pessoa_fisica
        aplicar_politica(pessoa_fisica, pessoa_fisica_data, Politica.AUTORITATIVA, preservar_documento=True)
        pessoa_fisica.save()
    else:
        pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(pessoa_fisica_data, Politica.CAUTELOSA)
        registro['pessoa_fisica_id'] = pessoa_fisica.id
        aluno = Aluno.objects.create(**registro)
        Aluno.objects.filter(id=aluno.id).update(data_matricula=registro['data_matricula'])

    aluno.deficiencias.set(deficiencias)
    aluno.outras_nees.set(outras_nees)

    v = aluno.get_vinculo()
    if v and email_notificacao:
        v.email_pessoal = email_notificacao
        v.save(update_fields=['email_pessoal'])
    return aluno


class ImportadorAlunos(ImportacaoCSVBase):
    """Importador de alunos, pessoas físicas, deficiências e vínculos."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        registro, erros = validar_alunos(linha, ignorar_obrigatorios)
        if registro and (recusa := _recusa_da_pessoa_do_aluno(registro)):  # junto com os demais erros da linha
            erros.append(recusa)
        return registro, erros

    def processar_registro_temporario(self, linha: dict[str, str], registro: dict[str, Any]) -> None:
        pass

    def _salvar_aluno_registro(self, registro: dict[str, Any]) -> None:
        salvar_aluno(registro)

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            for registro in self.progress.iterate(self.registros_validos):
                self._salvar_aluno_registro(registro)
            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e


class ImportadorHistoricoAluno(ImportacaoCSVBase):
    """Importador de histórico escolar de alunos."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        return validar_historico_aluno(linha, ignorar_obrigatorios)

    def _salvar_historico(self, registro: dict[str, Any]) -> None:
        aluno = Aluno.objects.get(pk=registro['aluno_id'])
        matricula_periodo_data = registro.pop('MatriculaPeriodo')
        ano_letivo_id = matricula_periodo_data.pop('ano_letivo_id')
        periodo_letivo = matricula_periodo_data.pop('periodo_letivo')
        matricula_periodo, _ = MatriculaPeriodo.objects.update_or_create(
            aluno=aluno,
            ano_letivo_id=ano_letivo_id,
            periodo_letivo=periodo_letivo,
            defaults=matricula_periodo_data,
        )

        registro_historico_data = registro.pop('RegistroHistorico')
        identificador_externo = text_to_int(registro_historico_data.pop('identificador_externo'))
        RegistroHistorico.objects.update_or_create(
            matricula_periodo=matricula_periodo,
            identificador_externo=identificador_externo,
            defaults=registro_historico_data,
        )

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            ids_alunos: list[int] = []
            for registro in self.progress.iterate(self.registros_validos):
                try:
                    self._salvar_historico(registro)
                    if registro['aluno_id'] not in ids_alunos:
                        ids_alunos.append(registro['aluno_id'])
                except Exception as e:
                    self.progress.add_log(f'Erro na linha {registro}: {e}')
                    raise

            Aluno.objects.filter(id__in=ids_alunos).update(data_integralizacao=datetime.datetime.now())
            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e


MAPA_PROCEDIMENTO_SITUACAO = {
    ProcedimentoMatricula.INTERCAMBIO: SituacaoMatriculaPeriodo.INTERCAMBIO,
    ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO: SituacaoMatriculaPeriodo.TRANCADA,
    ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO: SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
    ProcedimentoMatricula.CANCELAMENTO_COMPULSORIO: SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
    ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO: SituacaoMatriculaPeriodo.CANCELADA,
    ProcedimentoMatricula.CANCELAMENTO_POR_DUPLICIDADE: SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
    ProcedimentoMatricula.CANCELAMENTO_POR_DESLIGAMENTO: SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
    ProcedimentoMatricula.EVASAO: SituacaoMatriculaPeriodo.EVASAO,
    ProcedimentoMatricula.JUBILAMENTO: SituacaoMatriculaPeriodo.JUBILADO,
    ProcedimentoMatricula.TRANSFERENCIA_INTERCAMPUS: SituacaoMatriculaPeriodo.TRANSF_CURSO,
    ProcedimentoMatricula.TRANSFERENCIA_CURSO: SituacaoMatriculaPeriodo.TRANSF_CURSO,
    ProcedimentoMatricula.TRANSFERENCIA_EXTERNA: SituacaoMatriculaPeriodo.TRANSF_EXTERNA,
    ProcedimentoMatricula.MATRICULA_VINCULO: SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
    ProcedimentoMatricula.INTEGRALIZAR_ENSINO_MEDIO: SituacaoMatriculaPeriodo.INTEGRALIZADO_ENSINO_MEDIO,
    ProcedimentoMatricula.REINTEGRACAO: SituacaoMatriculaPeriodo.EM_ABERTO,
}


class ImportadorProcedimentoMatricula(ImportacaoCSVBase):
    """Importador de procedimentos de matrícula."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        return validar_procedimento_matricula(linha)

    def _salvar_procedimento(self, registro: dict[str, Any]) -> None:
        aluno = Aluno.objects.get(pk=registro['aluno_id'])
        procedimento_matricula_data = registro.pop('ProcedimentoMatricula')
        matricula_periodo_data = registro.pop('MatriculaPeriodo')

        tipo = procedimento_matricula_data['tipo']
        matricula_periodo_data['situacao_id'] = MAPA_PROCEDIMENTO_SITUACAO.get(tipo)

        ano_letivo_id = matricula_periodo_data.pop('ano_letivo_id')
        periodo_letivo = matricula_periodo_data.pop('periodo_letivo')
        matricula_periodo, _ = MatriculaPeriodo.objects.update_or_create(
            aluno=aluno,
            ano_letivo_id=ano_letivo_id,
            periodo_letivo=periodo_letivo,
            defaults=matricula_periodo_data,
        )

        identificador_externo = text_to_int(procedimento_matricula_data.pop('identificador_externo'))
        ProcedimentoMatricula.objects.update_or_create(
            matricula_periodo=matricula_periodo,
            identificador_externo=identificador_externo,
            defaults=procedimento_matricula_data,
        )

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            for registro in self.progress.iterate(self.registros_validos):
                try:
                    self._salvar_procedimento(registro)
                except Exception as e:
                    self.progress.add_log(f'Erro na linha {registro}: {e}')
                    raise
            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e


class ImportadorEquivalencia(ImportacaoCSVBase):
    """Importador de equivalências de componentes curriculares."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        return validar_equivalencia(linha)

    def _salvar_equivalencia(self, registro: dict[str, Any]) -> None:
        aluno = Aluno.objects.get(pk=registro['aluno_id'])
        componente_curricular_id = registro.pop('componente_currricular_id')
        matricula_periodo_data = registro.pop('MatriculaPeriodo')

        ano_letivo_id = matricula_periodo_data.pop('ano_letivo_id')
        periodo_letivo = matricula_periodo_data.pop('periodo_letivo')
        matricula_periodo, _ = MatriculaPeriodo.objects.get_or_create(
            aluno=aluno,
            ano_letivo_id=ano_letivo_id,
            periodo_letivo=periodo_letivo,
            defaults=matricula_periodo_data,
        )

        registros_historico = registro.get('registros_historico', [])
        if registros_historico:
            aproveitamento, _ = AproveitamentoComponente.objects.get_or_create(
                matricula_periodo=matricula_periodo,
                componente_curricular_id=componente_curricular_id,
            )
            for rh in registros_historico:
                aproveitamento.registros_historico.add(rh)

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            for registro in self.progress.iterate(self.registros_validos):
                try:
                    self._salvar_equivalencia(registro)
                except Exception as e:
                    self.progress.add_log(f'Erro na linha {registro}: {e}')
                    raise
            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e


class ImportadorInicializarPeriodoLetivo(ImportacaoCSVBase):
    """Inicializador de período letivo de alunos."""

    def validar_linha(self, linha: dict[str, str], ignorar_obrigatorios: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
        return validar_matricula(linha)

    def _registrar_extensao(self, aluno: Aluno) -> None:
        situacoes_aprovadas = [
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
            MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
        ]
        comp_ext = aluno.matriz.componentecurricular_set.filter(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO).values_list(
            'componente_id', flat=True
        )

        for rh in RegistroHistorico.objects.filter(
            matricula_periodo__aluno_id=aluno.id,
            componente_id__in=comp_ext,
            situacao__in=situacoes_aprovadas,
        ):
            AtividadeCurricularExtensao.registrar(
                aluno, type(rh), rh.pk, rh.componente.ch_hora_relogio, rh.componente.descricao_historico, True, True, rh.matricula_periodo
            )

        outros_comp = (
            aluno.matriz.componentecurricular_set.filter(ch_extensao__gt=0)
            .exclude(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO)
            .values_list('componente_id', flat=True)
        )
        cc_map = {cc.componente_id: cc for cc in aluno.matriz.componentecurricular_set.all()}
        for rh in RegistroHistorico.objects.filter(
            matricula_periodo__aluno_id=aluno.id,
            componente_id__in=outros_comp,
            situacao__in=situacoes_aprovadas,
        ):
            cc = cc_map.get(rh.componente_id)
            AtividadeCurricularExtensao.registrar(
                aluno, type(rh), rh.pk, cc.ch_extensao if cc else 0, rh.componente.descricao_historico, True, True, rh.matricula_periodo
            )

    def _processar_aluno(self, registro: dict[str, Any]) -> None:
        aluno = Aluno.objects.get(pk=registro['aluno_id'])
        aluno.recalcular_periodo_matriz_periodos_letivos()

        situacoes_ativas = [
            SituacaoMatricula.MATRICULADO,
            SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
            SituacaoMatricula.TRANCADO,
            SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
        ]
        if aluno.situacao_id in situacoes_ativas:
            mp = aluno.get_ultima_matricula_periodo()
            if mp and mp.situacao_id != SituacaoMatriculaPeriodo.EM_ABERTO:
                mp.instanciar_proxima_matricula_periodo()

        if aluno.situacao_id not in [SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO]:
            aluno.atualizar_pendencias()
            if aluno.situacao_id in [SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL]:
                aluno.situacao_id = aluno.get_situacao_id()
            aluno.save()

        aluno.calcular_indice_rendimento()
        aluno.atualizar_periodo_referencia()
        aluno.atualizar_percentual_ch_cumprida()
        aluno.ultima_operacao = 'Inicializar período letivo'
        aluno.save()

        self._registrar_extensao(aluno)

    def importar(self) -> None:
        sid = transaction.savepoint()
        try:
            for registro in self.progress.iterate(self.registros_validos):
                try:
                    self._processar_aluno(registro)
                except Exception as e:
                    self.progress.add_log(f'Erro na linha {registro}: {e}')
                    raise
            transaction.savepoint_commit(sid)
            self.progress.update_progress(self.total)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise e
