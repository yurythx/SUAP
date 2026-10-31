from datetime import date
from decimal import Decimal

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile


ProcessoRSCTae = apps.get_model('rsc_tae', 'ProcessoRSCTae')
Nivel = apps.get_model('rsc_tae', 'Nivel')
Requisito = apps.get_model('rsc_tae', 'Requisito')
GrupoSaberCompetencia = apps.get_model('rsc_tae', 'GrupoSaberCompetencia')
RolSaberCompetencia = apps.get_model('rsc_tae', 'RolSaberCompetencia')
RolSaberCompetenciaAnexo = apps.get_model('rsc_tae', 'RolSaberCompetenciaAnexo')
AvaliacaoAnexoRSCTae = apps.get_model('rsc_tae', 'AvaliacaoAnexoRSCTae')
AvaliacaoProcessoRSCTae = apps.get_model('rsc_tae', 'AvaliacaoProcessoRSCTae')
DocumentoPreliminarRSCTae = apps.get_model('rsc_tae', 'DocumentoPreliminarRSCTae')
AvaliacaoDocumentoPreliminarRSCTae = apps.get_model('rsc_tae', 'AvaliacaoDocumentoPreliminarRSCTae')
DeliberacaoCRSCRSCTae = apps.get_model('rsc_tae', 'DeliberacaoCRSCRSCTae')
BancoPontosRSCTae = apps.get_model('rsc_tae', 'BancoPontosRSCTae')
MovimentoBancoPontosRSCTae = apps.get_model('rsc_tae', 'MovimentoBancoPontosRSCTae')
ComissaoRSCTae = apps.get_model('rsc_tae', 'ComissaoRSCTae')
MembroComissaoRSCTae = apps.get_model('rsc_tae', 'MembroComissaoRSCTae')
CategoriaMembroComissaoRSCTae = apps.get_model('rsc_tae', 'CategoriaMembroComissaoRSCTae')
ConfiguracaoRSCTae = apps.get_model('rsc_tae', 'ConfiguracaoRSCTae')
MemorialDescritivoRSCTae = apps.get_model('rsc_tae', 'MemorialDescritivoRSCTae')
Permission = apps.get_model('auth', 'Permission')

from rsc_tae.enums import MotivoIndeferimento, TipoDocumentoPreliminar  # noqa: E402

# Situações de processo
AGUARDANDO_PREENCHIMENTO = 1
AGUARDANDO_AVALIADOR = 2
EM_ANALISE = 3
DEFERIDO = 4
INDEFERIDO = 5
AGUARDANDO_VALIDACAO = 6
AGUARDANDO_CORRECAO = 7
AGUARDANDO_CRSC = 9

# Situações de avaliação de anexo
AV_PENDENTE = 1
AV_DEFERIDO = 2
AV_INDEFERIDO = 3


def _pdf():
    return b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'


