import datetime

import pytest
from django.contrib.auth.models import Group

from ae.models import OfertaAlimentacao, Programa, TipoPrograma
from comum.models import Ano
from edu.models import Aluno, NivelEnsino, SituacaoMatricula
from rh.models import PessoaFisica
from edu.tests.factories import SituacaoMatriculaFactory
from rh.tests.factories import ServidorFactory

SENHA = '123'


class TestProgramasEstudantis:
    @pytest.fixture(autouse=True)
    def _setup(self, client, db, sync_permissions):
        self.client = client
        # O setor do servidor é o campus dos programas: `SetorFactory` já lhe dá uma `uo`.
        servidor = ServidorFactory()
        self.campus = servidor.setor
        self.user = servidor.get_user()
        self.user.set_password(SENHA)
        self.user.groups.add(Group.objects.get(name='Assistente Social'))
        self.user.groups.add(Group.objects.get(name='Administrador Acadêmico'))
        self.user.save()
        self.client.logout()
        self.client.login(username=self.user.username, password=SENHA)

        self.tipo_alimentacao, _ = TipoPrograma.objects.get_or_create(
            titulo='Programa de Alimentação',
            descricao='Programa de Alimentação',
            sigla=Programa.TIPO_ALIMENTACAO,
        )
        self.tipo_transporte, _ = TipoPrograma.objects.get_or_create(
            titulo='Programa de  Auxílio Transporte',
            descricao='Programa de  Auxílio Transporte',
            sigla=Programa.TIPO_TRANSPORTE,
        )
        self.tipo_trabalho, _ = TipoPrograma.objects.get_or_create(
            titulo='Programa de Iniciação ao Trabalho',
            descricao='Programa de Iniciação ao Trabalho',
            sigla=Programa.TIPO_TRABALHO,
        )
        self.tipo_idioma, _ = TipoPrograma.objects.get_or_create(
            titulo='Programa de Cursos de Idiomas',
            descricao='Programa de Cursos de Idiomas',
            sigla=Programa.TIPO_IDIOMA,
        )

        Programa.objects.get_or_create(
            tipo_programa=self.tipo_alimentacao,
            descricao=' Programa de Alimentação (Campus X)',
            instituicao=self.campus.uo,
        )
        Programa.objects.get_or_create(
            tipo_programa=self.tipo_transporte,
            descricao=' Programa de  Auxílio Transporte (Campus X)',
            instituicao=self.campus.uo,
        )
        Programa.objects.get_or_create(
            tipo_programa=self.tipo_trabalho,
            descricao=' Programa de Iniciação ao Trabalho (Campus X)',
            instituicao=self.campus.uo,
        )
        Programa.objects.get_or_create(
            tipo_programa=self.tipo_idioma,
            descricao=' Programa de Cursos de Idiomas (Campus X)',
            instituicao=self.campus.uo,
        )

        NivelEnsino.objects.get_or_create(descricao='Superior')

    def test_cadastro_oferta_alimentacao_mantem_registro_existente(self):
        oferta = OfertaAlimentacao.objects.create(campus=self.campus.uo)
        url = f'/admin/ae/ofertaalimentacao/{oferta.pk}/'

        resposta_get = self.client.get(url)
        assert resposta_get.status_code == 302

        quantidade_antes = OfertaAlimentacao.objects.count()
        payload = {
            'campus': self.campus.uo.pk,
            'valor_refeicao': '5',
            'cafe_seg': '0',
            'cafe_ter': '0',
            'cafe_qua': '0',
            'cafe_qui': '0',
            'cafe_sex': '0',
            'almoco_seg': '10',
            'almoco_ter': '10',
            'almoco_qua': '10',
            'almoco_qui': '10',
            'almoco_sex': '10',
            'janta_seg': '0',
            'janta_ter': '0',
            'janta_qua': '0',
            'janta_qui': '0',
            'janta_sex': '0',
        }
        resposta_post = self.client.post(url, payload)

        assert resposta_post.status_code == 302
        assert OfertaAlimentacao.objects.count() == quantidade_antes

    def test_cadastro_aluno_cria_novo_registro(self):
        pessoa_fisica, _ = PessoaFisica.objects.get_or_create(
            nome='Carlos Breno Pereira Silva',
            defaults={'cpf': '359.221.769-00'},
        )
        ano_letivo, _ = Ano.objects.get_or_create(ano='2013')
        situacao = SituacaoMatriculaFactory()

        quantidade_antes = Aluno.objects.count()

        Aluno.objects.create(
            matricula='201310140400001',
            pessoa_fisica=pessoa_fisica,
            ano_letivo=ano_letivo,
            periodo_letivo=1,
            situacao=situacao,
            ano_let_prev_conclusao=datetime.datetime.now().year,
        )

        assert Aluno.objects.count() == quantidade_antes + 1
