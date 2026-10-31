"""Testes de fluxo completo da Remoção Interna (remanejamento).

Cobre o ciclo de vida de um edital de Remoção Interna TAE com cargos e área
configuráveis, do cadastro do edital até a homologação do resultado final:

1. Cadastro/configuração de edital com cargo simples (Assistente em Administração)
   e cargo com área + áreas correlatas (Técnico de Laboratório / Informática,
   correlatas Sistemas de Computação e Suporte em Informática).
2. Inscrições com mais de uma pessoa por cargo.
3. Servidor de cargo/área não configurados no edital não pode se inscrever.
4. Só é possível publicar o resultado parcial após a data prevista.
5. Processamento do resultado parcial após o prazo final de inscrições.
6. Assinatura/finalização do documento do resultado parcial.
7. Recurso deferido: candidato consegue ver a resposta.
8. Recurso indeferido: candidato consegue ver a resposta.
9. Resultado final só pode ser gerado após o resultado parcial finalizado.
10. Reprocessamento do resultado após os recursos.
11. Publicação/assinatura/finalização do documento do resultado final.
12. Homologação do resultado final após a data prevista.
13. Cargo correlato (ex.: ODONTOLOGO - 30H - DEC JUD) concorre na mesma lista e às
    mesmas vagas do cargo principal (ODONTOLOGO - 40 HORAS).

Cada teste (1-5) constrói seu próprio estado via fixtures/endpoints reais e é
independente dos demais, seguindo a convenção de ``test_fluxo_remanejamento.py``.
Os cenários 6-12 formam um único processo sequencial sobre o MESMO documento
(assinatura/finalização, recursos, reprocessamento, resultado final,
homologação): reconstruir esse encadeamento do zero em cada teste apenas
duplicaria toda a assinatura de documentos sem ganhar independência real, por
isso estão reunidos em um teste único e narrado por etapas.
"""

import datetime

import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType

# garante o import de suap/urls.py (e da api ninja) antes do primeiro freeze_time: sob
# freeze_time o resolver de URLs reimporta suap/urls.py e a api ninja recusa registrar o
# mesmo router duas vezes.
import suap.urls
from comum.models import Configuracao
from comum.pytest_fixtures import assert_no_validation_errors
from djtools.middleware import threadlocals as tl
from documento_eletronico.assinar_documento import assinar_documento_com_senha
from documento_eletronico.models import Documento, HipoteseLegal, ModeloDocumento, TipoDocumentoTexto
from freezegun import freeze_time
from remanejamento.models import (
    CriterioClassificacao,
    CriterioClassificacaoChoices,
    Edital,
    EditalCriterioClassificacao,
    Inscricao,
    InscricaoContemplada,
    VagaEdital,
)
from rh.models import CargoEmprego, CargoEmpregoArea, Papel, Servidor, TipoUnidadeOrganizacional, UnidadeOrganizacional

DATAS_EDITAL = {
    'inicio_inscricoes': '01/01/2025',
    'inicio_inscricoes_time': '00:00',
    'fim_inscricoes': '10/01/2025',
    'fim_inscricoes_time': '23:59:59',
    'inicio_recursos': '11/01/2025',
    'inicio_recursos_time': '00:00:00',
    'fim_recursos': '15/01/2025',
    'fim_recursos_time': '23:59:59',
    'resultado_recursos': '16/01/2025',
    'resultado_recursos_time': '00:00:00',
    'data_resultado_parcial': '11/01/2025',
    'data_resultado_parcial_time': '00:00:00',
    'inicio_resultados': '16/01/2025',
    'inicio_resultados_time': '00:00:00',
    'data_homologacao_resultado': '20/01/2025',
    'data_homologacao_resultado_time': '00:00:00',
}

DADOS_INSCRICAO_PADRAO = {
    'concurso_ingresso_eh_ifrn': True,
    'classificacao_concurso': '1',
    'dou_numero': '1',
    'dou_data': '01/02/2000',
    'dou_pagina': '1',
    'dou_sessao': '1',
}


