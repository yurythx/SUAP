from __future__ import annotations

import logging

from copy import deepcopy
from datetime import date
from typing import TYPE_CHECKING
from xml.dom import minidom

from comum.models import PessoaFisica, Configuracao
from djtools.assincrono import task
from edu.models import (
    Aluno,
    CursoCampus,
    LinhaPesquisa,
    MatriculaPeriodo,
    SequencialMatricula,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turno,
    MatriculaDiario,
)
from processo_seletivo.models import Candidato, CandidatoVaga, Lista, OfertaVaga, OfertaVagaCurso, RotuloLista
from rh.deduplicacao.entrada import DocumentoDeOutraPessoa, Politica, aplicar_politica

if TYPE_CHECKING:
    from comum.models import Ano
    from djtools.models import Task
    from edu.models import Matriz
    from processo_seletivo.models import Edital

logger = logging.getLogger(__name__)


@task('Importar Edital')
def importar_edital(xml, edital, task=None):
    edital.salvar_arquivo_xml(xml)
    doc = minidom.parseString(xml)
    task.count(
        doc.getElementsByTagName('lista'),
        doc.getElementsByTagName('vaga'),
        doc.getElementsByTagName('candidato'),
        doc.getElementsByTagName('candidato-vaga'),
    )

    OfertaVaga.objects.filter(oferta_vaga_curso__edital=edital).update(qtd=0)

    for _lista in task.iterate(doc.getElementsByTagName('lista')):
        codigo = _lista.getElementsByTagName('codigo')[0].firstChild.nodeValue
        descricao = _lista.getElementsByTagName('descricao')[0].firstChild.nodeValue
        qs = Lista.objects.filter(codigo=codigo, edital=edital)
        if qs.exists():
            lista = qs[0]
        else:
            lista = Lista()
            lista.codigo = codigo
        lista.edital = edital
        lista.descricao = descricao
        lista.save()
        if not RotuloLista.objects.filter(nome=descricao).exists():
            RotuloLista.objects.create(nome=descricao)

    turnos = {}
    for turno in Turno.objects.all():
        turnos[turno.descricao.upper()] = turno

    # editais podem ser reimportados e se o contador não for reiniciado irá incrementar a cada re-importação
    OfertaVagaCurso.objects.filter(
        edital=edital,
    ).update(qtd_inscritos=0)
    for _vaga in task.iterate(doc.getElementsByTagName('vaga')):
        codigo_curso = _vaga.getElementsByTagName('codigo-curso')[0].firstChild.nodeValue
        codigo_linha_pesquisa = (
            _vaga.getElementsByTagName('linha-pesquisa')[0].firstChild and _vaga.getElementsByTagName('linha-pesquisa')[0].firstChild.nodeValue or 0
        )
        linha_pesquisa = LinhaPesquisa.objects.filter(pk=codigo_linha_pesquisa).first()
        curso_campus = CursoCampus.objects.get(codigo=codigo_curso)
        codigo_lista = _vaga.getElementsByTagName('codigo-lista')[0].firstChild.nodeValue
        turno = turnos.get(
            _vaga.getElementsByTagName('turno')[0].firstChild and str(_vaga.getElementsByTagName('turno')[0].firstChild.nodeValue).upper() or ''
        )
        qtd = int(_vaga.getElementsByTagName('quantidade')[0].firstChild.nodeValue)
        qtd_semestre_1 = (
            int(float(_vaga.getElementsByTagName('qtd-vagas-semestre-1')[0].firstChild.nodeValue))
            if _vaga.getElementsByTagName('qtd-vagas-semestre-1')
            else None
        )
        qtd_semestre_2 = (
            int(float(_vaga.getElementsByTagName('qtd-vagas-semestre-2')[0].firstChild.nodeValue))
            if _vaga.getElementsByTagName('qtd-vagas-semestre-2')
            else None
        )
        qtd_inscritos = int(
            _vaga.getElementsByTagName('numero-alunos')[0].firstChild and _vaga.getElementsByTagName('numero-alunos')[0].firstChild.nodeValue or 0
        )
        campus_polo = (
            _vaga.getElementsByTagName('campus-polo')
            and _vaga.getElementsByTagName('campus-polo')[0].firstChild
            and _vaga.getElementsByTagName('campus-polo')[0].firstChild.nodeValue
            or ''
        )
        qs_oferta_vaga_curso = OfertaVagaCurso.objects.filter(
            edital=edital, curso_campus__codigo=codigo_curso, turno=turno, campus_polo=campus_polo, linha_pesquisa=linha_pesquisa
        )

        if qs_oferta_vaga_curso.exists():
            oferta_vaga_curso = qs_oferta_vaga_curso[0]
        else:
            oferta_vaga_curso = OfertaVagaCurso()
            oferta_vaga_curso.edital = edital
            oferta_vaga_curso.curso_campus = curso_campus
            oferta_vaga_curso.turno = turno
            oferta_vaga_curso.campus_polo = campus_polo
        oferta_vaga_curso.linha_pesquisa = linha_pesquisa
        oferta_vaga_curso.qtd_inscritos += qtd_inscritos
        oferta_vaga_curso.save()
        qs = OfertaVaga.objects.filter(
            oferta_vaga_curso__edital=edital,
            oferta_vaga_curso__curso_campus__codigo=codigo_curso,
            lista__codigo=codigo_lista,
            oferta_vaga_curso__turno=turno,
            oferta_vaga_curso__campus_polo=campus_polo,
            oferta_vaga_curso__linha_pesquisa=linha_pesquisa,
        )

        if qs.exists():
            oferta_vaga = qs[0]
        else:
            oferta_vaga = OfertaVaga()
        oferta_vaga.oferta_vaga_curso = oferta_vaga_curso
        oferta_vaga.lista = Lista.objects.get(codigo=codigo_lista, edital=edital)
        oferta_vaga.qtd += qtd
        oferta_vaga.qtd_semestre_1 = qtd_semestre_1
        oferta_vaga.qtd_semestre_2 = qtd_semestre_2
        oferta_vaga.save()

    for _candidato in task.iterate(doc.getElementsByTagName('candidato')):
        inscricao = _candidato.getElementsByTagName('inscricao')[0].firstChild.nodeValue
        cpf = _candidato.getElementsByTagName('cpf')[0].firstChild.nodeValue
        nome = _candidato.getElementsByTagName('nome')[0].firstChild and _candidato.getElementsByTagName('nome')[0].firstChild.nodeValue or ''
        email = _candidato.getElementsByTagName('email')[0].firstChild and _candidato.getElementsByTagName('email')[0].firstChild.nodeValue or ''
        telefone = (
            _candidato.getElementsByTagName('telefone')[0].firstChild and _candidato.getElementsByTagName('telefone')[0].firstChild.nodeValue or ''
        )
        codigo_curso = (
            _candidato.getElementsByTagName('codigo-curso')[0].firstChild
            and _candidato.getElementsByTagName('codigo-curso')[0].firstChild.nodeValue
            or ''
        )
        turno = (
            _candidato.getElementsByTagName('turno')[0].firstChild
            and str(_candidato.getElementsByTagName('turno')[0].firstChild.nodeValue).upper()
            or ''
        )
        campus_polo = (
            _candidato.getElementsByTagName('campus-polo')[0].firstChild
            and _candidato.getElementsByTagName('campus-polo')[0].firstChild.nodeValue
            or ''
        )
        if (
            _candidato.getElementsByTagName('aprovado-heteroidentificacao')
            and _candidato.getElementsByTagName('aprovado-heteroidentificacao')[0].firstChild
        ):
            aprovado_heteroidentificacao = _candidato.getElementsByTagName('aprovado-heteroidentificacao')[0].firstChild.nodeValue == 'Sim'
        else:
            aprovado_heteroidentificacao = None

        if _candidato.getElementsByTagName('aprovado-quilombola') and _candidato.getElementsByTagName('aprovado-quilombola')[0].firstChild:
            aprovado_quilombola = _candidato.getElementsByTagName('aprovado-quilombola')[0].firstChild.nodeValue == 'Sim'
        else:
            aprovado_quilombola = None

        if _candidato.getElementsByTagName('aprovado-baixa-renda') and _candidato.getElementsByTagName('aprovado-baixa-renda')[0].firstChild:
            aprovado_baixa_renda = _candidato.getElementsByTagName('aprovado-baixa-renda')[0].firstChild.nodeValue == 'Sim'
        else:
            aprovado_baixa_renda = None

        if _candidato.getElementsByTagName('aprovado-escola-publica') and _candidato.getElementsByTagName('aprovado-escola-publica')[0].firstChild:
            aprovado_escola_publica = _candidato.getElementsByTagName('aprovado-escola-publica')[0].firstChild.nodeValue == 'Sim'
        else:
            aprovado_escola_publica = None

        if _candidato.getElementsByTagName('aprovado-deficiencia') and _candidato.getElementsByTagName('aprovado-deficiencia')[0].firstChild:
            aprovado_deficiencia = _candidato.getElementsByTagName('aprovado-deficiencia')[0].firstChild.nodeValue == 'Sim'
        else:
            aprovado_deficiencia = None

        qs = Candidato.objects.filter(inscricao=inscricao, edital=edital)
        if qs.exists():
            candidato = qs[0]
        else:
            candidato = Candidato()
            candidato.inscricao = inscricao
            candidato.edital = edital
        candidato.email = email
        candidato.telefone = telefone
        candidato.cpf = cpf
        candidato.nome = nome
        candidato.curso_campus = CursoCampus.objects.get(codigo=codigo_curso)
        candidato.turno = turnos.get(turno)
        candidato.campus_polo = campus_polo
        candidato.aprovado_heteroidentificacao = aprovado_heteroidentificacao
        candidato.aprovado_quilombola = aprovado_quilombola
        candidato.aprovado_escola_publica = aprovado_escola_publica
        candidato.aprovado_baixa_renda = aprovado_baixa_renda
        candidato.aprovado_deficiencia = aprovado_deficiencia
        candidato.save()

    for _candidato_vaga in task.iterate(doc.getElementsByTagName('candidato-vaga')):
        inscricao = _candidato_vaga.getElementsByTagName('inscricao')[0].firstChild.nodeValue
        codigo_curso = _candidato_vaga.getElementsByTagName('codigo-curso')[0].firstChild.nodeValue
        codigo_lista = _candidato_vaga.getElementsByTagName('codigo-lista')[0].firstChild.nodeValue
        codigo_linha_pesquisa = (
            _candidato_vaga.getElementsByTagName('linha-pesquisa')[0].firstChild
            and _candidato_vaga.getElementsByTagName('linha-pesquisa')[0].firstChild.nodeValue
            or 0
        )
        linha_pesquisa = LinhaPesquisa.objects.filter(pk=codigo_linha_pesquisa).first()
        candidato = Candidato.objects.get(inscricao=inscricao, edital=edital)
        classificacao = _candidato_vaga.getElementsByTagName('classificacao')[0].firstChild.nodeValue
        aprovado = _candidato_vaga.getElementsByTagName('aprovado')[0].firstChild.nodeValue == 'Sim'
        eliminado = _candidato_vaga.getElementsByTagName('eliminado')[0].firstChild.nodeValue == 'Sim'
        turno = (
            _candidato_vaga.getElementsByTagName('turno')[0].firstChild
            and str(_candidato_vaga.getElementsByTagName('turno')[0].firstChild.nodeValue).upper()
            or ''
        )

        qs_oferta_vaga = OfertaVaga.objects.filter(
            oferta_vaga_curso__edital=edital,
            oferta_vaga_curso__curso_campus__codigo=codigo_curso,
            lista__codigo=codigo_lista,
            oferta_vaga_curso__turno=turnos.get(turno),
            oferta_vaga_curso__linha_pesquisa=linha_pesquisa,
        )
        qs_oferta_vaga = qs_oferta_vaga.filter(oferta_vaga_curso__campus_polo=candidato.campus_polo)
        oferta_vaga = qs_oferta_vaga.first()
        if oferta_vaga is None:
            continue

        qs_candidato_vaga = CandidatoVaga.objects.filter(candidato=candidato, oferta_vaga=oferta_vaga)
        if qs_candidato_vaga.exists():
            candidato_vaga = qs_candidato_vaga[0]
        else:
            candidato_vaga = CandidatoVaga()
            candidato_vaga.candidato = candidato
            candidato_vaga.oferta_vaga = oferta_vaga
        candidato_vaga.aprovado = aprovado
        candidato_vaga.eliminado = eliminado
        candidato_vaga.classificacao = classificacao
        candidato_vaga.save()

    for oferta_vaga_curso in edital.ofertavagacurso_set.all():
        oferta_vaga_curso.realizar_nova_chamada(True)

    task.finalize('Importação realizada com sucesso', f'/processo_seletivo/edital/{edital.pk}/')


