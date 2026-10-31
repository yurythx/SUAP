import json
import logging
from json import JSONDecodeError

from django.core.exceptions import ValidationError

from comum.models import APIExterna
from comum.services.api_externa import APIExternaService
from djtools.utils import requests
from edu import services
from edu.models import ConfiguracaoAvaliacao, Diario, ItemConfiguracaoAvaliacao, NotaAvaliacao, TurmaMinicurso, Aluno, SituacaoMatricula

logger = logging.getLogger(__name__)


class ApiMoodleService(APIExternaService):
    def __init__(self):
        super().__init__(APIExterna.MOODLE)

    def get_headers(self, verbosity: bool = False) -> dict[str, object]:
        headers = super().get_headers(verbosity=verbosity)
        enviar_diarios_path = headers.pop('enviar_diarios_path', '')
        importar_notas_path = headers.pop('baixar_notas_path', '')
        self.turma_minicurso_id = headers.pop('turma_minicurso_id', 0)
        self.moodle_export_url = f'{self.api_externa.url_base}{enviar_diarios_path}'
        self.moodle_import_url = f'{self.api_externa.url_base}{importar_notas_path}'
        return headers

    def estah_acessivel(self, verbosity=False):
        try:
            headers = self.get_headers(verbosity=verbosity)
            turma = TurmaMinicurso.objects.filter(
                id=self.turma_minicurso_id,
            ).first()

            if not turma:
                return True

            url = f'{self.moodle_import_url}?campus_sigla={turma.minicurso.diretoria.setor.uo.sigla}&diario_id={turma.id}&user='
            response = requests.get(
                url,
                verify=True,
                headers=headers,
                timeout=self.get_timeout(),
                verbosity=verbosity,
                API=self.api_externa.nome,
            )
            return bool(response.ok and response.json() and 'error' not in response.json())
        except Exception as e:
            if verbosity:
                logger.info(f'API MOODLE não está acessível. Exception: {e}')
            return False

    def sincronizar(self, diario):
        headers = self.get_headers()
        dados = {
            'campus': services.serialize(diario.turma.curso_campus.diretoria.setor.uo, add_id=True),
            'curso': services.serialize(diario.turma.curso_campus, add_id=True),
            'turma': services.serialize(diario.turma, add_id=True),
            'diario': services.serialize(diario, add_id=True),
            'professores': [services.serialize(professor_diario, add_id=True) for professor_diario in diario.professordiario_set.all()],
            'alunos': [],
            'polo': diario.turma.polo and services.serialize(diario.turma.polo, add_id=True) or None,
            'componente': services.serialize(diario.componente_curricular, add_id=True),
        }
        for matricula_diario in diario.matriculadiario_set.all():
            aluno = services.serialize(matricula_diario.matricula_periodo.aluno, add_id=True)
            aluno['situacao_diario'] = 'ativo' if matricula_diario.is_situacao_ativa() else 'inativo'
            aluno['programa'] = (
                matricula_diario.matricula_periodo.aluno.convenio.descricao if matricula_diario.matricula_periodo.aluno.convenio_id else None
            )
            dados['alunos'].append(aluno)

        response = requests.post(
            self.moodle_export_url,
            verify=False,
            data=json.dumps(dados),
            headers=headers,
            timeout=self.get_timeout(),
        )

        if response.text.strip():
            try:
                retorno = json.loads(response.text)
            except JSONDecodeError as e:
                raise Exception(f'Ocorreu um erro: {e}. Texto recebido: {response.text}')
            if 'url' in retorno:
                return retorno['url']
            else:
                raise Exception(retorno['error'])
        else:
            raise Exception('Resposta vazia.')

    def sincronizar_turma_minicurso(self, turma):
        headers = self.get_headers()
        chave = f'{turma.ano_letivo}{turma.periodo_letivo}.1.{turma.minicurso.codigo}.1E'
        dados = {
            'campus': services.serialize(turma.minicurso.diretoria.setor.uo, add_id=True),
            'curso': services.serialize(turma.minicurso, add_id=True),
            'turma': {'id': turma.id, 'codigo': chave},
            'diario': {'id': turma.id, 'sigla': chave, 'situacao': 'Aberto', 'tipo': 'minicurso'},
            'professores': [services.serialize(professor_minicurso, add_id=True) for professor_minicurso in turma.professorminicurso_set.all()],
            'alunos': [],
            'polo': None,
            'componente': {
                'id': turma.id,
                'sigla': chave,
                'descricao': turma.descricao,
                'descricao_historico': turma.descricao,
                'tipo': f'MC{turma.id}',
                'optativo': False,
                'qtd_avaliacoes': 1,
            },
            'autoinscricao': {
                'brasileiros': turma.autoinscricao_brasileiros,
                'estrangeiros': turma.autoinscricao_estrangeiros,
                'tecnicos_administrativos': turma.autoinscricao_tae,
                'docentes': turma.autoinscricao_docente,
                'prestadores': turma.autoinscricao_prestadores,
                'alunos': turma.autoinscricao_alunos,
                'niveis_ensino': list(turma.autoinscricao_nivel_ensino.values_list('descricao', flat=True)),
                'modalidades': list(turma.autoinscricao_modalidades.values_list('descricao', flat=True)),
                'campi': list(turma.autoinscricao_campi.values_list('sigla', flat=True)),
                'cursos': list(turma.autoinscricao_cursos.values_list('descricao_historico', flat=True)),
            }
            if turma.autoinscricional
            else None,
        }
        if not turma.autoinscricional:
            for participacao in turma.participanteturmaminicurso_set.all():
                aluno = services.serialize(participacao.aluno, add_id=True)
                aluno['situacao_diario'] = 'ativo'
                aluno['programa'] = participacao.aluno.convenio.descricao if participacao.aluno.convenio_id else None
                dados['alunos'].append(aluno)

        if headers.get('Authentication') != 'Token 111111':
            response = requests.post(
                self.moodle_export_url,
                verify=False,
                data=json.dumps(dados),
                headers=headers,
                timeout=self.get_timeout(),
            )

            if response.text.strip():
                try:
                    retorno = json.loads(response.text)
                except JSONDecodeError as e:
                    raise Exception(f'Ocorreu um erro: {e}. Texto recebido: {response.text}')
                if 'url' in retorno:
                    return retorno['url']
                else:
                    raise Exception(retorno['error'])
            else:
                raise Exception('Resposta vazia.')

    def importar_notas(self, diario, request):
        contador = 0
        headers = self.get_headers()
        url = f'{self.moodle_import_url}?campus_sigla={diario.turma.curso_campus.diretoria.setor.uo.sigla}&diario_id={diario.id}&user={request.user.username}'
        response = requests.get(
            url,
            verify=False,
            headers=headers,
            timeout=self.get_timeout(),
        )
        retorno = json.loads(response.text)
        posse = {1: diario.posse_etapa_1, 2: diario.posse_etapa_2, 3: diario.posse_etapa_3, 4: diario.posse_etapa_4, 5: diario.posse_etapa_5}
        c1 = ConfiguracaoAvaliacao.objects.filter(diario=diario, etapa=1).first()
        c2 = ConfiguracaoAvaliacao.objects.filter(diario=diario, etapa=2).first()
        c3 = ConfiguracaoAvaliacao.objects.filter(diario=diario, etapa=3).first()
        c4 = ConfiguracaoAvaliacao.objects.filter(diario=diario, etapa=4).first()
        c5 = ConfiguracaoAvaliacao.objects.filter(diario=diario, etapa=5).first()
        utiliza_nota_atitudinal = diario.utiliza_nota_atitudinal()
        for aluno in retorno:
            md = diario.matriculadiario_set.filter(matricula_periodo__aluno__matricula=aluno['matricula']).first()
            # aluno não pode estar com período fechado
            if md and md.is_cursando() and aluno['notas']:
                n1 = aluno['notas'].get('N1')
                n2 = aluno['notas'].get('N2')
                n3 = aluno['notas'].get('N3')
                n4 = aluno['notas'].get('N4')
                n5 = aluno['notas'].get('NAF')
                for etapa, configuracao, nota in [(1, c1, n1), (2, c2, n2), (3, c3, n3), (4, c4, n4), (5, c5, n5)]:
                    if configuracao:
                        if 'meu_diario' in request.path:
                            if posse[etapa] != Diario.POSSE_PROFESSOR:
                                continue
                        else:
                            if posse[etapa] != Diario.POSSE_REGISTRO_ESCOLAR:
                                continue

                        qs_item = ItemConfiguracaoAvaliacao.objects.filter(configuracao_avaliacao=configuracao)
                        if utiliza_nota_atitudinal:
                            qs_item = qs_item.exclude(tipo=ItemConfiguracaoAvaliacao.TIPO_ATITUDINAL)
                        if qs_item.count() != 1:
                            raise ValidationError(f'O diário {diario.id} deve conter apenas uma avaliação na etapa {etapa}.')
                        item = qs_item.first()

                        nota_avaliacao = NotaAvaliacao.objects.filter(matricula_diario=md, item_configuracao_avaliacao=item).first()

                        # se não existe nota importada, mas tem nota registrada no SUAP.
                        if nota is None and nota_avaliacao:
                            nota_avaliacao.nota = None
                            nota_avaliacao.save()
                            md.registrar_nota_etapa(etapa)
                        elif nota is not None:
                            if nota_avaliacao is None:
                                nota_avaliacao = NotaAvaliacao()

                            nota_avaliacao.matricula_diario = md
                            nota_avaliacao.item_configuracao_avaliacao = item

                            # se existir nota importada da etapa final, mas aluno não estiver em prova final, nota importada será ignorada.
                            if etapa == 5 and not md.is_em_prova_final():
                                nota_avaliacao.nota = None
                            else:
                                nota_avaliacao.nota = round(nota * 1.00001)

                            nota_avaliacao.save()
                            md.registrar_nota_etapa(etapa)
                            contador = contador + 1
        return contador

    def importar_notas_turma_minicurso(self, turma, username):
        contador = 0
        headers = self.get_headers()

        if headers.get('Authentication') == 'Token 111111':
            retorno = []
            for i, participante in enumerate(turma.participanteturmaminicurso_set.all()):
                valor = 50 if i % 2 else 100
                retorno.append({'matricula': participante.aluno.matricula, 'notas': {'N1': valor}, 'completude': valor})
        else:
            url = f'{self.moodle_import_url}?campus_sigla={turma.minicurso.diretoria.setor.uo.sigla}&diario_id={turma.id}&user={username}'
            response = requests.get(
                url,
                verify=True,
                headers=headers,
                timeout=self.get_timeout(),
            )
            retorno = json.loads(response.text)

        for aluno in retorno:
            notas = aluno.get('notas')
            completude = aluno.get('completude')
            participante = turma.participanteturmaminicurso_set.filter(aluno__matricula=aluno['matricula'].upper()).first()
            if participante:
                if participante.aluno.situacao_id != SituacaoMatricula.CONCLUIDO:
                    save = False
                    if notas and notas.get('N1') is not None:
                        save = True
                        participante.nota = int(float(notas.get('N1')))
                    if completude is not None and completude != '':
                        save = True
                        participante.completude = int(float(completude))
                    if save:
                        participante.processar_resultado()
                        participante.save()
                        contador += 1
            elif turma.minicurso.autoinstrucional:
                matricula = aluno.get('matricula').upper()
                nota = int(float(notas.get('N1'))) if notas else None
                aluno = Aluno.objects.filter(matricula=matricula).first()
                if aluno:
                    matricula_periodo_origem = aluno.get_ultima_matricula_periodo()
                    completude = int(float(completude)) if completude else None
                    if turma.is_aprovado_por_nota(nota) and turma.is_aprovado_por_completudo(completude):
                        participante = turma.adicionar_novo_aluno(aluno.pessoa_fisica, matricula_periodo_origem)
                        participante.nota = nota
                        participante.completude = completude
                        participante.save()
                        turma.aprovar([participante])
                        contador += 1
        return contador