@pytest.mark.django_db(databases='__all__')
class _RscTaeBase:
    """Setup compartilhado: nível, grupo, item, processo e dois anexos."""

    databases = '__all__'

    def _limpar_cache_permission(self):
        """Reimplementa o antigo SuapTestCase.limpar_cache_permission: limpa o cache de permissões dos servidores."""
        for key in ('servidor_a', 'servidor_b', 'servidor_c'):
            servidor = getattr(self, key, None)
            if not servidor:
                continue
            user = servidor.get_user()
            for attr in ('_group_perm_cache', '_user_perm_cache', '_perm_cache'):
                if hasattr(user, attr):
                    delattr(user, attr)

    def _tornar_membro_crsc_ativo(self, user, presidente=False, categoria_nome='CONSUP'):
        """Vincula o usuário como membro ATIVO da comissão ATIVA — exigido por validar/remanejar/deliberar (eh_membro_crsc_ativo).

        A categoria é obrigatória: a cota de deliberações por categoria (``status_cota_categoria``)
        não deixa deliberar quem está sem categoria. Cada usuário entra numa categoria própria para
        que um teste com vários votantes não esgote a cota de 2 sem querer.
        """
        comissao, _ = ComissaoRSCTae.objects.get_or_create(
            nome='Comissão CRSC-TAE (teste)',
            defaults={'data_inicio': '2020-01-01', 'ativa': True},
        )
        if not comissao.ativa:
            comissao.ativa = True
            comissao.save()
        categoria, _ = CategoriaMembroComissaoRSCTae.objects.get_or_create(nome=f'{categoria_nome} {user.username}')
        MembroComissaoRSCTae.objects.get_or_create(
            comissao=comissao,
            vinculo=user.get_vinculo(),
            defaults={'ativo': True, 'presidente': presidente, 'categoria': categoria},
        )
        self._limpar_cache_permission()

    @staticmethod
    def _criar_hierarquia_item():
        requisito, _ = Requisito.objects.get_or_create(
            numero=99,
            defaults={
                'descricao': 'Requisito de teste',
                'descricao_curta': 'Req. Teste',
                'numeral_romano': 'X',
            },
        )
        grupo, _ = GrupoSaberCompetencia.objects.get_or_create(
            requisito=requisito,
            numero=1,
            defaults={'pontuacao_unidade': Decimal('1.000')},
        )
        item, _ = RolSaberCompetencia.objects.get_or_create(
            numero=1,
            grupo=grupo,
            defaults={
                'titulo': 'Item de Teste',
                'descricao': 'Item criado para testes automatizados.',
                'unidade_medida': 'un',
            },
        )
        return requisito, grupo, item

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.nivel = Nivel.objects.create(
            nome='Nível Teste',
            numero_minimo_itens=0,
            pontuacao_minima=Decimal('0.00'),
        )
        _, _, self.item = self._criar_hierarquia_item()

        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=self.nivel,
        )
        self.anexo = RolSaberCompetenciaAnexo.objects.create(
            processo=self.processo,
            rol_saber_competencia=self.item,
            arquivo=SimpleUploadedFile('teste.pdf', _pdf(), content_type='application/pdf'),
            pontuacao=Decimal('3.00'),
            nome_original='teste.pdf',
        )
        self.anexo2 = RolSaberCompetenciaAnexo.objects.create(
            processo=self.processo,
            rol_saber_competencia=self.item,
            arquivo=SimpleUploadedFile('teste2.pdf', _pdf(), content_type='application/pdf'),
            pontuacao=Decimal('2.00'),
            nome_original='teste2.pdf',
        )


