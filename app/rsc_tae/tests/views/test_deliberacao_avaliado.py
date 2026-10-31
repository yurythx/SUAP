"""O que o avaliado lê sobre a deliberação depois que o processo fecha.

Até aqui o avaliado via só a camada dos avaliadores auxiliares: a nota consolidada pela CRSC,
a justificativa de cada item e o motivo do indeferimento ficavam no PDF da deliberação — uma
rota que nenhum template linkava. Estes testes fixam o que a aba passa a mostrar e, sobretudo,
o que ela NÃO mostra: quem votou o quê.
"""

from decimal import Decimal

import pytest

from rsc_tae.enums import MotivoIndeferimento, SituacaoAvaliacaoItem, SituacaoProcesso
from rsc_tae.models import (
    AvaliacaoAnexoRSCTae,
    ConfiguracaoRSCTae,
    DeliberacaoCRSCRSCTae,
    DeliberacaoItemCRSCRSCTae,
    GrupoSaberCompetencia,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
)
from rsc_tae.views._deliberacao_avaliado import montar_deliberacao_para_avaliado


class BaseProcessoDeliberado:
    """Um processo indeferido com dois anexos: um contestado e consolidado, outro intocado.

    Sem prefixo ``Test`` de propósito: como classe de teste o pytest recoletaria estes mesmos
    casos em cada subclasse.
    """

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        # Dois votos fecham um item — um membro só pode votar uma vez por anexo (constraint do model).
        ConfiguracaoRSCTae.objects.create(quantidade_deliberacoes_item=2)
        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=1, pontuacao_minima=Decimal('5.00'))
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.INDEFERIDO,
        )
        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('1.000'), descricao='Grupo 1')
        self.item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item contestado', descricao='d', unidade_medida='unidade')
        self.item_ok = RolSaberCompetencia.objects.create(numero=2, grupo=grupo, titulo='Item intocado', descricao='d', unidade_medida='unidade')

        self.anexo = RolSaberCompetenciaAnexo.objects.create(
            processo=self.processo, rol_saber_competencia=self.item, arquivo='contestado.pdf', pontuacao=Decimal('3')
        )
        self.anexo_ok = RolSaberCompetenciaAnexo.objects.create(
            processo=self.processo, rol_saber_competencia=self.item_ok, arquivo='intocado.pdf', pontuacao=Decimal('2')
        )

        # O auxiliar cortou a pontuação do primeiro anexo — é o que cria a divergência.
        AvaliacaoAnexoRSCTae.objects.create(
            anexo=self.anexo,
            avaliador_vinculo=self.servidor_b.get_vinculo(),
            situacao=SituacaoAvaliacaoItem.DEFERIDO,
            pontuacao_validada=Decimal('1'),
            observacao='Período não comprovado integralmente.',
        )

        self.membros = [self.servidor_c.get_vinculo(), self.servidor_d.get_vinculo()]

    def _deliberar_item(self, nota, justificativa='Documento não supre o exigido.'):
        """Fecha a deliberação do anexo contestado: os dois membros votam a mesma nota."""
        for membro in self.membros:
            DeliberacaoItemCRSCRSCTae.objects.create(
                processo=self.processo,
                anexo=self.anexo,
                decisao=DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR,
                pontuacao_crsc=nota,
                justificativa=justificativa,
                deliberado_por_vinculo=membro,
            )

    def _deliberacao_final(self):
        return DeliberacaoCRSCRSCTae.objects.create(
            processo=self.processo,
            resultado=SituacaoProcesso.INDEFERIDO,
            pontuacao_final_crsc=Decimal('3.00'),
            justificativa='Pontuação final abaixo do mínimo do nível.',
            motivos_indeferimento=[MotivoIndeferimento.PONTUACAO_MINIMA],
            deliberado_por_vinculo=self.membros[0],
        )

    def _linha_do(self, dados, anexo):
        return next(linha for linha in dados['linhas'] if linha['anexo'].id == anexo.id)