@task('Atualizar Aprovações dos Candidatos em bancas')
def atualizar_aprovacoes_candidatos(edital, task=None):
    redirect_url = f'/processo_seletivo/edital/{edital.pk}/'

    if not edital.webservice or not edital.webservice.url_edital:
        task.finalize('O edital não possui webservice configurado para atualização das aprovações.', redirect_url)
        return

    try:
        xml = edital.webservice.edital_bruto(edital.codigo)
    except Exception as exc:  # pragma: no cover - dependência externa
        task.finalize(f'Erro ao consultar o webservice: {exc}', redirect_url)
        return

    if not xml:
        task.finalize('O webservice não retornou informações para atualização.', redirect_url)
        return

    try:
        import re

        xml_sanitizado = re.sub(r'&(?!#?[0-9a-zA-Z]+;)', '&amp;', xml)
        doc = minidom.parseString(xml_sanitizado)
    except Exception as exc:
        task.finalize(f'Erro ao processar o XML retornado: {exc}', redirect_url)
        return

    candidatos_xml = doc.getElementsByTagName('candidato')
    if not candidatos_xml:
        task.finalize('Nenhum candidato foi encontrado no webservice.', redirect_url)
        return

    task.count(candidatos_xml)

    field_map = {
        'aprovado_heteroidentificacao': 'aprovado-heteroidentificacao',
        'aprovado_quilombola': 'aprovado-quilombola',
        'aprovado_escola_publica': 'aprovado-escola-publica',
        'aprovado_baixa_renda': 'aprovado-baixa-renda',
        'aprovado_deficiencia': 'aprovado-deficiencia',
    }
    field_labels = {
        'aprovado_heteroidentificacao': 'Heteroidentificação',
        'aprovado_quilombola': 'Quilombola',
        'aprovado_escola_publica': 'Escola pública',
        'aprovado_baixa_renda': 'Baixa renda',
        'aprovado_deficiencia': 'Deficiência',
    }

    def criar_resumo():
        return {campo: {'aprovados': 0, 'reprovados': 0, 'pendentes': 0} for campo in field_map}

    def chave_valor(valor):
        if valor is True:
            return 'aprovados'
        if valor is False:
            return 'reprovados'
        return 'pendentes'

    def atualizar_resumo(resumo, campo, valor, delta):
        if campo in resumo:
            resumo[campo][chave_valor(valor)] += delta

    def extrair_booleano(node, tag):
        elementos = node.getElementsByTagName(tag)
        if not elementos:
            return None
        primeiro = elementos[0].firstChild
        if not primeiro:
            return None
        valor = primeiro.nodeValue.strip().lower()
        if valor in ('sim', 's', 'true', '1'):
            return True
        if valor in ('não', 'nao', 'n', 'false', '0'):
            return False
        return None

    dados_por_inscricao = {}
    for candidato_xml in task.iterate(candidatos_xml):
        inscricao_nodes = candidato_xml.getElementsByTagName('inscricao')
        if not inscricao_nodes or not inscricao_nodes[0].firstChild:
            continue
        inscricao = inscricao_nodes[0].firstChild.nodeValue
        dados = {campo: extrair_booleano(candidato_xml, tag) for campo, tag in field_map.items()}
        dados_por_inscricao[inscricao] = dados

    if not dados_por_inscricao:
        task.finalize('Nenhum dado de aprovação foi localizado para atualização.', redirect_url)
        return

    candidatos = list(Candidato.objects.filter(edital=edital, inscricao__in=dados_por_inscricao.keys()))
    inscricoes_existentes = {c.inscricao for c in candidatos}

    resumo_antes = criar_resumo()
    for candidato in candidatos:
        for campo in field_map:
            atualizar_resumo(resumo_antes, campo, getattr(candidato, campo), 1)

    resumo_depois = deepcopy(resumo_antes)

    atualizados = []
    for candidato in candidatos:
        dados = dados_por_inscricao.get(candidato.inscricao)
        alterado = False
        for campo in field_map:
            novo_valor = dados.get(campo)
            if novo_valor is None:
                continue
            if getattr(candidato, campo) != novo_valor:
                atualizar_resumo(resumo_depois, campo, getattr(candidato, campo), -1)
                atualizar_resumo(resumo_depois, campo, novo_valor, 1)
                setattr(candidato, campo, novo_valor)
                alterado = True
        if alterado:
            atualizados.append(candidato)

    if atualizados:
        Candidato.objects.bulk_update(atualizados, list(field_map.keys()))

    inscricoes_nao_encontradas = set(dados_por_inscricao.keys()) - inscricoes_existentes

    def formatar_resumo(label, antes, depois):
        def fmt(valores):
            return f'Aprovado {valores["aprovados"]}, Reprovado {valores["reprovados"]}, Sem avaliação {valores["pendentes"]}'

        return f'{label}: {fmt(antes)} → {fmt(depois)}'

    linhas_resumo = [formatar_resumo(field_labels[campo], resumo_antes[campo], resumo_depois[campo]) for campo in field_map]

    mensagem = f'Aprovações atualizadas para {len(atualizados)} candidato(s).'
    if inscricoes_nao_encontradas:
        mensagem += f' {len(inscricoes_nao_encontradas)} inscrição(ões) não foram localizadas no SUAP.'
    if linhas_resumo:
        mensagem += ' Resumo: ' + ' | '.join(linhas_resumo)

    task.finalize(mensagem, redirect_url)


