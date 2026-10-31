from django.apps import apps
from django.db import transaction

from djtools.management.commands import BaseCommandPlus

# Cargas iniciais por classe. Para adicionar nova carga: criar lista de dicts e referenciar em CARGAS.

LICITACAO_TIPO = [{'nome': 'dispensa'}, {'nome': 'pregao'}]
MATERIAL_TIPO = [{'nome': 'consumo'}, {'nome': 'permanente'}]
ENTRADA_TIPO = [{'nome': 'compra'}, {'nome': 'doacao'}]
BAIXA_TIPO = [{'nome': 'cessao'}, {'nome': 'doacao'}, {'nome': 'inservivel'}]
INVENTARIO_STATUS = [{'nome': 'pendente'}, {'nome': 'ativo'}, {'nome': 'baixado'}, {'nome': 'estornado'}]
MOVIMENTO_PATRIMONIO_TIPO = [{'nome': 'pendencia'}, {'nome': 'transferencia'}, {'nome': 'baixa'}, {'nome': 'estorno'}]
MOVIMENTO_ALMOX_ENTRADA_TIPO = [{'nome': 'entrada'}, {'nome': 'requisicao_uo_material'}, {'nome': 'devolucao'}]
MOVIMENTO_ALMOX_SAIDA_TIPO = [{'nome': 'requisicao_uo_material'}, {'nome': 'requisicao_user_material'}]

CATEGORIA_MATERIAL_CONSUMO = [
    {'codigo': '01', 'nome': 'COMBUSTIVEIS E LUBRIFICANTES AUTOMOTIVOS'},
    {'codigo': '02', 'nome': 'COMBUSTIVEIS E LUBRIFICANTES DE AVIACAO'},
    {'codigo': '03', 'nome': 'COMBUSTIVEIS E LUBRIF. P/ OUTRAS FINALIDADES'},
    {'codigo': '04', 'nome': 'GAS E OUTROS MATERIAIS ENGARRAFADOS'},
    {'codigo': '05', 'nome': 'EXPLOSIVOS E MUNICOES'},
    {'codigo': '06', 'nome': 'ALIMENTOS PARA ANIMAIS'},
    {'codigo': '07', 'nome': 'GENEROS DE ALIMENTACAO'},
    {'codigo': '08', 'nome': 'ANIMAIS PARA PESQUISA E ABATE'},
    {'codigo': '09', 'nome': 'MATERIAL FARMACOLOGICO'},
    {'codigo': '10', 'nome': 'MATERIAL ODONTOLOGICO'},
    {'codigo': '11', 'nome': 'MATERIAL QUIMICO'},
    {'codigo': '12', 'nome': 'MATERIAL DE COUDELARIA OU DE USO ZOOTECNICO'},
    {'codigo': '13', 'nome': 'MATERIAL DE CACA E PESCA'},
    {'codigo': '14', 'nome': 'MATERIAL EDUCATIVO E ESPORTIVO'},
    {'codigo': '15', 'nome': 'MATERIAL P/ FESTIVIDADES E HOMENAGENS'},
    {'codigo': '16', 'nome': 'MATERIAL DE EXPEDIENTE'},
    {'codigo': '17', 'nome': 'MATERIAL DE PROCESSAMENTO DE DADOS'},
    {'codigo': '18', 'nome': 'MATERIAIS E MEDICAMENTOS P/ USO VETERINARIO'},
    {'codigo': '19', 'nome': 'MATERIAL DE ACONDICIONAMENTO E EMBALAGEM'},
    {'codigo': '20', 'nome': 'MATERIAL DE CAMA, MESA E BANHO'},
    {'codigo': '21', 'nome': 'MATERIAL DE COPA E COZINHA'},
    {'codigo': '22', 'nome': 'MATERIAL DE LIMPEZA E PROD. DE HIGIENIZACAO'},
    {'codigo': '23', 'nome': 'UNIFORMES, TECIDOS E AVIAMENTOS'},
    {'codigo': '24', 'nome': 'MATERIAL P/ MANUT.DE BENS IMOVEIS/INSTALACOES'},
    {'codigo': '25', 'nome': 'MATERIAL P/ MANUTENCAO DE BENS MOVEIS'},
    {'codigo': '26', 'nome': 'MATERIAL ELETRICO E ELETRONICO'},
    {'codigo': '27', 'nome': 'MATERIAL DE MANOBRA E PATRULHAMENTO'},
    {'codigo': '28', 'nome': 'MATERIAL DE PROTECAO E SEGURANCA'},
    {'codigo': '29', 'nome': 'MATERIAL P/ AUDIO, VIDEO E FOTO'},
    {'codigo': '30', 'nome': 'MATERIAL PARA COMUNICACOES'},
    {'codigo': '31', 'nome': 'SEMENTES, MUDAS DE PLANTAS E INSUMOS'},
    {'codigo': '32', 'nome': 'SUPRIMENTO DE AVIACAO'},
    {'codigo': '33', 'nome': 'MATERIAL P/ PRODUCAO INDUSTRIAL'},
    {'codigo': '34', 'nome': 'SOBRESSAL. MAQ.E MOTORES NAVIOS E EMBARCACOES'},
    {'codigo': '35', 'nome': 'MATERIAL LABORATORIAL'},
    {'codigo': '36', 'nome': 'MATERIAL HOSPITALAR'},
    {'codigo': '37', 'nome': 'SOBRESSALENTES DE ARMAMENTO'},
    {'codigo': '38', 'nome': 'SUPRIMENTO DE PROTECAO AO VOO'},
    {'codigo': '39', 'nome': 'MATERIAL P/ MANUTENCAO DE VEICULOS'},
    {'codigo': '40', 'nome': 'MATERIAL BIOLOGICO'},
    {'codigo': '41', 'nome': 'MATERIAL P/ UTILIZACAO EM GRAFICA'},
    {'codigo': '42', 'nome': 'FERRAMENTAS'},
    {'codigo': '43', 'nome': 'MATERIAL P/ REABILITACAO PROFISSIONAL'},
    {'codigo': '44', 'nome': 'MATERIAL DE SINALIZACAO VISUAL E OUTROS'},
    {'codigo': '45', 'nome': 'MATERIAL TECNICO P/ SELECAO E TREINAMENTO'},
    {'codigo': '46', 'nome': 'MATERIAL BIBLIOGRAFICO'},
    {'codigo': '47', 'nome': 'AQUISICAO DE SOFTWARES DE BASE'},
    {'codigo': '48', 'nome': 'BENS MOVEIS NAO ATIVAVEIS'},
    {'codigo': '49', 'nome': 'BILHETES DE PASSAGEM'},
    {'codigo': '50', 'nome': 'BANDEIRAS, FLAMULAS E INSIGNIAS'},
    {'codigo': '51', 'nome': 'DISCOTECAS E FILMOTECAS NAO IMOBILIZAVEL'},
    {'codigo': '52', 'nome': 'MATERIAL DE CARATER SECRETO OU RESERVADO'},
    {'codigo': '53', 'nome': 'MATERIAL METEOROLOGICO'},
    {'codigo': '54', 'nome': 'MATERIAL P/MANUT.CONSERV.DE ESTRADAS E VIAS'},
    {'codigo': '55', 'nome': 'SELOS PARA CONTROLE FISCAL'},
    {'codigo': '84', 'nome': 'INTEGRACAO DADOS ESTADOS E MUNICIPIOS - SAFEM'},
    {'codigo': '96', 'nome': 'MATERIAL DE CONSUMO - PAGTO ANTECIPADO'},
]