class RscTaeAvaliacaoViewsTestCase(_RscTaeBase):
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c')

    def test_avaliar_requires_permission(self):
        user = self.servidor_b.get_user()
        self.client.login(user=user)
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliar/')
        assert resp.status_code == 403

    def test_avaliar_allows_with_permission(self):
        user = self.servidor_b.get_user()
        perm = Permission.objects.get(codename='avaliar_processorsctae')
        user.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=EM_ANALISE,
            avaliador_atual=user.get_vinculo(),
        )
        self.client.login(user=user)
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliar/')
        assert resp.status_code == 200

    def test_avaliar_denies_own_process_even_with_permission(self):
        user = self.servidor_a.get_user()
        perm = Permission.objects.get(codename='avaliar_processorsctae')
        user.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=EM_ANALISE,
            avaliador_atual=user.get_vinculo(),
        )
        self.client.login(user=user)
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliar/')
        assert resp.status_code == 403

    def test_resumo_avaliacao_allows_process_owner(self):
        user = self.servidor_a.get_user()
        self.client.login(user=user)
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliacao/resumo/')
        assert resp.status_code == 200

    def test_relatorio_avaliacao_allows_owner_only_when_finalized(self):
        user = self.servidor_a.get_user()
        self.client.login(user=user)

        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliacao/relatorio/')
        assert resp.status_code == 403

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(situacao=DEFERIDO)
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliacao/relatorio/')
        assert resp.status_code == 200

    def test_avaliar_arquivo_requires_permission(self):
        user = self.servidor_b.get_user()
        self.client.login(user=user)
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/anexo/{self.anexo.id}/avaliar/')
        assert resp.status_code == 403

    def test_avaliar_arquivo_post_salva_avaliacao(self):
        user = self.servidor_b.get_user()
        perm = Permission.objects.get(codename='avaliar_processorsctae')
        user.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=EM_ANALISE,
            avaliador_atual=user.get_vinculo(),
        )
        self.client.login(user=user)

        url = f'/rsc_tae/processo/{self.processo.id}/anexo/{self.anexo.id}/avaliar/?_popup=1'
        resp = self.client.post(url, data={'acao': 'validar', 'pontuacao_validada': '2.50', 'observacao': 'OK'})
        # No POST de sucesso a view salva a avaliação e redireciona (httprr) para o próximo item.
        assert resp.status_code in (200, 302)

        av = AvaliacaoAnexoRSCTae.objects.get(anexo=self.anexo)
        assert av.situacao == AV_DEFERIDO
        assert str(av.pontuacao_validada) == '2.50'
        assert av.observacao == 'OK'
        assert av.avaliado_por == user

    def test_avaliacao_define_avaliador_atual_e_bloqueia_outros(self):
        perm = Permission.objects.get(codename='avaliar_processorsctae')

        avaliador_1 = self.servidor_b.get_user()
        avaliador_1.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=EM_ANALISE,
            avaliador_atual=avaliador_1.get_vinculo(),
        )
        self.client.login(user=avaliador_1)

        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/anexo/{self.anexo.id}/avaliar/?_popup=1',
            data={'acao': 'validar', 'pontuacao_validada': '2.50', 'observacao': 'OK'},
        )

        avaliador_2 = self.servidor_c.get_user()
        avaliador_2.user_permissions.add(perm)
        self._limpar_cache_permission()
        self.client.login(user=avaliador_2)

        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliar/')
        assert resp.status_code == 403

    def test_avaliacao_permite_depois_de_trocar_avaliador_atual(self):
        perm = Permission.objects.get(codename='avaliar_processorsctae')

        avaliador_1 = self.servidor_b.get_user()
        avaliador_1.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=EM_ANALISE,
            avaliador_atual=avaliador_1.get_vinculo(),
        )
        self.client.login(user=avaliador_1)
        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/anexo/{self.anexo.id}/avaliar/?_popup=1',
            data={'acao': 'validar', 'pontuacao_validada': '2.50', 'observacao': 'OK'},
        )

        avaliador_2 = self.servidor_c.get_user()
        avaliador_2.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(avaliador_atual=avaliador_2.get_vinculo())

        self.client.login(user=avaliador_2)
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/avaliar/')
        assert resp.status_code == 200

    def test_finalizar_avaliacao_vai_para_aguardando_crsc_quando_ultimo_avaliador_finaliza(self):
        """Quando o último avaliador finaliza, o processo vai para AGUARDANDO_CRSC (não DEFERIDO/INDEFERIDO)."""
        avaliador = self.servidor_b.get_user()
        perm = Permission.objects.get(codename='avaliar_processorsctae')
        avaliador.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=EM_ANALISE,
            avaliador_atual=avaliador.get_vinculo(),
        )

        AvaliacaoAnexoRSCTae.objects.update_or_create(
            anexo=self.anexo,
            avaliador_vinculo=avaliador.get_vinculo(),
            defaults={'situacao': AV_DEFERIDO, 'pontuacao_validada': Decimal('2.50')},
        )
        AvaliacaoAnexoRSCTae.objects.update_or_create(
            anexo=self.anexo2,
            avaliador_vinculo=avaliador.get_vinculo(),
            defaults={'situacao': AV_DEFERIDO, 'pontuacao_validada': Decimal('2.00')},
        )

        self.client.login(user=avaliador)
        url = f'/rsc_tae/processo/{self.processo.id}/avaliacao/finalizar/?_popup=1'
        resp = self.client.post(url, data={'confirmacao': 'on', 'senha': '123'})
        assert resp.status_code in (200, 302)

        processo = ProcessoRSCTae.objects.get(pk=self.processo.pk)
        assert processo.situacao == AGUARDANDO_CRSC

    def test_finalizar_avaliacao_nao_avanca_sem_todos_avaliadores(self):
        """Com dois avaliadores, o processo só avança quando ambos finalizarem."""
        perm = Permission.objects.get(codename='avaliar_processorsctae')

        avaliador_1 = self.servidor_b.get_user()
        avaliador_1.user_permissions.add(perm)
        avaliador_2 = self.servidor_c.get_user()
        avaliador_2.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(situacao=EM_ANALISE)
        processo_obj = ProcessoRSCTae.objects.get(pk=self.processo.pk)
        processo_obj.avaliadores.set([avaliador_1.get_vinculo(), avaliador_2.get_vinculo()])

        for avaliador in (avaliador_1, avaliador_2):
            AvaliacaoProcessoRSCTae.objects.update_or_create(
                processo=processo_obj,
                avaliador_vinculo=avaliador.get_vinculo(),
                defaults={'substituido': False, 'aceite': True},
            )
            for anexo in (self.anexo, self.anexo2):
                AvaliacaoAnexoRSCTae.objects.update_or_create(
                    anexo=anexo,
                    avaliador_vinculo=avaliador.get_vinculo(),
                    defaults={'situacao': AV_DEFERIDO, 'pontuacao_validada': Decimal('1.00')},
                )

        # Primeiro avaliador finaliza: ainda EM_ANALISE
        self.client.login(user=avaliador_1)
        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/avaliacao/finalizar/?_popup=1',
            data={'confirmacao': 'on', 'senha': '123'},
        )
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == EM_ANALISE

        # Segundo avaliador finaliza: agora avança para AGUARDANDO_CRSC
        self.client.login(user=avaliador_2)
        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/avaliacao/finalizar/?_popup=1',
            data={'confirmacao': 'on', 'senha': '123'},
        )
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_CRSC

    def test_finalizar_avaliacao_bloqueia_com_anexos_pendentes(self):
        """Finalização é bloqueada enquanto há arquivos sem avaliação."""
        avaliador = self.servidor_b.get_user()
        perm = Permission.objects.get(codename='avaliar_processorsctae')
        avaliador.user_permissions.add(perm)
        self._limpar_cache_permission()

        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=EM_ANALISE,
            avaliador_atual=avaliador.get_vinculo(),
        )

        # Apenas um dos dois anexos está avaliado
        AvaliacaoAnexoRSCTae.objects.update_or_create(
            anexo=self.anexo,
            avaliador_vinculo=avaliador.get_vinculo(),
            defaults={'situacao': AV_DEFERIDO, 'pontuacao_validada': Decimal('2.00')},
        )

        self.client.login(user=avaliador)
        url = f'/rsc_tae/processo/{self.processo.id}/avaliacao/finalizar/?_popup=1'
        resp = self.client.post(url, data={'confirmacao': 'on', 'senha': '123'})
        assert resp.status_code in (200, 302)

        processo = ProcessoRSCTae.objects.get(pk=self.processo.pk)
        assert processo.situacao == EM_ANALISE