# chave em consultar_candidato -> atributo do aluno (só valores preenchidos são gravados)
CAMPOS_DADOS_PESSOAIS_ALUNO = {
    'estado_civil': 'estado_civil',
    'tipo_sanguineo': 'tipo_sanguineo',
    'nome_mae': 'nome_mae',
    'nome_pai': 'nome_pai',
    'responsavel': 'responsavel',
    'parentesco_responsavel': 'parentesco_responsavel',
    'logradouro': 'logradouro',
    'numero': 'numero',
    'complemento': 'complemento',
    'bairro': 'bairro',
    'cidade': 'cidade',
    'cep': 'cep',
    'telefone_principal': 'telefone_principal',
    'telefone_secundario': 'telefone_secundario',
    'numero_rg': 'numero_rg',
    'uf_emissao_rg': 'uf_emissao_rg_id',
    'orgao_emissao_rg': 'orgao_emissao_rg_id',
    'data_emissao_rg': 'data_emissao_rg',
    'linha_pesquisa': 'linha_pesquisa',
    'tipo_zona_residencial': 'tipo_zona_residencial',
    'naturalidade': 'naturalidade',
}


def _aluno_do_candidato_proitec(candidato_vaga: CandidatoVaga) -> Aluno:
    """O aluno do candidato (existente ou novo); a pessoa só é preenchida, nunca sobrescrita: sem data de nascimento não há como checar a identidade."""
    dados_pessoa = {'cpf': candidato_vaga.candidato.cpf, 'nome': candidato_vaga.candidato.nome}
    aluno = Aluno.objects.filter(candidato_vaga=candidato_vaga).first()
    if aluno:
        aplicar_politica(aluno.pessoa_fisica, dados_pessoa, Politica.PREENCHER)
        aluno.telefone_principal = candidato_vaga.candidato.telefone
        aluno.pessoa_fisica.save()
        return aluno
    pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(dados_pessoa, Politica.PREENCHER)
    aluno = Aluno()
    aluno.pessoa_fisica = pessoa_fisica
    return aluno


