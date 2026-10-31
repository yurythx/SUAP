from comum.models import Ano, UnidadeOrganizacional
from djtools.management.commands import BaseCommandPlus
from edu.models import CenarioOferta, MatriculaDiario, Matriz, Modalidade, PrevisaoQuantidadeAlunos, Turno


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        sigla = 'CN'
        ano = 2024
        ano_letivo = Ano.objects.get_or_create(ano=ano)[0]
        turno = Turno.objects.get(pk=Turno.MATUTINO)
        for uo in UnidadeOrganizacional.objects.filter(sigla=sigla):
            cenario = CenarioOferta.objects.filter(uo=uo, ano_letivo=ano_letivo, periodo_letivo=1).first()
            if cenario is None:
                cenario = CenarioOferta.objects.create(uo=uo, ano_letivo=ano_letivo, periodo_letivo=1)
            matrizes = Matriz.objects.filter(
                ativo=True, matrizcurso__curso_campus__diretoria__setor__uo=uo, matrizcurso__curso_campus__modalidade_id=Modalidade.INTEGRADO
            )
            for matriz in matrizes:
                print(matriz)
                pqa = PrevisaoQuantidadeAlunos.objects.filter(cenario=cenario, matriz=matriz, turno=turno).first()
                if pqa is None:
                    pqa = PrevisaoQuantidadeAlunos(cenario=cenario, matriz=matriz, turno=turno)
                for cc in matriz.componentecurricular_set.filter(componente__grupo_atuacao__isnull=True):
                    print(f'\t>>> Informar grupo de atualização do componente: {cc.componente}')
                for serie in cenario.get_series():
                    qtd_alunos = (
                        MatriculaDiario.objects.filter(
                            diario__turma__curso_campus__diretoria__setor__uo=uo,
                            diario__componente_curricular__matriz=matriz,
                            diario__ano_letivo__ano=ano - 1,
                            diario__componente_curricular__periodo_letivo=serie,
                        )
                        .values_list('matricula_periodo__aluno')
                        .order_by('matricula_periodo__aluno')
                        .distinct()
                        .count()
                    )
                    if serie == 1:
                        pqa.qtd_ingressantes = qtd_alunos
                        pqa.qtd_turmas = 1
                    setattr(pqa, f'qtd_alunos_{serie}', qtd_alunos)
                pqa.save()