class RscTaeFluxoProcessoTestCase(_RscTaeBase):
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c')
    _SIGN_CONCLUIR = {
        'declaracao_conformidade': 'on',
        'declaracao_rn05': 'on',
        'declaracao_rn08': 'on',
        'confirmacao': 'on',
        'senha': '123',
    }

    def _concluir_assinado(self):
        """Conclui o preenchimento no fluxo atual: exige declaração de conformidade + POST assinado."""
        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(declaracao_conformidade=True)
        return self.client.post(f'/rsc_tae/processo/{self.processo.id}/concluir_preenchimento/', data=self._SIGN_CONCLUIR)

    @pytest.fixture(autouse=True)
    def _setup_fluxo(self, _setup):
        Nivel.objects.filter(pk=self.nivel.pk).update(
            nome='Nível Fluxo',
            numero_minimo_itens=1,
            pontuacao_minima=Decimal('5.00'),
        )
        self.nivel.refresh_from_db()
        RolSaberCompetenciaAnexo.objects.create(
            processo=self.processo,
            rol_saber_competencia=self.item,
            arquivo=SimpleUploadedFile('fluxo.pdf', _pdf(), content_type='application/pdf'),
            pontuacao=Decimal('3.00'),
            nome_original='fluxo.pdf',
            descricao='Comprovante do item de teste.',
        )
        # A conclusão exige que todo anexo tenha descrição (inclui os anexos criados na base _setup).
        RolSaberCompetenciaAnexo.objects.filter(processo=self.processo).update(descricao='Comprovante do item de teste.')
        # A conclusão exige memorial descritivo com introdução e conclusão preenchidas.
        MemorialDescritivoRSCTae.objects.create(
            processo=self.processo,
            introducao='Introdução do memorial descritivo (teste).',
            conclusao='Conclusão do memorial descritivo (teste).',
        )

    def test_concluir_preenchimento_critica_se_nao_atingir_minimos(self):
        user = self.servidor_a.get_user()
        self.client.login(user=user)
        self._concluir_assinado()
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_PREENCHIMENTO

    def test_concluir_preenchimento_muda_para_aguardando_validacao_quando_ok(self):
        Nivel.objects.filter(pk=self.nivel.pk).update(pontuacao_minima=Decimal('3.00'))

        user = self.servidor_a.get_user()
        self.client.login(user=user)

        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            arquivo=SimpleUploadedFile('titulo.pdf', _pdf(), content_type='application/pdf'),
            nome_original='titulo.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            tipo=TipoDocumentoPreliminar.HOMOLOGACAO_ESTAGIO_PROBATORIO,
            arquivo=SimpleUploadedFile('homologacao.pdf', _pdf(), content_type='application/pdf'),
            nome_original='homologacao.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        self._concluir_assinado()
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_VALIDACAO

    def test_nao_permite_editar_apos_concluir(self):
        Nivel.objects.filter(pk=self.nivel.pk).update(pontuacao_minima=Decimal('3.00'))
        user = self.servidor_a.get_user()
        self.client.login(user=user)

        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            arquivo=SimpleUploadedFile('titulo.pdf', _pdf(), content_type='application/pdf'),
            nome_original='titulo.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            tipo=TipoDocumentoPreliminar.HOMOLOGACAO_ESTAGIO_PROBATORIO,
            arquivo=SimpleUploadedFile('homologacao.pdf', _pdf(), content_type='application/pdf'),
            nome_original='homologacao.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        self._concluir_assinado()

        resp_upload = self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/item/{self.item.id}/anexos/upload/',
            data={'arquivo': SimpleUploadedFile('x.pdf', _pdf(), content_type='application/pdf'), 'pontuacao': '1.00'},
        )
        assert resp_upload.status_code == 403

        anexo = RolSaberCompetenciaAnexo.objects.filter(processo=self.processo).first()
        resp_pts = self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/anexo/{anexo.id}/salvar_pontuacao/',
            data={'pontuacao': '9.00'},
        )
        assert resp_pts.status_code == 403

    def test_bloqueia_upload_documento_preliminar_apos_concluir(self):
        Nivel.objects.filter(pk=self.nivel.pk).update(pontuacao_minima=Decimal('3.00'))
        user = self.servidor_a.get_user()
        self.client.login(user=user)

        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            arquivo=SimpleUploadedFile('titulo.pdf', _pdf(), content_type='application/pdf'),
            nome_original='titulo.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            tipo=TipoDocumentoPreliminar.HOMOLOGACAO_ESTAGIO_PROBATORIO,
            arquivo=SimpleUploadedFile('homologacao.pdf', _pdf(), content_type='application/pdf'),
            nome_original='homologacao.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        self._concluir_assinado()
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_VALIDACAO

        count_before = DocumentoPreliminarRSCTae.objects.filter(processo=self.processo).count()
        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/documento_preliminar/upload/{TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO}/',
            data={
                'arquivo': SimpleUploadedFile('novo.pdf', _pdf(), content_type='application/pdf'),
                'data_obtencao_titulacao': '2020-01-10',
            },
        )
        assert DocumentoPreliminarRSCTae.objects.filter(processo=self.processo).count() == count_before

    def test_solicitar_correcao_coloca_em_aguardando_correcao_e_reabre_edicao(self):
        Nivel.objects.filter(pk=self.nivel.pk).update(pontuacao_minima=Decimal('3.00'))
        dono = self.servidor_a.get_user()
        self.client.login(user=dono)

        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            arquivo=SimpleUploadedFile('titulo.pdf', _pdf(), content_type='application/pdf'),
            nome_original='titulo.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        DocumentoPreliminarRSCTae.objects.create(
            processo=self.processo,
            tipo=TipoDocumentoPreliminar.HOMOLOGACAO_ESTAGIO_PROBATORIO,
            arquivo=SimpleUploadedFile('homologacao.pdf', _pdf(), content_type='application/pdf'),
            nome_original='homologacao.pdf',
            data_obtencao_titulacao='2020-01-10',
            cadastrado_por_vinculo=self.servidor_a.get_vinculo(),
        )
        self._concluir_assinado()
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_VALIDACAO

        gestor = self.servidor_b.get_user()
        # Solicitar correção (validação) agora exige membro ATIVO da CRSC, não mais a permissão.
        self._tornar_membro_crsc_ativo(gestor)
        self.client.login(user=gestor)

        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/solicitar_correcao/',
            data={
                'corrigir_diploma': 'on',
                'descricao_diploma': 'Faltou informação.',
                'confirmacao': 'on',
                'senha': '123',
            },
        )
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_CORRECAO

        self.client.login(user=dono)

        count_before = DocumentoPreliminarRSCTae.objects.filter(processo=self.processo).count()
        resp_doc = self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/documento_preliminar/upload/{TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO}/',
            data={
                'arquivo': SimpleUploadedFile('corrigido.pdf', _pdf(), content_type='application/pdf'),
                'data_obtencao_titulacao': '2020-01-10',
            },
        )
        assert resp_doc.status_code in (200, 302)
        assert DocumentoPreliminarRSCTae.objects.filter(processo=self.processo).count() == count_before + 1

        resp_anexo = self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/item/{self.item.id}/anexos/upload/',
            data={
                'arquivo': SimpleUploadedFile('x.pdf', _pdf(), content_type='application/pdf'),
                'pontuacao': '1.00',
            },
        )
        assert resp_anexo.status_code == 200
        assert resp_anexo.json().get('ok') is True

    def test_concluir_preenchimento_bloqueia_sem_documento_preliminar(self):
        Nivel.objects.filter(pk=self.nivel.pk).update(pontuacao_minima=Decimal('3.00'))
        user = self.servidor_a.get_user()
        self.client.login(user=user)
        self._concluir_assinado()
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_PREENCHIMENTO

    def test_definir_avaliador_atual_view_legada_redireciona_para_processo(self):
        """definir_avaliador_atual é view legada: sempre redireciona ao processo (avaliadores por sorteio automático)."""
        self.client.login(user=self.servidor_a.get_user())
        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/definir_avaliador/')
        assert resp.status_code == 302
        assert f'/rsc_tae/visualizar/{self.processo.id}/' in resp['Location']


