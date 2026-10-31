"""Fluxos clínicos centrais: atendimento médico/enfermagem e avaliação de saúde.

O primeiro teste porta a cadeia da feature 0001: abertura pelo Auxiliar, intervenção pelo
Técnico, registro e fechamento pelo Médico. O segundo exercita as nove fichas da avaliação
biomédica que sustentam prontuário e relatórios; cada gravação confirma mensagem e ORM para
pegar formulários que respondam sucesso sem persistir o dado clínico.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from edu.models import Aluno
    from saude.models import Atendimento, Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ABRIR_ATENDIMENTO = '/saude/abrir_atendimento/{}/{}/{}/{}/'
FECHAR_ATENDIMENTO = '/saude/fechar_atendimento/{}/'
ATENDIMENTO_MEDICO = '/saude/atendimento_medico_enfermagem/{}/'
AVALIACAO_BIOMEDICA = '/saude/avaliacao_biomedica/{}/'
ADICIONAR_MOTIVO = '/saude/adicionar_motivo_atendimento/{}/'
ADICIONAR_INTERVENCAO = '/saude/adicionar_intervencao_enfermagem/{}/'
ADICIONAR_ANAMNESE = '/saude/adicionar_anamnese/{}/'
ADICIONAR_CONDUTA = '/saude/adicionar_conduta_medica/{}/'
ADICIONAR_INTERVENCAO_FISIO = '/saude/adicionar_intervencao_fisioterapia/{}/'
ADICIONAR_SINAIS_VITAIS = '/saude/adicionar_sinaisvitais/{}/'
ADICIONAR_ANTROPOMETRIA = '/saude/adicionar_antropometria/{}/'
ADICIONAR_ACUIDADE_VISUAL = '/saude/adicionar_acuidadevisual/{}/'
ADICIONAR_ANTECEDENTES = '/saude/adicionar_antecedentesfamiliares/{}/'
ADICIONAR_PROCESSO_SAUDE_DOENCA = '/saude/adicionar_processosaudedoenca/{}/'
ADICIONAR_HABITOS = '/saude/adicionar_habitosdevida/{}/'
ADICIONAR_DESENVOLVIMENTO = '/saude/adicionar_desenvolvimentopessoal/{}/'
ADICIONAR_EXAME_FISICO = '/saude/adicionar_examefisico/{}/'
ADICIONAR_PERCEPCAO_BUCAL = '/saude/adicionar_percepcaosaudebucal/{}/{}/'
ADICIONAR_PERIODONTAL = '/saude/adicionar_exame_periodontal/{}/'
EDITAR_PERIODONTAL = '/saude/editar_exame_periodontal/{}/'
HISTORICO_FICHA = '/saude/historico_ficha/{}/{}/'
VALORES_ANTROPOMETRIA = '/saude/antropometria_valores_referencia/'


def _aluno_e_prontuario() -> tuple[Aluno, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou falha explicando a ordem da cadeia."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _ultimo_atendimento(tipo: int) -> Atendimento:
    """Devolve o atendimento mais recente do paciente para o tipo solicitado."""
    from saude.models import Atendimento

    atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=tipo).order_by('-id').first()
    assert atendimento is not None, f'atendimento do tipo {tipo} não foi criado pela tela'
    return atendimento


def test_atendimento_medico_enfermagem_com_intervencao_e_fechamento(logado_saude: Callable[[str], Page]) -> None:
    """Três papéis completam o atendimento que a feature distribui em três cenários."""
    tela_auxiliar = Tela(logado_saude('auxiliar_enfermagem'))

    from saude.models import (
        Anamnese,
        Atendimento,
        CondutaMedica,
        IntervencaoEnfermagem,
        IntervencaoFisioterapia,
        Motivo,
        SituacaoAtendimento,
        TipoAtendimento,
    )

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela_auxiliar.ir(f'/saude/prontuario/{vinculo.pk}/').ver_titulo('Prontuário')
    tela_auxiliar.clicar_botao('Atendimento Médico/Enfermagem')
    expect(tela_auxiliar.pagina).to_have_url(re.compile(r'/saude/atendimento_medico_enfermagem/\d+/$'))
    tela_auxiliar.esperar().sucesso('Atendimento Médico/Enfermagem gerado com sucesso.').ver_titulo('Atendimento Médico/Enfermagem')
    atendimento = _ultimo_atendimento(TipoAtendimento.ENFERMAGEM_MEDICO)
    assert atendimento.situacao == SituacaoAtendimento.ABERTO, 'a UI disse que abriu, mas o atendimento não ficou aberto'

    tela_auxiliar.clicar_botao('Adicionar Motivo')
    expect(tela_auxiliar.pagina).to_have_url(re.compile(rf'{ADICIONAR_MOTIVO.format(atendimento.pk)}$'))
    tela_auxiliar.esperar().preencher('Motivo do Atendimento', 'TextArea', 'Motivo do atendimento')
    tela_auxiliar.clicar_botao('Salvar')
    tela_auxiliar.sucesso('Motivo do Atendimento registrado com sucesso.')
    assert Motivo.objects.filter(atendimento=atendimento, motivo_atendimento='Motivo do atendimento').exists(), (
        'a UI disse que salvou, mas o motivo não persistiu'
    )

    tela_tecnico = Tela(logado_saude('tecnico_enfermagem')).ir(ATENDIMENTO_MEDICO.format(atendimento.pk))
    tela_tecnico.ver_titulo('Atendimento Médico/Enfermagem')
    tela_tecnico.ir(ADICIONAR_INTERVENCAO.format(atendimento.pk))
    tela_tecnico.preencher_formulario(
        [
            ('Procedimento', 'Autocomplete Multiplo', 'Outros'),
            ('Descrição', 'TextArea', 'Descrição da Intervenção'),
        ]
    )
    tela_tecnico.clicar_botao('Enviar')
    tela_tecnico.sucesso('Intervenção de enfermagem registrada com sucesso.')
    assert IntervencaoEnfermagem.objects.filter(atendimento=atendimento, descricao='Descrição da Intervenção').exists(), (
        'a UI disse que salvou, mas a intervenção não persistiu'
    )

    tela_medico = Tela(logado_saude('medico')).ir(ADICIONAR_ANAMNESE.format(atendimento.pk))
    tela_medico.preencher('HDA', 'TextArea', 'Descrição Anamnese.')
    tela_medico.clicar_botao('Salvar')
    tela_medico.sucesso('Anamnese registrada com sucesso.')
    assert Anamnese.objects.filter(atendimento=atendimento, hda='Descrição Anamnese.').exists(), 'a UI disse que salvou, mas a anamnese não persistiu'

    tela_medico.ir(ADICIONAR_CONDUTA.format(atendimento.pk))
    tela_medico.preencher('Conduta', 'TextArea', 'Conduta médica')
    tela_medico.clicar_botao('Salvar')
    tela_medico.sucesso('Conduta Médica registrada com sucesso.')
    assert CondutaMedica.objects.filter(atendimento=atendimento, conduta='Conduta médica').exists(), (
        'a UI disse que salvou, mas a conduta não persistiu'
    )

    # A intervenção de fisioterapia é registrada na própria tela do atendimento médico/enfermagem
    # (aba "Intervenções de Fisioterapia") — é o ponto em que o produto a oferece ao fisioterapeuta.
    tela_fisio = Tela(logado_saude('fisioterapeuta')).ir(ATENDIMENTO_MEDICO.format(atendimento.pk))
    tela_fisio.clicar_aba('Intervenções de Fisioterapia')
    tela_fisio.clicar_botao('Adicionar')
    expect(tela_fisio.pagina).to_have_url(re.compile(rf'{ADICIONAR_INTERVENCAO_FISIO.format(atendimento.pk)}$'))
    tela_fisio.preencher('Descrição', 'TextArea', 'Intervenção de fisioterapia E2E')
    tela_fisio.clicar_botao('Enviar').sucesso('Intervenção de fisioterapia registrada com sucesso.')
    assert IntervencaoFisioterapia.objects.filter(atendimento=atendimento, descricao='Intervenção de fisioterapia E2E').exists(), (
        'a UI disse que salvou, mas a intervenção de fisioterapia não persistiu'
    )

    tela_medico.clicar_link('Fechar')
    expect(tela_medico.pagina).to_have_url(re.compile(rf'{FECHAR_ATENDIMENTO.format(atendimento.pk)}$'))
    tela_medico.esperar().preencher('Observação de Fechamento', 'TextArea', 'Observação')
    tela_medico.clicar_botao('Salvar')
    tela_medico.sucesso('Atendimento fechado com sucesso.')
    atendimento = Atendimento.objects.get(pk=atendimento.pk)
    assert atendimento.situacao == SituacaoAtendimento.FECHADO, 'a UI disse que fechou, mas o atendimento continua aberto'
    assert atendimento.obs_fechado == 'Observação', 'a observação de fechamento não persistiu'


def test_avaliacao_biomedica_preenche_fichas_e_fecha(logado_saude: Callable[[str], Page]) -> None:
    """O Médico abre a avaliação, preenche as nove fichas clínicas e a encerra."""
    tela = Tela(logado_saude('medico'))

    from saude.models import (
        AcuidadeVisual,
        AntecedentesFamiliares,
        Antropometria,
        Atendimento,
        DesenvolvimentoPessoal,
        ExameFisico,
        ExamePeriodontal,
        HabitosDeVida,
        PercepcaoSaudeBucal,
        ProcessoSaudeDoenca,
        SinaisVitais,
        SituacaoAtendimento,
        TipoAtendimento,
    )

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(f'/saude/prontuario/{vinculo.pk}/').ver_titulo('Prontuário')
    # O rótulo inteiro do botão: com só "Avaliação de Saúde", o `clicar_botao` (que prioriza link de
    # texto exato) às vezes resolvia um link para /saude/relatorio_avaliacao_biomedica/ e o teste ia
    # parar no relatório em vez de abrir a avaliação.
    tela.clicar_botao('Adicionar Avaliação de Saúde')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/avaliacao_biomedica/\d+/$'))
    tela.esperar().sucesso('Avaliação biomédica gerada com sucesso.').ver_titulo('Avaliação de Saúde')
    atendimento = _ultimo_atendimento(TipoAtendimento.AVALIACAO_BIOMEDICA)
    assert atendimento.situacao == SituacaoAtendimento.ABERTO, 'a UI disse que abriu, mas a avaliação não ficou aberta'

    tela.ir(ADICIONAR_SINAIS_VITAIS.format(atendimento.pk))
    tela.preencher_formulario(
        [
            ('Pressão Sistólica', 'Número', '120'),
            ('Pressão Diastólica', 'Número', '80'),
            ('Pulsação', 'Número', '70'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Sinais Vitais registrados com sucesso.')
    assert SinaisVitais.objects.filter(atendimento=atendimento, pressao_sistolica=120, pressao_diastolica=80).exists(), (
        'a UI disse que salvou, mas os sinais vitais não persistiram'
    )

    tela.ir(ADICIONAR_ANTROPOMETRIA.format(atendimento.pk))
    tela.preencher_formulario([('Estatura', 'Número', '180'), ('Peso', 'Número', '70')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Antropometria registrada com sucesso.')
    assert Antropometria.objects.filter(atendimento=atendimento, estatura=180).exists(), 'a UI disse que salvou, mas a antropometria não persistiu'

    tela.ir(VALORES_ANTROPOMETRIA).ver_titulo('Valores de Referência').ver_texto('IMC Adultos')

    tela.ir(ADICIONAR_ACUIDADE_VISUAL.format(atendimento.pk))
    tela.preencher_formulario(
        [
            ('O teste será realizado com o estudante utilizando lentes corretivas?', 'Lista', 'Sim'),
            ('Olho Esquerdo', 'Lista', '20/20'),
            ('Olho Direito', 'Lista', '20/20'),
            ('Já fez ou faz uso de lentes corretivas (óculos ou lentes de contato)?', 'Lista', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Acuidade visual registrada com sucesso.')
    assert AcuidadeVisual.objects.filter(atendimento=atendimento, olho_direito='20/20', olho_esquerdo='20/20').exists(), (
        'a UI disse que salvou, mas a acuidade visual não persistiu'
    )

    tela.ir(ADICIONAR_ANTECEDENTES.format(atendimento.pk))
    tela.preencher_formulario(
        [
            ('Agravos à saúde com parentesco de 1º grau?', 'Lista', 'Não'),
            ('Agravos à saúde com parentesco de 2º grau?', 'Lista', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Antecedentes familiares registrados com sucesso.')
    assert AntecedentesFamiliares.objects.filter(atendimento=atendimento).exists(), 'a UI disse que salvou, mas os antecedentes não persistiram'

    tela.ir(ADICIONAR_PROCESSO_SAUDE_DOENCA.format(atendimento.pk))
    tela.preencher_formulario(
        [
            ('Já fez alguma cirurgia?', 'Lista', 'Não'),
            ('Histórico de hemorragia?', 'Lista', 'Não'),
            ('Alergia a medicamentos?', 'Lista', 'Não'),
            ('Faz uso de medicamentos rotineiramente?', 'Lista', 'Não'),
            ('Tem Plano de Saúde?', 'Lista', 'Não'),
            ('Tem Plano Odontológico?', 'Lista', 'Não'),
            ('Já teve lesão nos músculos ou nos ossos?', 'Lista', 'Não'),
            ('Sofre de alguma doença crônica?', 'Lista', 'Não'),
            ('Doenças Prévias?', 'Lista', 'Não'),
            ('Problemas Auditivos?', 'Lista', 'Não'),
            ('É pessoa com deficiência?', 'Lista', 'Não'),
            ('Tem transtorno de neurodesenvolvimento?', 'Lista', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Processo Saúde-Doença registrado com sucesso.')
    assert ProcessoSaudeDoenca.objects.filter(atendimento=atendimento).exists(), 'a UI disse que salvou, mas o processo saúde-doença não persistiu'

    tela.ir(ADICIONAR_HABITOS.format(atendimento.pk))
    tela.preencher_formulario(
        [
            ('Pratica atividade física?', 'Lista', 'Não'),
            ('Fuma?', 'Lista', 'Não'),
            ('Ingere bebidas alcoólicas?', 'Lista', 'Não'),
            ('Faz uso ou já usou drogas ilícitas?', 'Lista', 'Não'),
            ('Tem vida sexual ativa?', 'Lista', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Hábitos de Vida registrados com sucesso.')
    assert HabitosDeVida.objects.filter(atendimento=atendimento).exists(), 'a UI disse que salvou, mas os hábitos de vida não persistiram'

    tela.ir(ADICIONAR_DESENVOLVIMENTO.format(atendimento.pk))
    tela.preencher('Já teve ou tem algum problema de aprendizado?', 'Lista', 'Não')
    tela.clicar_botao('Salvar')
    tela.sucesso('Desenvolvimento Pessoal registrado com sucesso.')
    assert DesenvolvimentoPessoal.objects.filter(atendimento=atendimento).exists(), (
        'a UI disse que salvou, mas o desenvolvimento pessoal não persistiu'
    )

    tela.ir(ADICIONAR_EXAME_FISICO.format(atendimento.pk))
    tela.preencher_formulario(
        [
            ('Ectoscopia alterada?', 'Lista', 'Não'),
            ('Aparelho cardiovascular alterado?', 'Lista', 'Não'),
            ('Aparelho respiratório alterado?', 'Lista', 'Não'),
            ('Abdome alterado?', 'Lista', 'Não'),
            ('Membros inferiores alterados?', 'Lista', 'Não'),
            ('Membros superiores alterados?', 'Lista', 'Não'),
            ('Sistema neurológico alterado?', 'Lista', 'Não'),
            ('Estado mental alterado?', 'Lista', 'Não'),
            ('Outros órgãos/sistemas alterados?', 'Lista', 'Não'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Exame Físico registrado com sucesso.')
    assert ExameFisico.objects.filter(atendimento=atendimento).exists(), 'a UI disse que salvou, mas o exame físico não persistiu'

    tela.ir(ADICIONAR_PERCEPCAO_BUCAL.format(atendimento.pk, 1))
    tela.preencher_formulario(
        [
            ('Quantas vezes você costuma escovar os dentes por dia?', 'Radio', 'Duas a três vezes'),
            ('Já foi a um dentista anteriormente?', 'Lista', 'Não'),
            ('Você usa fio dental?', 'Lista', 'Não'),
            (
                'Quantas vezes por dia você consome alimentos ou bebidas com açúcar (Bolos, balas, refrigerantes, sucos artificiais, biscoitos e doces em geral)?',
                'Radio',
                'Nenhuma',
            ),
            ('Usa prótese (coroa, removível ou total)?', 'Lista', 'Não'),
            ('Usa aparelho ortodôntico/contenção?', 'Lista', 'Não'),
            (
                'Nos últimos 6 meses teve alguma dificuldade relacionada à boca, dente, prótese ou aparelho ortodôntico que lhe causou alguma dificuldade?',
                'Lista',
                'Não',
            ),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Percepção de Saúde Bucal registrada com sucesso.')
    assert PercepcaoSaudeBucal.objects.filter(atendimento=atendimento).exists(), 'a UI disse que salvou, mas a percepção bucal não persistiu'

    tela.ir(HISTORICO_FICHA.format(atendimento.pk, 1)).ver_titulo('Histórico - Sinais Vitais').ver_texto('120')

    # Exame periodontal: o ciclo completo com **edição** é o da aba Odontograma da avaliação
    # biomédica — no atendimento odontológico o box só oferece Adicionar/Resolver/Excluir, e
    # `editar_exame_periodontal` redireciona para cá (é o desfecho esperado pelo produto).
    # Quem tem a especialidade exigida é o odontólogo, em sessão própria.
    tela_odonto = Tela(logado_saude('odontologo')).ir(AVALIACAO_BIOMEDICA.format(atendimento.pk)).clicar_aba('Odontograma')
    tela_odonto.quadro('Exame Periodontal').clicar_botao('Adicionar')
    expect(tela_odonto.pagina).to_have_url(re.compile(rf'{ADICIONAR_PERIODONTAL.format(atendimento.pk)}\?origem=1$'))
    tela_odonto.preencher_formulario([('Ocorrência', 'Lista', 'Sangramento'), ('Sextante', 'FilteredSelectMultiple', 'S1, S2')])
    tela_odonto.clicar_botao('Salvar').sucesso('Exame periodontal registrado com sucesso.')
    exame = ExamePeriodontal.objects.get(atendimento=atendimento, ocorrencia=ExamePeriodontal.SANGRAMENTO)
    assert exame.sextante == 'S1; S2', 'a UI disse que salvou, mas o exame periodontal não persistiu'

    tela_odonto.ir(AVALIACAO_BIOMEDICA.format(atendimento.pk)).clicar_aba('Odontograma')
    tela_odonto.quadro('Exame Periodontal').linha('Sangramento').clicar_icone('edição')
    expect(tela_odonto.pagina).to_have_url(re.compile(rf'{EDITAR_PERIODONTAL.format(exame.pk)}$'))
    tela_odonto.preencher_formulario([('Ocorrência', 'Lista', 'Recessão'), ('Sextante', 'FilteredSelectMultiple', 'S3')])
    tela_odonto.clicar_botao('Salvar').sucesso('Exame periodontal editado com sucesso.')
    exame.refresh_from_db()
    assert exame.ocorrencia == ExamePeriodontal.RECESSAO, 'a UI disse que editou, mas a ocorrência não mudou'
    assert exame.sextante == 'S3', 'a UI disse que editou, mas o sextante não mudou'

    tela_odonto.clicar_aba('Odontograma')
    tela_odonto.quadro('Exame Periodontal').linha('Recessão').clicar_icone('remoção')
    tela_odonto.sucesso('Exame periodontal excluido com sucesso.')
    assert not ExamePeriodontal.objects.filter(pk=exame.pk).exists(), 'a UI disse que excluiu, mas o exame permanece'

    tela.ir(AVALIACAO_BIOMEDICA.format(atendimento.pk)).ver_titulo('Avaliação de Saúde')
    tela.clicar_link('Fechar')
    expect(tela.pagina).to_have_url(re.compile(rf'{FECHAR_ATENDIMENTO.format(atendimento.pk)}$'))
    tela.esperar().preencher('Observação de Fechamento', 'TextArea', 'Avaliação concluída')
    tela.clicar_botao('Salvar')
    tela.sucesso('Atendimento fechado com sucesso.')
    atendimento = Atendimento.objects.get(pk=atendimento.pk)
    assert atendimento.situacao == SituacaoAtendimento.FECHADO, 'a UI disse que fechou, mas a avaliação continua aberta'
