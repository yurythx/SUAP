from comum.models import Configuracao
from djtools import relatorios
from djtools.utils import data_extenso


def get_rodape_termos(nome=''):
    sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')

    elementos = [relatorios.space(8)]
    elementos.append(
        relatorios.para(
            'Declaro pelo presente documento de responsabilidade que recebi o material '
            'acima especificado e que sou responsável direto pelo mesmo e devo observar '
            'normas sobre o controle e zelo do material permanente, equipamentos e instalações '
            f'pertencentes ao {sigla}.',
            align='center',
            escape=False,
        )
    )
    elementos.append(relatorios.space(8))
    elementos.append(relatorios.para('_______________________, ______ de ______________________ de __________', align='center', escape=False))
    elementos.append(relatorios.space(8))
    elementos.append(
        relatorios.table(
            [
                [
                    relatorios.para('________________________________________<br/>Coordenador de Patrimônio', align='center', escape=False),
                    relatorios.para(f'________________________________________<br/>{nome}', align='center', escape=False),
                ]
            ],
            w=[95, 95],
            grid=0,
        )
    )
    return elementos


def get_corpo_nada_consta(vinculo):
    elementos = [relatorios.space(30)]
    elementos.append(
        relatorios.para(
            f'Declaramos, para devidos fins, que <strong>{vinculo}</strong>, com matrícula <strong>{vinculo.relacionamento.matricula}</strong>, '
            'não possui nenhum bem patrimonial em sua carga/responsabilidade.',
            align='justify',
            escape=False,
        )
    )
    elementos.append(relatorios.space(30))
    elementos.append(relatorios.para(f'{data_extenso()}', align='center'))
    elementos.append(relatorios.space(20))
    elementos.append(relatorios.para('______________________________________________', align='center', escape=False))
    elementos.append(relatorios.para(' Coordenador de Patrimônio', align='center', escape=False))
    return elementos


def get_corpo_nada_consta_inventario_uso_pessoal(usuario_logado, vinculo='', uso_pessoal=None):
    if uso_pessoal is None:
        uso_pessoal = []
    elementos = [relatorios.space(30)]

    elementos.append(
        relatorios.para(
            f'Declaramos, para devidos fins, que <strong>{vinculo.pessoa.nome}</strong>, com matrícula <strong>{vinculo.relacionamento.matricula}</strong>, '
            'não possui nenhum bem patrimonial em sua carga/responsabilidade, exceto os seguintes inventários de uso pessoal:',
            align='justify',
            escape=False,
        )
    )
    elementos.append(relatorios.space(10))

    # tabela com elementos de uso pessoal
    dados = [['#', 'Número', 'Descrição', 'Valor']]
    for index, item in enumerate(uso_pessoal):
        dados.append([index + 1, item['numero'], item['descricao'], item['entrada_permanente__valor']])

    widths = [10, 15, 142, 20]
    tabela_dados = relatorios.table(dados, head=1, zebra=1, w=widths, count=0, a=['r', 'c', 'c', 'r'])
    elementos.append(tabela_dados)

    elementos.append(relatorios.space(30))
    elementos.append(relatorios.para(f'{data_extenso()}', align='center'))
    elementos.append(relatorios.space(20))
    elementos.append(relatorios.para('________________________________________________', align='center'))
    elementos.append(relatorios.para(' Coordenador de Patrimônio', align='center'))
    return elementos