@pytest.mark.django_db(databases='__all__')
class BancoPontosRSCTaeModelTestCase:
    """Testa a lógica de crédito, débito e rastreabilidade do banco de pontos."""

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.vinculo = self.servidor_a.get_vinculo()
        self.banco = BancoPontosRSCTae.get_or_create_for_vinculo(self.vinculo)

    def test_creditar_aumenta_saldo(self):
        self.banco.creditar(Decimal('3.00'))
        self.banco.refresh_from_db()
        assert self.banco.saldo == Decimal('3.00')

    def test_debitar_diminui_saldo(self):
        self.banco.creditar(Decimal('5.00'))
        self.banco.debitar(Decimal('2.00'))
        self.banco.refresh_from_db()
        assert self.banco.saldo == Decimal('3.00')

    def test_debitar_nao_fica_negativo(self):
        self.banco.creditar(Decimal('1.00'))
        self.banco.debitar(Decimal('10.00'))
        self.banco.refresh_from_db()
        assert self.banco.saldo == Decimal('0.00')

    def test_creditar_registra_movimento(self):
        self.banco.creditar(Decimal('2.50'))
        mov = MovimentoBancoPontosRSCTae.objects.filter(banco=self.banco).first()
        assert mov is not None
        assert mov.valor == Decimal('2.50')
        assert mov.saldo_apos == Decimal('2.50')
        assert mov.eh_credito is True
        assert mov.eh_debito is False

    def test_debitar_registra_movimento(self):
        self.banco.creditar(Decimal('5.00'))
        self.banco.debitar(Decimal('2.00'))
        movimentos = list(MovimentoBancoPontosRSCTae.objects.filter(banco=self.banco).order_by('id'))
        assert len(movimentos) == 2
        debito = movimentos[1]
        assert debito.valor == Decimal('2.00')
        assert debito.saldo_apos == Decimal('3.00')
        assert debito.eh_debito is True

    def test_multiplos_creditos_acumulam_saldo(self):
        self.banco.creditar(Decimal('1.00'))
        self.banco.creditar(Decimal('2.50'))
        self.banco.creditar(Decimal('0.75'))
        self.banco.refresh_from_db()
        assert self.banco.saldo == Decimal('4.25')

    def test_saldo_apos_reflete_historico(self):
        """saldo_apos de cada movimento deve permitir reconstituir o extrato."""
        self.banco.creditar(Decimal('3.00'))
        self.banco.debitar(Decimal('1.00'))
        self.banco.creditar(Decimal('2.00'))

        movimentos = list(MovimentoBancoPontosRSCTae.objects.filter(banco=self.banco).order_by('id'))
        assert movimentos[0].saldo_apos == Decimal('3.00')
        assert movimentos[1].saldo_apos == Decimal('2.00')
        assert movimentos[2].saldo_apos == Decimal('4.00')

    def test_tipo_devolucao_indeferimento(self):
        self.banco.creditar(
            Decimal('1.50'),
            tipo=MovimentoBancoPontosRSCTae.TIPO_DEVOLUCAO_INDEFERIMENTO,
            descricao='Devolução teste',
        )
        mov = MovimentoBancoPontosRSCTae.objects.filter(banco=self.banco).first()
        assert mov.tipo == MovimentoBancoPontosRSCTae.TIPO_DEVOLUCAO_INDEFERIMENTO
        assert mov.eh_credito is True