@pytest.mark.django_db(databases='__all__')
class TestFluxoRemocaoInterna:
    @pytest.fixture(autouse=True)
    def _setup(self, estrutura_remocao):
        self.estrutura = estrutura_remocao
        self.client = estrutura_remocao.client

        # corrige a sigla das UOs SIAPE dos campi: por padrão fica em branco, mas
        # o processamento de resultado resolve o campus de destino casando pela sigla.
        UnidadeOrganizacional.objects.filter(pk=estrutura_remocao.campus_a_suap_siape.pk).update(sigla='A0')
        UnidadeOrganizacional.objects.filter(pk=estrutura_remocao.campus_b_suap_siape.pk).update(sigla='B0')

        grupo_cargo = estrutura_remocao.grupo_cargo_emprego
        self.cargo_assistente = CargoEmprego.objects.create(
            codigo='RI001', nome='Assistente em Administração', grupo_cargo_emprego=grupo_cargo, sigla_escolaridade='01', cargo_suap=True
        )
        self.cargo_tecnico_lab = CargoEmprego.objects.create(
            codigo='RI002', nome='Técnico de Laboratório', grupo_cargo_emprego=grupo_cargo, sigla_escolaridade='01', cargo_suap=True
        )
        self.area_informatica = CargoEmpregoArea.objects.create(cargo_emprego=self.cargo_tecnico_lab, descricao='Informática')
        self.area_sistemas = CargoEmpregoArea.objects.create(cargo_emprego=self.cargo_tecnico_lab, descricao='Sistemas de Computação')
        self.area_suporte = CargoEmpregoArea.objects.create(cargo_emprego=self.cargo_tecnico_lab, descricao='Suporte em Informática')

        # EditalForm.cargos usa CargoEmprego.utilizados (só cargos com pelo menos um servidor
        # vinculado); vincula alguém desde já para que o edital possa ser criado em qualquer teste.
        Servidor.objects.filter(pk=estrutura_remocao.servidor_a.pk).update(cargo_emprego=self.cargo_assistente)
        Servidor.objects.filter(pk=estrutura_remocao.servidor_c.pk).update(
            cargo_emprego=self.cargo_tecnico_lab, cargo_emprego_area=self.area_informatica
        )
        for chave in ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d'):
            self._invalidar_cache_vinculo(getattr(estrutura_remocao, chave))

        self.admin_user = estrutura_remocao.admin.get_user()
        self.admin_user.groups.add(Group.objects.get(name='Coordenador de Remanejamento'))

    # ------------------------------------------------------------------ helpers

    def _invalidar_cache_vinculo(self, servidor):
        """``comum.models.User.VINCULOS``/``.relacionamento`` cacheiam o vínculo resolvido em um
        dict de classe (processo, não por request): sobrevive ao rollback de cada teste e a
        `Servidor.objects.filter(...).update(...)` não o invalida, então sem isto o segundo teste
        que reatribui o cargo de um mesmo servidor herda o cargo do teste anterior."""
        servidor.get_user().reset_vinculo()

    def _definir_servidor(self, servidor, cargo, area=None):
        Servidor.objects.filter(pk=servidor.pk).update(
            cargo_emprego=cargo, cargo_emprego_area=area, data_inicio_exercicio_no_cargo=datetime.date(2010, 1, 1)
        )
        self._invalidar_cache_vinculo(servidor)
        return Servidor.objects.get(pk=servidor.pk)

    def _criar_edital(self, titulo, cargos=None):
        self.client.login(username=self.admin_user.username, password='123')
        dados = dict(
            DATAS_EDITAL,
            categoria=Edital.TAE,
            titulo=titulo,
            descricao='Descrição',
            chave_hash='chave',
            cargos=[cargo.pk for cargo in cargos or (self.cargo_assistente, self.cargo_tecnico_lab)],
            coordenadores=[self.admin_user.pk],
            campus=[self.estrutura.campus_a_suap.pk, self.estrutura.campus_b_suap.pk],
        )
        resposta = self.client.post('/admin/remanejamento/edital/add/', dados)
        assert_no_validation_errors(resposta)
        return Edital.objects.get(titulo=titulo)

    def _configurar_vagas(self, edital, vagas_assistente=(0, 1), vagas_tecnico=(0, 1)):
        campus_a = self.estrutura.campus_a_suap
        campus_b = self.estrutura.campus_b_suap

        resposta = self.client.post(
            f'/remanejamento/edital/{edital.pk}/configurar_cargos/',
            {
                f'{self.cargo_assistente.pk}': True,
                f'{self.cargo_tecnico_lab.pk}_{self.area_informatica.pk}': True,
            },
        )
        assert resposta.status_code == 302

        vaga_assistente_a = VagaEdital.objects.get(edital=edital, cargo=self.cargo_assistente, campus=campus_a)
        vaga_assistente_b = VagaEdital.objects.get(edital=edital, cargo=self.cargo_assistente, campus=campus_b)
        vaga_tecnico_a = VagaEdital.objects.get(edital=edital, cargo=self.cargo_tecnico_lab, campus=campus_a)
        vaga_tecnico_b = VagaEdital.objects.get(edital=edital, cargo=self.cargo_tecnico_lab, campus=campus_b)

        resposta = self.client.post(
            f'/remanejamento/edital/{edital.pk}/vagaedital_id/{vaga_assistente_a.pk}/cadastrar_vagas/',
            {f'{vaga_assistente_a.pk}': vagas_assistente[0], f'{vaga_assistente_b.pk}': vagas_assistente[1]},
        )
        assert resposta.status_code == 302
        resposta = self.client.post(
            f'/remanejamento/edital/{edital.pk}/vagaedital_id/{vaga_tecnico_a.pk}/cadastrar_vagas/',
            {f'{vaga_tecnico_a.pk}': vagas_tecnico[0], f'{vaga_tecnico_b.pk}': vagas_tecnico[1]},
        )
        assert resposta.status_code == 302

        resposta = self.client.post(
            f'/remanejamento/edital/vagaedital_id/{vaga_tecnico_a.pk}/cadastrar_areas_correlatas/',
            {'areas_correlatas': [self.area_sistemas.pk, self.area_suporte.pk]},
        )
        assert resposta.status_code == 302

        # os objetos acima foram lidos ANTES dos POSTs que alteram qtd_edital/areas_correlatas
        vaga_assistente_a.refresh_from_db()
        vaga_assistente_b.refresh_from_db()
        vaga_tecnico_a.refresh_from_db()
        vaga_tecnico_b.refresh_from_db()

        return {
            'assistente_a': vaga_assistente_a,
            'assistente_b': vaga_assistente_b,
            'tecnico_a': vaga_tecnico_a,
            'tecnico_b': vaga_tecnico_b,
        }

    def _inscrever(self, servidor, edital, campus_preferencia_pk, campus_origem=None, validar=True):
        self.client.login(username=servidor.get_user().username, password='123')
        dados = dict(
            DADOS_INSCRICAO_PADRAO,
            inicio_exercicio='01/01/2000',
            jornada_trabalho=servidor.jornada_trabalho_id,
            **{f'campus_{campus_preferencia_pk}': 1},
        )
        resposta = self.client.post(edital.get_url_inscrever(), dados)
        assert resposta.status_code == 302, f'status={resposta.status_code}\n{resposta.content.decode()[-2000:]}'
        assert_no_validation_errors(resposta)
        inscricao = Inscricao.objects.get(edital=edital, servidor=servidor)
        if campus_origem is not None or validar:
            Inscricao.objects.filter(pk=inscricao.pk).update(
                campus_origem_ajustado=campus_origem,
                validado_por=self.admin_user.get_vinculo() if validar else None,
            )
        return Inscricao.objects.get(pk=inscricao.pk)

    def _criar_infra_documentos(self):
        tipo = TipoDocumentoTexto.objects.create(nome='Resultado de Remoção Interna - Tipo', sigla='RRI', vincular_pessoa=False)
        modelo = ModeloDocumento.objects.create(
            nome='Resultado de Remoção Interna',
            corpo_padrao='{{ resultado_html }}',
            tipo_documento_texto=tipo,
            permite_nivel_acesso_publico=True,
            nivel_acesso_padrao=Documento.NIVEL_ACESSO_PUBLICO,
            ativo=True,
        )
        HipoteseLegal.objects.get_or_create(pk=6, defaults={'nivel_acesso': 'Público', 'descricao': 'Hipótese Scratch', 'base_legal': 'Art. X'})
        Configuracao.objects.create(
            app='rh', chave='setor_remocaointerna_rh', valor=str(self.estrutura.setor_re_suap.pk), descricao='Setor Remoção Interna RH'
        )
        # a raiz da árvore de setores não tem UO própria: sem isso,
        # get_variaveis()/get_diretor_geral() sobe recursivamente até `setor.superior.uo`
        # ser None e explode. Uma UO na raiz encerra a recursão (sem diretor geral cadastrado,
        # o código já trata isso normalmente como "Sem Reitor").
        tipo_uo = TipoUnidadeOrganizacional.objects.get(pk=4)
        UnidadeOrganizacional.objects.suap().get_or_create(
            setor=self.estrutura.setor_raiz_suap, defaults={'codigo_protocolo': '00000', 'nome': 'Reitoria', 'sigla': 'REITORIA', 'tipo': tipo_uo}
        )
        return modelo

    def _criar_papel(self, servidor):
        return Papel.objects.create(
            vinculo=servidor.get_vinculo(),
            tipo_papel=Papel.TIPO_PAPEL_CARGO,
            descricao=str(servidor.cargo_emprego),
            detalhamento=str(servidor.cargo_emprego),
            portaria='000',
            data_inicio=datetime.date(2000, 1, 1),
            papel_content_type=ContentType.objects.get_for_model(CargoEmprego),
            papel_content_id=servidor.cargo_emprego_id,
        )

    def _assinar_e_finalizar(self, documento, user, papel):
        tl.context.user = user
        documento.concluir()
        documento.save()
        assinar_documento_com_senha(documento, user, papel)
        return documento.__class__.objects.get(pk=documento.pk)

    # ------------------------------------------------------------------ cenário 1

    def test_cadastrar_e_configurar_edital_com_cargos_e_areas_correlatas(self):
        with freeze_time('2025-01-01 08:00:00'):
            edital = self._criar_edital('Remoção Interna - Cenário 1')
            vagas = self._configurar_vagas(edital)

        assert vagas['assistente_b'].qtd_edital == 1
        assert vagas['tecnico_b'].qtd_edital == 1
        assert VagaEdital.objects.filter(edital=edital, cargo=self.cargo_assistente).count() == 2
        assert VagaEdital.objects.filter(edital=edital, cargo=self.cargo_tecnico_lab, cargo_emprego_area=self.area_informatica).count() == 2
        correlatas = set(vagas['tecnico_a'].areas_correlatas.values_list('pk', flat=True))
        assert correlatas == {self.area_sistemas.pk, self.area_suporte.pk}

    # ------------------------------------------------------------------ cenário 2

    def test_cadastrar_inscricoes_com_mais_de_uma_pessoa_por_cargo(self):
        campus_a = self.estrutura.campus_a_suap
        campus_b = self.estrutura.campus_b_suap

        with freeze_time('2025-01-01 08:00:00'):
            edital = self._criar_edital('Remoção Interna - Cenário 2')
            self._configurar_vagas(edital)

            servidor_a = self._definir_servidor(self.estrutura.servidor_a, self.cargo_assistente)
            servidor_b = self._definir_servidor(self.estrutura.servidor_b, self.cargo_assistente)
            servidor_c = self._definir_servidor(self.estrutura.servidor_c, self.cargo_tecnico_lab, self.area_informatica)
            servidor_d = self._definir_servidor(
                self.estrutura.servidor_d, self.cargo_tecnico_lab, self.area_sistemas
            )  # área correlata, também elegível

            self._inscrever(servidor_a, edital, campus_b.pk, campus_origem=campus_a)
            self._inscrever(servidor_b, edital, campus_a.pk, campus_origem=campus_a)
            self._inscrever(servidor_c, edital, campus_b.pk, campus_origem=campus_a)
            self._inscrever(servidor_d, edital, campus_a.pk, campus_origem=campus_a)

        inscritos_assistente = Inscricao.objects.filter(edital=edital, servidor__cargo_emprego=self.cargo_assistente, confirmada=True)
        inscritos_tecnico = Inscricao.objects.filter(edital=edital, servidor__cargo_emprego=self.cargo_tecnico_lab, confirmada=True)
        assert inscritos_assistente.count() == 2
        assert inscritos_tecnico.count() == 2

    # ------------------------------------------------------------------ cenário 3

    def test_servidor_de_cargo_ou_area_nao_configurada_nao_pode_se_inscrever(self):
        campus_a = self.estrutura.campus_a_suap

        with freeze_time('2025-01-01 08:00:00'):
            edital = self._criar_edital('Remoção Interna - Cenário 3')
            self._configurar_vagas(edital)

            # servidor_b permanece com o cargo genérico da fixture,
            # que não está entre os cargos do edital.
            servidor_fora_do_cargo = self.estrutura.servidor_b
            assert not edital.cargos.filter(pk=servidor_fora_do_cargo.cargo_emprego_id).exists()

            area_nao_configurada = CargoEmpregoArea.objects.create(cargo_emprego=self.cargo_tecnico_lab, descricao='Redes')
            servidor_fora_da_area = self._definir_servidor(self.estrutura.servidor_d, self.cargo_tecnico_lab, area_nao_configurada)

            self.client.login(username=servidor_fora_do_cargo.get_user().username, password='123')
            resposta_cargo = self.client.post(edital.get_url_inscrever(), {**DADOS_INSCRICAO_PADRAO, 'inicio_exercicio': '01/01/2000'})

            self.client.login(username=servidor_fora_da_area.get_user().username, password='123')
            resposta_area = self.client.post(
                edital.get_url_inscrever(),
                dict(
                    DADOS_INSCRICAO_PADRAO,
                    inicio_exercicio='01/01/2000',
                    jornada_trabalho=servidor_fora_da_area.jornada_trabalho_id,
                    **{f'campus_{campus_a.pk}': 1},
                ),
            )

        assert resposta_cargo.status_code == 403
        assert resposta_area.status_code == 403
        assert not Inscricao.objects.filter(edital=edital, servidor=servidor_fora_do_cargo).exists()
        assert not Inscricao.objects.filter(edital=edital, servidor=servidor_fora_da_area).exists()

    # ------------------------------------------------------------------ cenário 4

    def test_so_publica_resultado_parcial_apos_prazo_previsto(self):
        with freeze_time('2025-01-01 08:00:00'):
            edital = self._criar_edital('Remoção Interna - Cenário 4')
            self._configurar_vagas(edital)

        self._criar_infra_documentos()

        with freeze_time('2025-01-10 08:00:00'):  # antes de data_resultado_parcial (11/01)
            self.client.login(username=self.admin_user.username, password='123')
            resposta_antes = self.client.get(f'/remanejamento/edital/{edital.pk}/publicar_resultado_parcial/')

        assert resposta_antes.status_code == 403
        edital.refresh_from_db()
        assert edital.resultado_parcial_documentotexto is None

        with freeze_time('2025-01-12 08:00:00'):  # após data_resultado_parcial
            resposta_depois = self.client.get(f'/remanejamento/edital/{edital.pk}/publicar_resultado_parcial/', follow=True)

        assert resposta_depois.status_code == 200
        edital.refresh_from_db()
        assert edital.resultado_parcial_documentotexto is not None

    # ------------------------------------------------------------------ cenário 5

    def test_processar_resultado_parcial_apos_prazo_final_gera_contemplados_esperados(self):
        campus_a = self.estrutura.campus_a_suap
        campus_b = self.estrutura.campus_b_suap

        with freeze_time('2025-01-01 08:00:00'):
            edital = self._criar_edital('Remoção Interna - Cenário 5')
            self._configurar_vagas(edital)

            servidor_a = self._definir_servidor(self.estrutura.servidor_a, self.cargo_assistente)  # pede mudança -> contemplado
            servidor_b = self._definir_servidor(self.estrutura.servidor_b, self.cargo_assistente)  # fica -> não contemplado
            servidor_c = self._definir_servidor(
                self.estrutura.servidor_c, self.cargo_tecnico_lab, self.area_informatica
            )  # pede mudança -> contemplado

            self._inscrever(servidor_a, edital, campus_b.pk, campus_origem=campus_a)
            self._inscrever(servidor_b, edital, campus_a.pk, campus_origem=campus_a)
            self._inscrever(servidor_c, edital, campus_b.pk, campus_origem=campus_a)

        with freeze_time('2025-01-12 08:00:00'):  # após fim_inscricoes (10/01)
            self.client.login(username=self.admin_user.username, password='123')
            resposta = self.client.get(f'/remanejamento/edital/{edital.pk}/processar/', follow=True)

        assert resposta.status_code == 200
        contempladas = {
            c.inscricao.servidor.matricula: c.campus_destino.sigla
            for c in InscricaoContemplada.objects.filter(inscricao__edital=edital, situacao=InscricaoContemplada.CONTEMPLADO)
        }
        assert contempladas == {servidor_a.matricula: 'B0', servidor_c.matricula: 'B0'}
        assert not InscricaoContemplada.objects.filter(inscricao__edital=edital, inscricao__servidor=servidor_b).exists()

    # ------------------------------------------------------- cenários 6 a 12 (ciclo do resultado)

    def test_ciclo_resultado_parcial_recursos_resultado_final_homologacao(self):
        campus_a = self.estrutura.campus_a_suap
        campus_b = self.estrutura.campus_b_suap

        modelo = self._criar_infra_documentos()
        assert modelo.nome == 'Resultado de Remoção Interna'
        papel_coordenador = self._criar_papel(self.estrutura.admin)

        with freeze_time('2025-01-01 08:00:00'):
            edital = self._criar_edital('Remoção Interna - Ciclo Completo')
            self._configurar_vagas(edital)

            servidor_a = self._definir_servidor(self.estrutura.servidor_a, self.cargo_assistente)
            servidor_c = self._definir_servidor(self.estrutura.servidor_c, self.cargo_tecnico_lab, self.area_informatica)

            inscricao_a = self._inscrever(servidor_a, edital, campus_b.pk, campus_origem=campus_a)
            inscricao_c = self._inscrever(servidor_c, edital, campus_b.pk, campus_origem=campus_a)

        # ---- cenário 5 (pré-condição do ciclo): processa resultado parcial após o prazo final
        with freeze_time('2025-01-12 08:00:00'):
            self.client.login(username=self.admin_user.username, password='123')
            resposta = self.client.get(f'/remanejamento/edital/{edital.pk}/processar/', follow=True)
            assert resposta.status_code == 200
            assert InscricaoContemplada.objects.filter(inscricao__edital=edital, situacao=InscricaoContemplada.CONTEMPLADO).count() == 2

            resposta = self.client.get(f'/remanejamento/edital/{edital.pk}/publicar_resultado_parcial/', follow=True)
            assert resposta.status_code == 200
            edital.refresh_from_db()
            assert edital.resultado_parcial_documentotexto is not None

        # ---- cenário 6: assina e finaliza o documento do resultado parcial
        with freeze_time('2025-01-12 09:00:00'):
            self._assinar_e_finalizar(edital.resultado_parcial_documentotexto, self.admin_user, papel_coordenador)
        edital.refresh_from_db()
        assert edital.resultado_parcial_documentotexto.estah_finalizado

        # ---- cenário 9 (parte 1): antes da assinatura do parcial o resultado final não pode ser gerado
        # (o parcial já está finalizado agora; confirmamos o outro lado do portão: falta o prazo dos recursos)
        with freeze_time('2025-01-13 08:00:00'):  # ainda dentro do período de recursos (até 15/01)
            resposta = self.client.get(f'/remanejamento/edital/{edital.pk}/publicar_resultado_final/', follow=True)
        assert 'Resultado Final somente pode ser publicado' in resposta.content.decode()
        edital.refresh_from_db()
        assert edital.resultado_final_documentotexto is None

        # ---- cenário 7: recurso deferido, candidato consegue ver a resposta após o prazo de resultado dos recursos
        with freeze_time('2025-01-13 08:00:00'):
            self.client.login(username=servidor_a.get_user().username, password='123')
            resposta = self.client.post(f'/remanejamento/inscricao/{inscricao_a.pk}/', {'recurso_texto': 'Solicito revisão da minha classificação.'})
            assert_no_validation_errors(resposta)

            self.client.login(username=self.admin_user.username, password='123')
            resposta = self.client.post(
                f'/remanejamento/inscricao/{inscricao_a.pk}/',
                {'avaliacao_recurso': 'Recurso deferido, mantida a alocação.', 'situacao_recurso': 'DEFERIDO'},
            )
            assert_no_validation_errors(resposta)

        inscricao_a.refresh_from_db()
        assert inscricao_a.situacao_recurso == 'DEFERIDO'

        with freeze_time('2025-01-13 08:00:00'):
            self.client.login(username=servidor_a.get_user().username, password='123')
            resposta_antes = self.client.get(f'/remanejamento/inscricao/{inscricao_a.pk}/')
        assert resposta_antes.context['pode_ver_resultado_recurso'] is False

        with freeze_time('2025-01-16 08:00:00'):  # após resultado_recursos (16/01)
            self.client.login(username=servidor_a.get_user().username, password='123')
            resposta_depois = self.client.get(f'/remanejamento/inscricao/{inscricao_a.pk}/')
        assert resposta_depois.context['pode_ver_resultado_recurso'] is True
        assert 'Recurso deferido, mantida a alocação.' in resposta_depois.content.decode()

        # ---- cenário 8: recurso indeferido, candidato consegue ver a resposta
        with freeze_time('2025-01-13 08:00:00'):
            self.client.login(username=servidor_c.get_user().username, password='123')
            resposta = self.client.post(f'/remanejamento/inscricao/{inscricao_c.pk}/', {'recurso_texto': 'Solicito revisão da minha classificação.'})
            assert_no_validation_errors(resposta)

            self.client.login(username=self.admin_user.username, password='123')
            resposta = self.client.post(
                f'/remanejamento/inscricao/{inscricao_c.pk}/',
                {'avaliacao_recurso': 'Recurso indeferido, critérios corretamente aplicados.', 'situacao_recurso': 'INDEFERIDO'},
            )
            assert_no_validation_errors(resposta)

        inscricao_c.refresh_from_db()
        assert inscricao_c.situacao_recurso == 'INDEFERIDO'

        with freeze_time('2025-01-16 08:00:00'):
            self.client.login(username=servidor_c.get_user().username, password='123')
            resposta = self.client.get(f'/remanejamento/inscricao/{inscricao_c.pk}/')
        assert resposta.context['pode_ver_resultado_recurso'] is True
        assert 'Recurso indeferido, critérios corretamente aplicados.' in resposta.content.decode()

        # ---- cenário 10: reprocessa o resultado após os recursos e confere os contemplados
        # Como o resultado parcial já foi publicado (situação PUBLICADA_PARCIAL) e finalizado,
        # processar_resultado() não recria essas inscrições como CONTEMPLADO — apenas as que ainda
        # não estão em uma situação final. O reprocessamento mantém a alocação já publicada.
        with freeze_time('2025-01-16 09:00:00'):
            self.client.login(username=self.admin_user.username, password='123')
            resposta = self.client.get(f'/remanejamento/edital/{edital.pk}/processar/', follow=True)
        assert resposta.status_code == 200
        contempladas = {
            c.inscricao.servidor.matricula: c.campus_destino.sigla
            for c in InscricaoContemplada.objects.filter(
                inscricao__edital=edital, situacao__in=[InscricaoContemplada.CONTEMPLADO, InscricaoContemplada.PUBLICADA_PARCIAL]
            )
        }
        assert contempladas == {servidor_a.matricula: 'B0', servidor_c.matricula: 'B0'}

        # ---- cenário 9 (parte 2) + 11: publica, assina e finaliza o resultado final
        with freeze_time('2025-01-17 08:00:00'):  # após fim_recursos (15/01) e inicio_resultados (16/01)
            resposta = self.client.get(f'/remanejamento/edital/{edital.pk}/publicar_resultado_final/', follow=True)
        assert resposta.status_code == 200
        edital.refresh_from_db()
        assert edital.resultado_final_documentotexto is not None

        with freeze_time('2025-01-17 09:00:00'):
            self._assinar_e_finalizar(edital.resultado_final_documentotexto, self.admin_user, papel_coordenador)
        edital.refresh_from_db()
        assert edital.resultado_final_documentotexto.estah_finalizado

        # ---- cenário 12: homologação, só possível após a data prevista e com o resultado final finalizado
        with freeze_time('2025-01-18 08:00:00'):  # antes de data_homologacao_resultado (20/01)
            resposta_antes = self.client.get(f'/remanejamento/edital/{edital.pk}/publicar_homologacao_resultado_final/', follow=True)
        assert 'somente pode ser publicada' in resposta_antes.content.decode()
        edital.refresh_from_db()
        assert edital.resultado_final_homologacao_documentotexto is None

        with freeze_time('2025-01-21 08:00:00'):  # após data_homologacao_resultado
            resposta_depois = self.client.get(f'/remanejamento/edital/{edital.pk}/publicar_homologacao_resultado_final/', follow=True)
        assert resposta_depois.status_code == 200
        edital.refresh_from_db()
        assert edital.resultado_final_homologacao_documentotexto is not None

        with freeze_time('2025-01-21 09:00:00'):
            self._assinar_e_finalizar(edital.resultado_final_homologacao_documentotexto, self.admin_user, papel_coordenador)
        edital.refresh_from_db()
        assert edital.resultado_final_homologacao_documentotexto.estah_finalizado

    # ------------------------------------------------------------------ cenário 13

    def test_cargo_correlato_concorre_as_vagas_do_cargo_principal(self):
        campus_a = self.estrutura.campus_a_suap
        campus_b = self.estrutura.campus_b_suap
        grupo_cargo = self.estrutura.grupo_cargo_emprego
        cargo_principal = CargoEmprego.objects.create(
            codigo='RI003', nome='ODONTOLOGO - 40 HORAS', grupo_cargo_emprego=grupo_cargo, sigla_escolaridade='01', cargo_suap=True
        )
        cargo_correlato = CargoEmprego.objects.create(
            codigo='RI004', nome='ODONTOLOGO - 30H - DEC JUD', grupo_cargo_emprego=grupo_cargo, sigla_escolaridade='01', cargo_suap=True
        )

        with freeze_time('2025-01-01 08:00:00'):
            servidor_principal = self._definir_servidor(self.estrutura.servidor_a, cargo_principal)
            servidor_correlato = self._definir_servidor(self.estrutura.servidor_c, cargo_correlato)
            # mais antigo no cargo: deve ficar à frente do servidor do cargo principal na lista única
            Servidor.objects.filter(pk=servidor_correlato.pk).update(data_inicio_exercicio_no_cargo=datetime.date(2005, 1, 1))

            edital = self._criar_edital('Remoção Interna - Cenário 13', cargos=[cargo_principal, cargo_correlato])
            criterio, _ = CriterioClassificacao.objects.get_or_create(nome=CriterioClassificacaoChoices.DATA_INICIO_EXERCICIO_CARGO_NO_ORGAO)
            EditalCriterioClassificacao.objects.create(edital=edital, criterio_classificacao=criterio, ordem=1)

            # vagas só para o cargo principal; o correlato concorre a elas
            resposta = self.client.post(f'/remanejamento/edital/{edital.pk}/configurar_cargos/', {f'{cargo_principal.pk}': True})
            assert resposta.status_code == 302
            vaga_a = VagaEdital.objects.get(edital=edital, cargo=cargo_principal, campus=campus_a)
            vaga_b = VagaEdital.objects.get(edital=edital, cargo=cargo_principal, campus=campus_b)
            resposta = self.client.post(
                f'/remanejamento/edital/{edital.pk}/vagaedital_id/{vaga_a.pk}/cadastrar_vagas/', {f'{vaga_a.pk}': 0, f'{vaga_b.pk}': 1}
            )
            assert resposta.status_code == 302
            resposta = self.client.post(
                f'/remanejamento/edital/vagaedital_id/{vaga_a.pk}/cadastrar_cargos_correlatos/', {'cargos_correlatos': [cargo_correlato.pk]}
            )
            assert resposta.status_code == 302

            self._inscrever(servidor_principal, edital, campus_b.pk, campus_origem=campus_a)
            self._inscrever(servidor_correlato, edital, campus_b.pk, campus_origem=campus_a)

        assert set(vaga_b.cargos_correlatos.values_list('pk', flat=True)) == {cargo_correlato.pk}
        assert not edital.get_cargo_areas_sem_inscricoes().exists()

        with freeze_time('2025-01-12 08:00:00'):  # após fim_inscricoes (10/01)
            self.client.login(username=self.admin_user.username, password='123')
            resposta = self.client.get(f'/remanejamento/edital/{edital.pk}/processar/', follow=True)

        assert resposta.status_code == 200
        contempladas = {
            c.inscricao.servidor.matricula: c.campus_destino.sigla
            for c in InscricaoContemplada.objects.filter(inscricao__edital=edital, situacao=InscricaoContemplada.CONTEMPLADO)
        }
        assert contempladas == {servidor_correlato.matricula: 'B0'}
        assert list(edital.get_dados_classificados_por_cargo_resultado()) == ['ODONTOLOGO - 40 HORAS']