def _definir_situacao_proitec(aluno: Aluno, candidato_vaga: CandidatoVaga, finalizar: bool) -> int:
    """Define a situação do aluno e retorna a da matrícula no período."""
    if not finalizar:
        aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
        return SituacaoMatriculaPeriodo.MATRICULADO
    if not candidato_vaga.aprovado:
        aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.NAO_CONCLUIDO)
        return SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA
    aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.CONCLUIDO)
    if not aluno.dt_conclusao_curso:
        aluno.dt_conclusao_curso = date.today()
        aluno.ano_conclusao = aluno.ano_letivo.ano
    return SituacaoMatriculaPeriodo.APROVADO


def _importar_dados_pessoais_proitec(aluno: Aluno, dados: dict) -> None:
    aplicar_politica(aluno.pessoa_fisica, {'sexo': dados['sexo'], 'nascimento_data': dados['data_nascimento']}, Politica.PREENCHER)
    for chave, atributo in CAMPOS_DADOS_PESSOAIS_ALUNO.items():
        if dados[chave]:
            setattr(aluno, atributo, dados[chave])


def _atualizar_vinculo_proitec(aluno: Aluno, dados: dict, email_secundario: str) -> None:
    v = aluno.get_vinculo()
    if not v:
        return
    update_fields_vinculo = set()
    if dados.get('raca'):
        v.raca = dados['raca']
        update_fields_vinculo.add('raca')
    email_pessoal_v = dados.get('email_pessoal') and not Configuracao.eh_email_institucional(dados['email_pessoal']) and dados['email_pessoal']
    if email_pessoal_v:
        v.email_pessoal = email_pessoal_v
        update_fields_vinculo.add('email_pessoal')
    if not v.email_pessoal and email_secundario:
        v.email_pessoal = email_secundario
        update_fields_vinculo.add('email_pessoal')
    if update_fields_vinculo:
        v.save(update_fields=list(update_fields_vinculo))