class RscTaeDeliberarCRSCViewTestCase(_RscTaeBase):
    """Testa a view de deliberação da CRSC: acesso, transições e banco de pontos."""

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c')

    def _setup_aguardando_crsc(self, pontuacao_minima=Decimal('0.00'), saldo_anterior=Decimal('0.00')):
        """Coloca o processo em AGUARDANDO_CRSC com anexos avaliados pelo avaliador B."""
        Nivel.objects.filter(pk=self.nivel.pk).update(
            pontuacao_minima=pontuacao_minima,
            numero_minimo_itens=0,
        )
        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(
            situacao=AGUARDANDO_CRSC,
            saldo_pontuacao_anterior=saldo_anterior,
        )
        # A deliberação final agora é por votação com quórum (default 4). Nos testes, 1 membro
        # ativo basta para fechar: reduz o quórum para 1 via configuração.
        config = ConfiguracaoRSCTae.objects.first()
        if config:
            ConfiguracaoRSCTae.objects.filter(pk=config.pk).update(quantidade_deliberacoes_item=1)
        else:
            ConfiguracaoRSCTae.objects.create(quantidade_deliberacoes_item=1)

    def _grant_deliberar(self, user):
        # Deliberar a CRSC exige ser membro ATIVO da comissão ATIVA (eh_membro_crsc_ativo),
        # não mais a permissão de grupo. Reusa o helper compartilhado da base.
        self._tornar_membro_crsc_ativo(user, presidente=True)

    def test_deliberar_crsc_requer_permissao(self):
        self._setup_aguardando_crsc()
        user = self.servidor_b.get_user()
        self.client.login(user=user)

        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/')
        assert resp.status_code == 403

    def test_deliberar_crsc_requer_estado_aguardando_crsc(self):
        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(situacao=EM_ANALISE)
        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/')
        assert resp.status_code == 403

    def test_deliberar_crsc_get_retorna_200(self):
        self._setup_aguardando_crsc()
        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/')
        assert resp.status_code == 200

    def test_deliberar_crsc_exibe_o_id_no_nome_do_anexo(self):
        """A tabela de divergências identifica o anexo por '#<id> - <nome>'.

        Prende a fiação da template: sem isso, remover ``nome_exibicao`` de
        deliberar_crsc.html não quebraria nenhum teste e a comissão voltaria a ver
        só o nome do arquivo, que se repete entre processos.
        """
        self._setup_aguardando_crsc()
        # Indeferir o anexo cria a divergência que o coloca na tabela da deliberação.
        AvaliacaoAnexoRSCTae.objects.create(
            anexo=self.anexo,
            avaliador_vinculo=self.servidor_c.get_vinculo(),
            situacao=AV_INDEFERIDO,
        )
        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/')

        assert resp.status_code == 200
        assert f'#{self.anexo.id} - teste.pdf' in resp.content.decode()

    def test_deliberar_crsc_exibe_data_de_exercicio_efetiva(self):
        """Sem data confirmada pela comissão, a deliberação mostra a data de exercício cadastrada do servidor.

        O campo ``processo.data_exercicio_cargo`` só é preenchido quando a comissão corrige a data
        na validação; exibi-lo cru deixaria a comissão sem a data que rege a análise.
        """
        self._setup_aguardando_crsc()
        type(self.servidor_a).objects.filter(pk=self.servidor_a.pk).update(data_inicio_exercicio_no_cargo=date(2017, 3, 15))
        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        resp = self.client.get(f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/')

        assert resp.status_code == 200
        assert '15/03/2017' in resp.content.decode()

    def test_deliberar_crsc_defere_processo(self):
        self._setup_aguardando_crsc()
        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        resp = self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/',
            data={
                'resultado': str(DEFERIDO),
                'justificativa': '',
                'confirmacao': 'on',
                'senha': '123',
            },
        )
        assert resp.status_code in (200, 302)

        processo = ProcessoRSCTae.objects.get(pk=self.processo.pk)
        assert processo.situacao == DEFERIDO

        deliberacao = DeliberacaoCRSCRSCTae.objects.filter(processo=processo).first()
        assert deliberacao is not None
        assert deliberacao.resultado == DEFERIDO

    def test_deliberar_crsc_indefere_exige_motivos(self):
        self._setup_aguardando_crsc()
        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        # Sem motivos marcados: processo não muda (constatações fundamentam o parecer)
        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/',
            data={
                'resultado': str(INDEFERIDO),
                'justificativa': 'Documentação insuficiente conforme Art. 13, IV.',
                'confirmacao': 'on',
                'senha': '123',
            },
        )
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == AGUARDANDO_CRSC

        # Com motivos: processo é indeferido e a deliberação consolida a união distinta
        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/',
            data={
                'resultado': str(INDEFERIDO),
                'motivos_indeferimento': [str(MotivoIndeferimento.PONTUACAO_MINIMA), str(MotivoIndeferimento.ESTAGIO_PROBATORIO)],
                'justificativa': 'Documentação insuficiente conforme Art. 13, IV.',
                'confirmacao': 'on',
                'senha': '123',
            },
        )
        processo = ProcessoRSCTae.objects.get(pk=self.processo.pk)
        assert processo.situacao == INDEFERIDO
        assert 'Art. 13, IV' in processo.avaliacao_motivo_indeferimento

        deliberacao = DeliberacaoCRSCRSCTae.objects.get(processo=processo)
        assert deliberacao.motivos_indeferimento == [MotivoIndeferimento.PONTUACAO_MINIMA, MotivoIndeferimento.ESTAGIO_PROBATORIO]
        # Assinatura da deliberação inclui os motivos (registros novos)
        assert '"motivos_indeferimento"' in (DeliberacaoCRSCRSCTae.objects.get(pk=deliberacao.pk).assinatura_conteudo or '')

    def test_deliberar_crsc_defere_credita_excedente_ao_banco(self):
        """Deferimento com pontuação acima do mínimo credita o excedente ao banco de pontos."""
        pontuacao_minima = Decimal('2.00')
        self._setup_aguardando_crsc(pontuacao_minima=pontuacao_minima)

        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        # CRSC atribui pontuação 3.50, mínimo é 2.00 → excedente = 1.50
        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/',
            data={
                'resultado': str(DEFERIDO),
                'pontuacao_final_crsc': '3,50',  # decimal pt-BR (campo do form é localizado)
                'justificativa': '',
                'confirmacao': 'on',
                'senha': '123',
            },
        )

        banco = BancoPontosRSCTae.objects.filter(vinculo=self.processo.vinculo).first()
        assert banco is not None
        assert banco.saldo == Decimal('1.50')

        mov = MovimentoBancoPontosRSCTae.objects.filter(banco=banco).first()
        assert mov.tipo == MovimentoBancoPontosRSCTae.TIPO_CREDITO_DEFERIMENTO

    def test_deliberar_crsc_indefere_devolve_saldo_anterior_ao_banco(self):
        """Indeferimento com saldo_pontuacao_anterior > 0 devolve o saldo ao banco."""
        saldo_utilizado = Decimal('1.20')
        self._setup_aguardando_crsc(saldo_anterior=saldo_utilizado)

        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        self.client.post(
            f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/',
            data={
                'resultado': str(INDEFERIDO),
                'motivos_indeferimento': [str(MotivoIndeferimento.PONTUACAO_MINIMA)],
                'justificativa': 'Não atendeu os requisitos mínimos.',
                'confirmacao': 'on',
                'senha': '123',
            },
        )

        banco = BancoPontosRSCTae.objects.filter(vinculo=self.processo.vinculo).first()
        assert banco is not None
        assert banco.saldo == saldo_utilizado

        mov = MovimentoBancoPontosRSCTae.objects.filter(banco=banco).first()
        assert mov.tipo == MovimentoBancoPontosRSCTae.TIPO_DEVOLUCAO_INDEFERIMENTO

    def test_deliberar_crsc_nao_permite_segunda_deliberacao(self):
        """Após deliberação registrada, uma segunda tentativa deve ser bloqueada (pode_deliberar_crsc=False)."""
        self._setup_aguardando_crsc()
        user = self.servidor_b.get_user()
        self._grant_deliberar(user)
        self.client.login(user=user)

        url = f'/rsc_tae/processo/{self.processo.id}/deliberar_crsc/'
        self.client.post(url, data={'resultado': str(DEFERIDO), 'confirmacao': 'on', 'senha': '123'})

        # Segunda tentativa: processo já saiu de AGUARDANDO_CRSC → 403
        resp = self.client.get(url)
        assert resp.status_code == 403