CARGAS = [
    ('almoxarifado', 'MovimentoAlmoxEntradaTipo', MOVIMENTO_ALMOX_ENTRADA_TIPO),
    ('almoxarifado', 'MovimentoAlmoxSaidaTipo', MOVIMENTO_ALMOX_SAIDA_TIPO),
    ('almoxarifado', 'CategoriaMaterialConsumo', CATEGORIA_MATERIAL_CONSUMO),
    ('almoxarifado', 'LicitacaoTipo', LICITACAO_TIPO),
    ('almoxarifado', 'MaterialTipo', MATERIAL_TIPO),
    ('almoxarifado', 'EntradaTipo', ENTRADA_TIPO),
    ('patrimonio', 'BaixaTipo', BAIXA_TIPO),
    ('patrimonio', 'InventarioStatus', INVENTARIO_STATUS),
    ('patrimonio', 'MovimentoPatrimTipo', MOVIMENTO_PATRIMONIO_TIPO),
]


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        total = 0
        for app_label, model_name, itens in CARGAS:
            cls = apps.get_model(app_label, model_name)
            self.stdout.write(f'Iniciando carga de {model_name}...')
            criados = 0
            for item in itens:
                _, created = cls.objects.get_or_create(**item)
                if created:
                    criados += 1
            self.stdout.write(f'Foram inseridos {criados} itens.')
            total += criados
        self.stdout.write('...')
        self.stdout.write(f'Fim da carga inicial, foram incluidos {total} itens.')