@pytest.mark.django_db(databases='__all__')
class TestDeliberacaoParaAvaliado(BaseProcessoDeliberado):
    """O que o helper monta a partir do processo decidido."""

    def test_item_consolidado_traz_a_nota_da_crsc_e_a_justificativa(self):
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()

        linha = self._linha_do(montar_deliberacao_para_avaliado(self.processo), self.anexo)

        assert linha['estado'] == 'consolidado'
        assert linha['nota_crsc'] == Decimal('2')
        assert 'Documento não supre o exigido.' in linha['justificativas']

    def test_item_que_ninguem_contestou_sai_como_aceito_como_declarado(self):
        self._deliberacao_final()

        linha = self._linha_do(montar_deliberacao_para_avaliado(self.processo), self.anexo_ok)

        assert linha['estado'] == 'aceito_como_declarado'
        assert linha['nota_crsc'] is None

    def test_nao_revela_quem_votou_o_que(self):
        """A escolha do usuário: consolidado por item, sem voto nominal."""
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()

        linha = self._linha_do(montar_deliberacao_para_avaliado(self.processo), self.anexo)

        for membro in self.membros:
            assert str(membro.pessoa.nome) not in str(linha)

    def test_motivo_do_indeferimento_vem_com_a_redacao_do_decreto(self):
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()

        dados = montar_deliberacao_para_avaliado(self.processo)

        assert dados['deferido'] is False
        assert any('pontuação' in motivo.lower() for motivo in dados['motivos'])

    def test_processo_anterior_a_crsc_nao_finge_ter_deliberacao(self):
        """Processo finalizado no fluxo antigo (média dos auxiliares) não tem o que consolidar."""
        dados = montar_deliberacao_para_avaliado(self.processo)

        assert dados['sem_deliberacao_crsc'] is True


@pytest.mark.django_db(databases='__all__')
class TestAbaNaTelaDoProcesso(BaseProcessoDeliberado):
    """A aba na tela do processo: quando aparece, e com que números."""

    def _abrir_processo(self):
        self.client.login(user=self.servidor_a.get_user())
        return self.client.get(f'/rsc_tae/visualizar/{self.processo.id}/')

    def test_aba_aparece_para_o_avaliado_com_o_processo_finalizado(self):
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()

        html = self._abrir_processo().content.decode()

        assert 'data-tab="deliberacao"' in html
        assert 'Pontuação final abaixo do mínimo do nível.' in html

    def test_aba_nao_aparece_enquanto_a_crsc_delibera(self):
        """Antes da decisão o avaliado não acompanha a deliberação em curso."""
        self.processo.situacao = SituacaoProcesso.AGUARDANDO_CRSC
        self.processo.save()

        html = self._abrir_processo().content.decode()

        assert 'data-tab="deliberacao"' not in html

    def test_resumo_da_avaliacao_mostra_o_total_consolidado_pela_crsc(self):
        """Antes, a tela somava o bruto dos auxiliares e divergia do parecer."""
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()
        self.client.login(user=self.servidor_a.get_user())

        resposta = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliacao/resumo/')

        consolidado = montar_deliberacao_para_avaliado(self.processo)['resumo']['total_pontos']
        assert resposta.context['total_pontos_validados'] == consolidado


@pytest.mark.django_db(databases='__all__')
class TestNadaDeVotoNominal(BaseProcessoDeliberado):
    """A promessa do módulo: nada que ligue um nome a um voto chega ao template.

    Enquanto a deliberação viajava como model, ``deliberacao.deliberado_por_vinculo`` e
    ``deliberacao.processo.votos_deliberacao_final`` estavam a um ponto de distância na
    resolução de variáveis do Django — bastava um ajuste no template para expor o voto
    nominal que a decisão de produto exclui.
    """

    def test_a_deliberacao_chega_ao_template_sem_vinculo_algum(self):
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()

        deliberacao = montar_deliberacao_para_avaliado(self.processo)['deliberacao']

        assert not hasattr(deliberacao, 'deliberado_por_vinculo')
        assert not hasattr(deliberacao, 'processo')

    def test_a_justificativa_continua_chegando(self):
        """O que foi tirado é o vínculo, não o conteúdo."""
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()

        deliberacao = montar_deliberacao_para_avaliado(self.processo)['deliberacao']

        assert deliberacao['justificativa'] == 'Pontuação final abaixo do mínimo do nível.'


@pytest.mark.django_db(databases='__all__')
class TestProcessoAnteriorACRSC(BaseProcessoDeliberado):
    """Processo decidido no fluxo antigo: a decisão existiu, só não foi colegiada."""

    def test_anexo_contestado_nao_aparece_como_deliberacao_pendente(self):
        """Dizer "sem deliberação concluída" num processo já decidido o faz parecer aberto."""
        linha = self._linha_do(montar_deliberacao_para_avaliado(self.processo), self.anexo)

        assert linha['estado'] == 'avaliado_pelos_auxiliares'
        assert linha['nota_auxiliares'] == Decimal('1')


@pytest.mark.django_db(databases='__all__')
class TestDetalhamentoDoResumo(BaseProcessoDeliberado):
    """O cabeçalho consolidado e a tabela de detalhamento têm de contar a mesma história."""

    def test_linha_do_anexo_consolidado_usa_a_nota_da_crsc(self):
        self._deliberar_item(Decimal('2'))
        self._deliberacao_final()
        self.client.login(user=self.servidor_a.get_user())

        resposta = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliacao/resumo/')

        anexos = [anexo for linha in resposta.context['linhas_avaliacao'] for anexo in linha['anexos']]
        contestado = next(anexo for anexo in anexos if anexo.id == self.anexo.id)
        assert contestado.pontos_validados == Decimal('2')