def _salvar_matricula_periodo_proitec(aluno: Aluno, situacao_periodo: int) -> None:
    mp = aluno.matriculaperiodo_set.first() or MatriculaPeriodo()
    mp.ano_letivo = aluno.ano_letivo
    mp.periodo_letivo = aluno.periodo_letivo
    mp.situacao = SituacaoMatriculaPeriodo.objects.get(pk=situacao_periodo)
    mp.periodo_matriz = 1
    mp.aluno = aluno
    mp.save()


@task('Matricular Alunos PROITEC')
def matricular_alunos_proitec(
    edital: Edital,
    ano_letivo: Ano,
    periodo_letivo: int,
    matriz: Matriz,
    finalizar: bool = False,
    importar_dados_pessoais: bool = False,
    task: Task | None = None,
) -> None:
    candidatos_vaga = CandidatoVaga.objects.filter(
        oferta_vaga__oferta_vaga_curso__curso_campus__in=edital.get_ids_cursos_proitec(), oferta_vaga__oferta_vaga_curso__edital=edital
    )
    recusados = []
    for candidato_vaga in task.iterate(candidatos_vaga):
        email_secundario = not Configuracao.eh_email_institucional(candidato_vaga.candidato.email) and candidato_vaga.candidato.email or ''
        try:
            aluno = _aluno_do_candidato_proitec(candidato_vaga)
        except DocumentoDeOutraPessoa:
            # o CPF do candidato já é de outra pessoa física: fica de fora, e os demais são matriculados (o CPF não vai ao log)
            logger.warning(
                f'PROITEC: candidato {candidato_vaga.candidato.nome} (CandidatoVaga {candidato_vaga.pk}) não matriculado: CPF de outra pessoa.'
            )
            recusados.append(candidato_vaga.candidato.nome)
            continue

        aluno.ira = 0
        aluno.periodo_letivo = periodo_letivo
        aluno.ano_letivo = ano_letivo
        aluno.periodo_atual = 1

        aluno.matriz = matriz
        aluno.curso_campus = candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus
        situacao_periodo = _definir_situacao_proitec(aluno, candidato_vaga, finalizar)

        aluno.candidato_vaga = candidato_vaga
        if not aluno.matricula:
            prefixo = f'{aluno.ano_letivo}{aluno.periodo_letivo}{aluno.curso_campus.codigo}'
            aluno.matricula = SequencialMatricula.proximo_numero(prefixo)

        dados = {}
        if importar_dados_pessoais:
            dados = edital.consultar_candidato(candidato_vaga)
            _importar_dados_pessoais_proitec(aluno, dados)

        aluno.save()
        aluno.pessoa_fisica.save()
        _atualizar_vinculo_proitec(aluno, dados, email_secundario)
        _salvar_matricula_periodo_proitec(aluno, situacao_periodo)
    CandidatoVaga.objects.filter(candidato__edital=edital, aluno__matriz=matriz).update(situacao=CandidatoVaga.MATRICULADO, convocacao=1)
    mensagem = 'Matrículas realizadas com sucesso'
    if recusados:
        mensagem += f'. Não matriculados (CPF de outra pessoa): {", ".join(recusados)}'
    task.finalize(mensagem, f'/processo_seletivo/edital/{edital.pk}/')


