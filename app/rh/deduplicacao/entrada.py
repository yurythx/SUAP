"""Entrada de dados de pessoa física: obter ou criar pela identidade civil (CPF/passaporte).

Único caminho para criar PessoaFisica: spec 2026-10-07-deduplicacao-pessoa-fisica-design.md, seção 3.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from rh.deduplicacao.documentos import (
    chave_passaporte,
    cpf_valido,
    digitos,
    formatar_cpf,
    formatar_passaporte,
    passaporte_valido,
    recusar_documento_invalido,
    recusar_pais_sem_iso,
)

if TYPE_CHECKING:
    from comum.models import Pais
    from rh.models import PessoaFisica

MENSAGEM_OUTRA_PESSOA = 'CPF/passaporte já cadastrado para outra pessoa (data de nascimento diferente). Procure a secretaria acadêmica ou o RH.'
MENSAGEM_PASSAPORTE_OUTRA_PESSOA = 'Passaporte já pertence a outra pessoa'
MENSAGEM_CPF_DE_OUTRA_PESSOA = 'Já existe uma pessoa física com este CPF.'


class Politica(StrEnum):
    AUTORITATIVA = 'autoritativa'
    CAUTELOSA = 'cautelosa'
    PREENCHER = 'preencher'


class DocumentoDeOutraPessoa(ValidationError):
    """O documento informado já pertence a uma pessoa com outra data de nascimento."""


class PassaporteDeOutraPessoa(DocumentoDeOutraPessoa):
    """O par passaporte+país informado com um CPF já pertence a uma pessoa com outro CPF."""


def chave_prioridade(pf: Any) -> tuple[bool, bool, bool, int]:
    """Ordem de sobrevivência; exige um objeto vindo de ``PessoaFisica.objects.com_prioridade()``."""
    return (pf.servidor_ativo, pf.aluno_ativo, pf.prestador_ativo, pf.pk)


def _vazio(valor: Any) -> bool:
    return valor is None or valor == ''


VALIDADORES_DE_DOCUMENTO = {'cpf': cpf_valido, 'passaporte': passaporte_valido}


def _sem_valor(campo: str, valor: Any) -> bool:
    """Vazio, ou documento inválido: lixo que a higiene anula não é gravado por nenhuma política (nem a do SIAPE)."""
    return _vazio(valor) or (campo in VALIDADORES_DE_DOCUMENTO and not VALIDADORES_DE_DOCUMENTO[campo](valor))


def _como_data(valor: Any) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        return date.fromisoformat(valor[:10]) if valor else None
    return valor


def nascimento_diverge(atual: Any, informado: Any) -> bool:
    atual, informado = _como_data(atual), _como_data(informado)
    return atual is not None and informado is not None and atual != informado


def iso_pais(dados: Mapping[str, Any]) -> str | None:
    """ISO 3166-1 alfa-3 do país de ``dados`` (``pais_origem`` ou ``pais_origem_id``); ``None`` sem país ou com o alfa-3 vazio."""
    if dados.get('pais_origem') is not None:
        return dados['pais_origem'].iso_alfa3 or None
    if dados.get('pais_origem_id'):
        from comum.models import Pais

        return Pais.objects.filter(pk=dados['pais_origem_id']).values_list('iso_alfa3', flat=True).first() or None
    return None


def _maior_prioridade(filtro: Q) -> PessoaFisica | None:
    from rh.models import PessoaFisica

    return max(PessoaFisica.objects.com_prioridade().filter(filtro), key=chave_prioridade, default=None)


def _filtro_par(passaporte: str | None, iso: str | None) -> Q | None:
    """O par pela chave ou pelo ISO do país: junta os códigos do SIAPE de um mesmo alfa-3 (a Suíça é 150 e 236)."""
    chave = chave_passaporte(passaporte, iso)
    if not chave or not passaporte_valido(passaporte):
        return None
    return Q(documento_identificador=chave) | Q(passaporte__iexact=formatar_passaporte(passaporte), pais_origem__iso_alfa3=iso)


def _recusar_par_de_outra_pessoa(par: Q, cpf: str, escolhida: PessoaFisica | None) -> None:
    """O par passaporte+país não pode ficar em duas PFs: recusa se outra PF, que não a ``escolhida`` (a usada ou, sem ela, a criada), o tem.

    PF com o mesmo CPF em outro formato é a mesma pessoa (o ``planejar`` a mescla pelo CPF), não outra.
    """
    from rh.models import PessoaFisica

    outras = PessoaFisica.objects.filter(par).exclude(pk=escolhida.pk if escolhida else None).values_list('cpf', flat=True)
    if any(digitos(outro) != digitos(cpf) for outro in outras):
        raise PassaporteDeOutraPessoa(MENSAGEM_PASSAPORTE_OUTRA_PESSOA)


def buscar_existente(cpf: str | None, passaporte: str | None, iso: str | None = None) -> PessoaFisica | None:
    """A PF dona do documento (CPF, ou passaporte + ISO do país); com duplicata legada, a de maior prioridade.

    Com CPF, só ele identifica (como no ``planejar``): o par passaporte+país só reusa a PF **sem** CPF, o estrangeiro
    que ganhou CPF. O par que já é de qualquer outra PF (com outro CPF ou sem CPF) é de outra pessoa: ``PassaporteDeOutraPessoa``.
    Documento inválido nunca casa: é lixo que a higiene anula, não identidade.
    """
    cpf = cpf if cpf_valido(cpf) else None
    par = _filtro_par(passaporte, iso)
    if not cpf:
        return _maior_prioridade(par) if par else None
    pf = _maior_prioridade(Q(cpf__in={cpf, digitos(cpf)}) | Q(documento_identificador=cpf))
    if par:
        pf = pf or _maior_prioridade(par & (Q(cpf__isnull=True) | Q(cpf='')))
        _recusar_par_de_outra_pessoa(par, cpf, pf)
    return pf


def _registrar_divergencia(pf: PessoaFisica, campo: str, valor_original: str, motivo: str) -> None:
    from rh.models import DeduplicacaoPessoa

    DeduplicacaoPessoa.objects.create(
        pf_id=pf.pk,
        documento=pf.documento_identificador or '',
        acao=DeduplicacaoPessoa.DIVERGENCIA_ENTRADA,
        campo=campo,
        valor_original=valor_original,
        motivo=motivo,
        aplicado_em=timezone.now(),
    )


CAMPOS_DE_DOCUMENTO = frozenset({'cpf', 'passaporte', 'pais_origem', 'pais_origem_id'})


def tem_documento_valido(pf: PessoaFisica) -> bool:
    return cpf_valido(pf.cpf) or (passaporte_valido(pf.passaporte) and pf.pais_origem_id is not None)


def aplicar_politica(pf: PessoaFisica, dados: Mapping[str, Any], politica: Politica, preservar_documento: bool = False) -> None:
    """Aplica ``dados`` em ``pf`` (sem salvar) conforme a política. Nunca grava valor vazio nem CPF/passaporte inválido.

    ``preservar_documento``: o "próprio cadastro" que não é o SIAPE (acadêmico, planilhas, prestador, externa) não troca
    CPF, passaporte nem país da PF que já tem documento válido. Depois da deduplicação a PF pode ser compartilhada com o
    servidor; a troca de documento fica com o SIAPE e com o formulário de PF (``clean_cpf``).

    Nenhuma política grava documento que já é de outra PF (na Release 2 seria ``IntegrityError``): o SIAPE (autoritativa
    sem ``preservar_documento``) mantém o atual e audita; as demais recusam antes de alterar a PF.
    """
    conferir_politica(pf, dados, politica, preservar_documento)
    novos = _valores_a_gravar(pf, dados, politica, preservar_documento)
    for campo, recebido, dona in _documentos_de_outra_pessoa(pf, novos):  # só o SIAPE chega aqui: as demais já recusaram
        _registrar_divergencia(pf, campo, recebido, f'documento informado pela fonte pertence à PF {dona}; não aplicado')
        for removido in CAMPOS_DO_PAR if campo == 'passaporte' else ('cpf',):
            novos.pop(removido, None)
    informado = dados.get('nascimento_data')
    if politica == Politica.AUTORITATIVA and nascimento_diverge(pf.nascimento_data, informado):
        _registrar_divergencia(pf, 'nascimento_data', str(pf.nascimento_data), f'Fonte autoritativa informou {_como_data(informado)}')
    for campo, valor in novos.items():
        setattr(pf, campo, valor)


def conferir_politica(pf: PessoaFisica, dados: Mapping[str, Any], politica: Politica, preservar_documento: bool = False) -> None:
    """As recusas de ``aplicar_politica``, sem alterar nem auditar nada: para o ``clean()`` de formulário e a validação de linha.

    O SIAPE (autoritativa sem ``preservar_documento``) nunca recusa; as demais recusam o documento que já é de outra PF, e a
    cautelosa recusa também o nascimento divergente.
    """
    if politica == Politica.AUTORITATIVA and not preservar_documento:
        return
    for campo, _recebido, _dona in _documentos_de_outra_pessoa(pf, _valores_a_gravar(pf, dados, politica, preservar_documento)):
        raise PassaporteDeOutraPessoa(MENSAGEM_PASSAPORTE_OUTRA_PESSOA) if campo == 'passaporte' else DocumentoDeOutraPessoa(MENSAGEM_OUTRA_PESSOA)
    if politica == Politica.CAUTELOSA and nascimento_diverge(pf.nascimento_data, dados.get('nascimento_data')):
        raise DocumentoDeOutraPessoa(MENSAGEM_OUTRA_PESSOA)


def recusar_cadastro_de_prestador(form: Any) -> None:
    """``clean()`` dos formulários que salvam por ``PrestadorServico.update_or_create``: a recusa vira erro do campo, não 500.

    Lê do ``cleaned_data`` os campos de documento com os nomes usados por esses formulários (``cpf``, ``passaporte``,
    ``pais_origem``, ``nacionalidade``, ``nascimento_data``); sem CPF nem passaporte, não há o que conferir.
    """
    from comum.models import PrestadorServico

    campos = ('cpf', 'passaporte', 'pais_origem', 'nacionalidade', 'nascimento_data')
    dados = {campo: form.cleaned_data[campo] for campo in campos if form.cleaned_data.get(campo) not in (None, '')}
    if not (dados.get('cpf') or dados.get('passaporte')):
        return
    try:
        PrestadorServico.verificar_cadastro(dados)
    except DocumentoDeOutraPessoa as erro:
        campo = 'passaporte' if isinstance(erro, PassaporteDeOutraPessoa) else 'cpf'
        form.add_error(campo if campo in form.fields else None, erro)


def _valores_a_gravar(pf: PessoaFisica, dados: Mapping[str, Any], politica: Politica, preservar_documento: bool) -> dict[str, Any]:
    travados = CAMPOS_DE_DOCUMENTO if preservar_documento and tem_documento_valido(pf) else frozenset()
    return {
        campo: valor
        for campo, valor in dados.items()
        if not (campo in travados or _sem_valor(campo, valor) or (politica == Politica.PREENCHER and not _vazio(getattr(pf, campo, None))))
    }


CAMPOS_DO_PAR = ('passaporte', 'pais_origem', 'pais_origem_id')


def dona_do_cpf(cpf: str | None, excluir_pk: int | None) -> int | None:
    """A PF, que não a ``excluir_pk``, que já tem o CPF (formatado ou só com os dígitos); ``None`` se nenhuma."""
    from rh.models import PessoaFisica

    return PessoaFisica.objects.filter(cpf__in={formatar_cpf(cpf), digitos(cpf)}).exclude(pk=excluir_pk).values_list('pk', flat=True).first()


def _documentos_de_outra_pessoa(pf: PessoaFisica, novos: Mapping[str, Any]) -> list[tuple[str, str, int]]:
    """``(campo, documento recebido, PF dona)`` de cada documento de ``novos`` que troca o da ``pf`` por um que já é de outra PF.

    Só a troca conta, e a PF com o mesmo CPF (em outro formato) é a mesma pessoa, como em ``_recusar_par_de_outra_pessoa``:
    a duplicata legada não é de outra pessoa até o ``planejar`` mesclá-las.
    """
    conflitos = []
    if 'cpf' in novos and digitos(novos['cpf']) != digitos(pf.cpf) and (dona := dona_do_cpf(novos['cpf'], pf.pk)):
        conflitos.append(('cpf', formatar_cpf(novos['cpf']), dona))
    if novos.keys() & set(CAMPOS_DO_PAR):
        passaporte = formatar_passaporte(novos.get('passaporte', pf.passaporte))
        pais = novos.get('pais_origem') or novos.get('pais_origem_id') or pf.pais_origem_id
        pais_id = getattr(pais, 'pk', pais)
        if (passaporte, pais_id) != (formatar_passaporte(pf.passaporte), pf.pais_origem_id):
            cpf = novos.get('cpf', pf.cpf)
            if dona := _dona_do_par(passaporte, pais_id, pf.pk, digitos(cpf) if cpf_valido(cpf) else None):
                conflitos.append(('passaporte', passaporte, dona))
    return conflitos


def _dona_do_par(passaporte: str | None, pais_id: int | None, excluir_pk: int | None, digitos_do_cpf: str | None) -> int | None:
    """A PF, que não a ``excluir_pk`` nem uma com o mesmo CPF, que já tem o par país + passaporte; ``None`` se nenhuma."""
    from rh.models import PessoaFisica

    donas = PessoaFisica.objects.filter(filtro_par_passaporte(passaporte, pais_id)).exclude(pk=excluir_pk).values_list('pk', 'cpf')
    return next((pk for pk, cpf in donas if not digitos_do_cpf or digitos(cpf) != digitos_do_cpf), None)


def verificar_documento(*, cpf: str | None = None, passaporte: str | None = None, pais: Any = None, nascimento_data: Any = None) -> None:
    """Sem escrita, para o ``clean()`` de formulário: recusa documento de pessoa com outro nascimento, e o país sem ISO de quem não tem CPF."""
    cpf, passaporte, iso = formatar_cpf(cpf), formatar_passaporte(passaporte), iso_pais({'pais_origem': pais})
    recusar_pais_sem_iso(cpf, passaporte, pais is not None, iso)
    pf = buscar_existente(cpf, passaporte, iso)
    if pf is not None and nascimento_diverge(pf.nascimento_data, nascimento_data):
        raise DocumentoDeOutraPessoa(MENSAGEM_OUTRA_PESSOA)


NENHUM = Q(pk__in=[])


def _mesmo_pais(pais: Pais | int, prefixo: str) -> Q:
    """Mesmo país pelo ISO 3166-1 alfa-3 (junta os códigos do SIAPE de um mesmo alfa-3: a Suíça é 150 e 236); sem ISO, pela FK."""
    iso = iso_pais({'pais_origem': pais} if hasattr(pais, 'iso_alfa3') else {'pais_origem_id': pais})
    return Q(**{f'{prefixo}pais_origem__iso_alfa3': iso}) if iso else Q(**{f'{prefixo}pais_origem': pais})


def filtro_par_passaporte(passaporte: str | None, pais: Pais | int | None, prefixo: str = '') -> Q:
    """Para ANEXAR a uma pessoa existente: só o par passaporte + país; sem país, não casa ninguém.

    O país casa pelo ISO 3166-1 alfa-3 (junta os códigos do SIAPE de um mesmo alfa-3: a Suíça é 150 e 236); o país sem ISO,
    que não forma documento, casa pela FK. ``pais`` é o ``Pais`` ou o id dele.
    """
    numero = formatar_passaporte(passaporte)
    if not numero or not pais:
        return NENHUM
    return Q(**{f'{prefixo}passaporte__iexact': numero}) & _mesmo_pais(pais, prefixo)


def filtro_mesma_pessoa_por_passaporte(pessoa: PessoaFisica, prefixo: str = '') -> Q:
    """A própria PF e as que têm o par passaporte+país dela (duplicata que o ``planejar`` ainda não mesclou); nunca só o número."""
    return Q(**{f'{prefixo}pk': pessoa.pk}) | filtro_par_passaporte(pessoa.passaporte, pessoa.pais_origem_id, prefixo)


def travar_documentos_na_edicao(form: Any, pessoa: PessoaFisica) -> None:
    """Na edição, CPF, passaporte, país e nacionalidade ficam somente leitura: trocar o documento (ou o que decide qual
    documento vale) de um cadastro criaria outra pessoa.

    País e nacionalidade vazios podem ser completados: é o que tira o legado do ``SEMPAIS-`` (o cadastro dele é reusado,
    ver ``PrestadorServico.matricula_do_passaporte``). Quem valida lê o valor por ``form[campo].value()``: campo
    somente leitura não vem no POST.
    """
    from djtools.forms import ReadOnlyField

    travados = {'cpf': ('CPF', pessoa.cpf, pessoa.cpf), 'passaporte': ('Nº do Passaporte', pessoa.passaporte, pessoa.passaporte)}
    if pessoa.pais_origem_id:
        travados['pais_origem'] = ('País de Origem', pessoa.pais_origem, pessoa.pais_origem)
    if pessoa.nacionalidade:
        travados['nacionalidade'] = ('Nacionalidade', pessoa.nacionalidade, pessoa.get_nacionalidade_display())
    for campo, (rotulo, valor, exibido) in travados.items():
        form.fields[campo] = ReadOnlyField(label=rotulo, initial=valor)
        form.fields[campo].widget.display_value = exibido or '-'


def recusar_passaporte_de_outra_pessoa(form: Any, cpf: str | None, passaporte: str | None, pais: Pais | None, campo: str = 'passaporte') -> None:
    """Antecipa como erro do campo passaporte a recusa do ``obter_ou_criar``: sem CPF, passaporte inválido ou país sem
    ISO 3166-1 alfa-3; com CPF, o par já é de uma pessoa com outro CPF.

    Só na criação: na edição, o ``update_or_create`` do prestador acha a PF pelo usuário do próprio papel, sem buscar pelo documento.
    """
    if getattr(form.instance, 'pk', None):
        return
    cpf, passaporte, iso = formatar_cpf(cpf), formatar_passaporte(passaporte), iso_pais({'pais_origem': pais})
    try:
        if not cpf:  # com CPF, o passaporte inválido só não é gravado
            recusar_documento_invalido(None, passaporte)
        recusar_pais_sem_iso(cpf, passaporte, pais is not None, iso)
        buscar_existente(cpf, passaporte, iso)
    except ValidationError as erro:  # o passaporte inválido, o país sem ISO, ou PassaporteDeOutraPessoa
        form.add_error(campo, erro.messages)


def recusar_documento_de_outra_pessoa(form: Any, campo_cpf: str, cpf: str | None, nascimento_data: Any) -> None:
    """Antecipa como erro do campo CPF do formulário a recusa que o ``save()`` levantaria: CPF de pessoa com outro nascimento."""
    try:
        verificar_documento(cpf=cpf, nascimento_data=nascimento_data)
    except DocumentoDeOutraPessoa as erro:
        form.add_error(campo_cpf, erro.messages)


def _documentos_da_entrada(dados: Mapping[str, Any]) -> dict[str, Any]:
    """CPF/passaporte formatados; documento inválido é recusado, mesmo que uma PF legada o tenha (ela não é dona dele).

    Com CPF válido, o passaporte inválido só não é gravado: a higiene o anularia e a próxima entrada o regravaria.
    """
    cpf, passaporte = formatar_cpf(dados.get('cpf')), formatar_passaporte(dados.get('passaporte'))
    recusar_documento_invalido(cpf, passaporte)
    return {**dados, 'cpf': cpf, 'passaporte': passaporte if passaporte_valido(passaporte) else None}


def obter_ou_criar(dados: Mapping[str, Any], politica: Politica) -> tuple[PessoaFisica, bool]:
    """Obtém a PF dona do CPF/passaporte de ``dados`` (aplicando a política) ou a cria."""
    dados = _documentos_da_entrada(dados)
    iso = iso_pais(dados)
    recusar_pais_sem_iso(dados['cpf'], dados['passaporte'], bool(dados.get('pais_origem') or dados.get('pais_origem_id')), iso)
    chaves = [chave for chave in (dados['cpf'], chave_passaporte(dados['passaporte'], iso)) if chave]
    if not chaves:
        raise ValidationError('Informe o CPF, ou o passaporte e o país de origem da pessoa.')
    # ponytail: lock de sessão por documento, liberado ao fim de cada chamada: num import com milhares de pessoas dentro de
    # uma transação longa, o pg_advisory_xact_lock só sairia no COMMIT e estouraria a tabela de locks do servidor.
    # Lock e unlock ficam na mesma transação (mesma conexão no pgbouncer em modo transação). Teto: dentro de uma transação
    # externa, outra sessão só vê a PF criada aqui no COMMIT dela; a corrida rara gera duplicata, que o próximo planejar
    # resolve (na Release 2, a UNIQUE recusa). Lock por transação curta só se a duplicata virar problema medido.
    with transaction.atomic():
        travadas: list[int] = []
        try:
            for trava in _travas_em_ordem(chaves):
                # savepoint: a falha ao travar (lock_timeout, cancelamento) não aborta a transação, e as já travadas são soltas
                with transaction.atomic():
                    _executar_trava('pg_advisory_lock', trava)
                travadas.append(trava)
            with transaction.atomic():
                return _obter_ou_criar_travado(dados, politica, iso)
        finally:
            # needs_rollback: o rollback do savepoint falhou (conexão caiu); o unlock levantaria e encobriria o erro original,
            # e o servidor solta os locks de sessão ao derrubar o backend
            if not connection.needs_rollback:
                for trava in travadas:
                    _executar_trava('pg_advisory_unlock', trava)


def _travas_em_ordem(chaves: list[str]) -> list[int]:
    """Os ids dos locks, na ordem do próprio id (sem deadlock nem com colisão de hash entre chaves diferentes)."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT DISTINCT hashtext(chave) FROM unnest(%s::text[]) chave ORDER BY 1', [chaves])
        return [trava for (trava,) in cursor.fetchall()]


def _executar_trava(funcao: str, trava: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT {funcao}(%s)', [trava])


def _obter_ou_criar_travado(dados: dict[str, Any], politica: Politica, iso: str | None) -> tuple[PessoaFisica, bool]:
    from rh.models import PessoaFisica

    pf = buscar_existente(dados['cpf'], dados['passaporte'], iso)
    criada = pf is None
    if criada:
        # setattr simples: um default não vazio do model (False, 0) não pode barrar o valor informado
        pf = PessoaFisica()
        for campo, valor in dados.items():
            if not _vazio(valor):
                setattr(pf, campo, valor)
    else:
        aplicar_politica(pf, dados, politica)
    pf.save()
    return pf, criada