@task('Processar Alunos PROITEC')
def processar_matriculas_proitec(edital, task=None):
    xml = edital.webservice.edital(edital.codigo)
    doc = minidom.parseString(xml)
    tags = doc.getElementsByTagName('candidato-vaga')
    for _candidato_vaga in task.iterate(tags):
        inscricao = _candidato_vaga.getElementsByTagName('inscricao')[0].firstChild.nodeValue
        aprovado = _candidato_vaga.getElementsByTagName('aprovado')[0].firstChild.nodeValue == 'Sim'
        CandidatoVaga.objects.filter(candidato__edital=edital, candidato__inscricao=inscricao).update(aprovado=aprovado)
        aluno_pk = (
            Aluno.objects.filter(candidato_vaga__candidato__edital=edital, candidato_vaga__candidato__inscricao=inscricao)
            .values_list('id', flat=True)
            .first()
        )
        Aluno.objects.filter(pk=aluno_pk).update(
            situacao_id=SituacaoMatricula.CONCLUIDO if aprovado else SituacaoMatricula.NAO_CONCLUIDO,
            dt_conclusao_curso=date.today() if aprovado else None,
            ano_conclusao=date.today().year if aprovado else None,
        )
        MatriculaPeriodo.objects.filter(aluno_id=aluno_pk).update(
            situacao_id=SituacaoMatriculaPeriodo.APROVADO if aprovado else SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA
        )
        MatriculaDiario.objects.filter(
            matricula_periodo__aluno__candidato_vaga__candidato__edital=edital, matricula_periodo__situacao_id=SituacaoMatriculaPeriodo.APROVADO
        ).update(situacao=MatriculaDiario.SITUACAO_APROVADO)
        MatriculaDiario.objects.filter(
            matricula_periodo__aluno__candidato_vaga__candidato__edital=edital,
            matricula_periodo__situacao_id=SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA,
        ).update(situacao=MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA)
    task.finalize('Matrículas realizadas com sucesso', f'/processo_seletivo/edital/{edital.pk}/')
