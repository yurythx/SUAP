"""Preenche ``comum.Pais.iso_alfa3`` vazio pelo ISO 3166-1 alfa-3 de cada país da tabela do SIAPE (``comum.Pais.codigo``).
Os códigos do SIAPE são iguais em todas as instituições.

O documento é o passaporte, então vale o alfa-3 do Estado que emite o passaporte. Território ou subdivisão vai para o Estado
emissor, tenha ou não alfa-3 próprio na ISO (INGLATERRA → GBR, DUBAI → ARE, TAITI e POLINESIA FRANCESA → FRA, HONG KONG → CHN).
A exceção é a entidade que emite passaporte próprio com código próprio, que mantém o seu (FORMOSA → TWN, PALESTINA → PSE).
País extinto, caso ambíguo ou código que não é lugar fica de fora: sem alfa-3, o passaporte não forma documento (spec da
deduplicação, 6.1). A única extinta incluída é ANTILHAS HOLANDESAS (173) → NLD, o Estado que emitia o passaporte.
Vários códigos SIAPE caem no mesmo alfa-3 (a Suíça é 150 e 236).

Nunca sobrescreve um alfa-3 preenchido: a correção manual no admin vale. A migration comum/0123 chama este command (não o
renomeie) e o importador do SIAPE usa ``ISO_ALFA3_POR_CODIGO_SIAPE``; corrigir um valor já aplicado em bancos migrados exige
uma data migration nova.
"""

from comum.models import Pais
from djtools.management.commands import BaseCommandPlus

ISO_ALFA3_POR_CODIGO_SIAPE: dict[str, str] = {
    '001': 'AFG',  # REPUBL. DEMOCR. DO AFEGANISTAO
    '002': 'ZAF',  # REPUBL. DA AFRICA DO SUL
    '003': 'ALB',  # REPUBL. POPULAR DA ALBANIA
    '004': 'DEU',  # ALEMANHA
    '006': 'AND',  # ANDORRA
    '007': 'AGO',  # ANGOLA
    '008': 'ATG',  # ANTIGUA
    '009': 'SAU',  # ARABIA SAUDITA
    '010': 'DZA',  # ARGELIA
    '011': 'ARG',  # ARGENTINA
    '012': 'AUS',  # AUSTRALIA
    '013': 'AUT',  # AUSTRIA
    '014': 'BHS',  # BAHAMAS
    '015': 'BGD',  # BANGLADESH
    '016': 'BRB',  # BARBADOS
    '017': 'BHR',  # BAREIN
    '018': 'BEL',  # BELGICA
    '019': 'BLZ',  # BELIZE
    '020': 'BEN',  # BENIN
    '021': 'MMR',  # BIRMANIA
    '022': 'BOL',  # BOLIVIA
    '023': 'BWA',  # BOTSUANA
    '024': 'BRA',  # BRASIL
    '025': 'BRN',  # BRUNEI
    '026': 'BGR',  # BULGARIA
    '027': 'BFA',  # BURKINA
    '028': 'BDI',  # BURUNDI
    '029': 'BTN',  # BUTAO
    '030': 'CPV',  # CABO VERDE
    '031': 'CMR',  # CAMAROES
    '032': 'KHM',  # CAMBOJA
    '033': 'CAN',  # CANADA
    '034': 'QAT',  # CATAR
    '035': 'TCD',  # CHADE
    '036': 'CHL',  # CHILE
    '037': 'CHN',  # CHINA
    '038': 'CYP',  # CHIPRE
    '039': 'SGP',  # CINGAPURA
    '040': 'COL',  # COLOMBIA
    '041': 'COG',  # CONGO
    '042': 'PRK',  # COREIA DO NORTE
    '043': 'KOR',  # COREIA DO SUL
    '044': 'CIV',  # COSTA DO MARFIM
    '045': 'CRI',  # COSTA RICA
    '046': 'CUB',  # CUBA
    '047': 'DNK',  # DINAMARCA
    '048': 'DJI',  # DJIBUTI
    '049': 'DMA',  # DOMINICA
    '050': 'EGY',  # EGITO
    '051': 'SLV',  # EL SALVADOR
    '052': 'ARE',  # EMIRADOS ARABES UNIDOS
    '053': 'ECU',  # EQUADOR
    '054': 'ESP',  # ESPANHA
    '055': 'USA',  # ESTADOS UNIDOS
    '056': 'ETH',  # ETIOPIA
    '057': 'FJI',  # FIJI
    '058': 'PHL',  # FILIPINAS
    '059': 'FIN',  # FINLANDIA
    '060': 'TWN',  # FORMOSA
    '061': 'FRA',  # FRANCA
    '062': 'GAB',  # GABAO
    '063': 'GMB',  # GAMBIA
    '064': 'GHA',  # GANA
    '065': 'GBR',  # GRA-BRETANHA
    '066': 'GRD',  # GRANADA
    '067': 'GRC',  # GRECIA
    '068': 'GTM',  # GUATEMALA
    '069': 'GUY',  # GUIANA
    '070': 'GIN',  # GUINE
    '071': 'GNB',  # GUINE-BISSAU
    '072': 'GNQ',  # GUINE EQUATORIAL
    '073': 'HTI',  # HAITI
    '074': 'NLD',  # HOLANDA
    '075': 'HND',  # HONDURAS
    '076': 'HUN',  # HUNGRIA
    '077': 'YEM',  # IEMEM
    '079': 'COM',  # ILHAS COMORES
    '080': 'SLB',  # ILHAS SALOMAO
    '081': 'IND',  # INDIA
    '082': 'IDN',  # INDONESIA
    '083': 'IRN',  # IRA
    '084': 'IRQ',  # IRAQUE
    '085': 'IRL',  # IRLANDIA
    '086': 'ISL',  # ISLANDIA
    '087': 'ISR',  # ISRAEL
    '088': 'ITA',  # ITALIA
    '090': 'JAM',  # JAMAICA
    '091': 'JPN',  # JAPAO
    '092': 'JOR',  # JORDANIA
    '093': 'KIR',  # KIRIBATI
    '094': 'KWT',  # KUWEIT
    '095': 'LAO',  # LAOS
    '096': 'LSO',  # LESOTO
    '097': 'LBN',  # LIBANO
    '098': 'LBR',  # LIBERIA
    '099': 'LBY',  # LIBIA
    '100': 'LIE',  # LIECHTENSTEIN
    '101': 'LUX',  # LUXEMBURGO
    '102': 'MDG',  # MADAGASCAR
    '103': 'MYS',  # MALASIA
    '104': 'MWI',  # MALAVI
    '105': 'MDV',  # MALDIVAS
    '106': 'MLI',  # MALI
    '107': 'MLT',  # MALTA
    '108': 'MAR',  # MARROCOS
    '109': 'MUS',  # MAURICIO
    '110': 'MRT',  # MAURITANIA
    '111': 'MEX',  # MEXICO
    '112': 'MOZ',  # MOCAMBIQUE
    '113': 'MCO',  # MONACO
    '114': 'MNG',  # MONGOLIA
    '115': 'NRU',  # NAURU
    '116': 'NPL',  # NEPAL
    '117': 'NIC',  # NICARAGUA
    '118': 'NER',  # NIGER
    '119': 'NGA',  # NIGERIA
    '120': 'NOR',  # NORUEGA
    '121': 'NZL',  # NOVA ZELANDIA
    '122': 'OMN',  # OMA
    '123': 'PAN',  # PANAMA
    '124': 'PNG',  # PAPUA NOVA GUINE
    '125': 'PAK',  # PAQUISTAO
    '126': 'PRY',  # PARAGUAI
    '127': 'PER',  # PERU
    '128': 'POL',  # POLONIA
    '129': 'PRT',  # PORTUGAL
    '130': 'KEN',  # QUENIA
    '131': 'CAF',  # REPUBLICA CENTRO AFRICANA
    '132': 'DOM',  # REPUBLICA DOMINICANA
    '133': 'ROU',  # ROMENIA
    '134': 'RWA',  # RUANDA
    '135': 'WSM',  # SAMOA OCIDENTAL
    '136': 'SMR',  # SAN MARINO
    '137': 'LCA',  # SANTA LUCIA
    '138': 'KNA',  # SAO CRISTOVAO E NEVES
    '139': 'STP',  # SAO TOME E PRINCIPE
    '140': 'VCT',  # SAO VICENTE E GRANABINAS
    '141': 'SEN',  # SENEGAL
    '142': 'SLE',  # SERRA LEOA
    '143': 'SYC',  # SEYCHELLES
    '144': 'SYR',  # SIRIA
    '145': 'SOM',  # SOMALIA
    '146': 'LKA',  # SRI LANKA
    '147': 'SWZ',  # SUAZILANDIA
    '148': 'SDN',  # SUDAO
    '149': 'SWE',  # SUECIA
    '150': 'CHE',  # SUICA
    '151': 'SUR',  # SURINAME
    '152': 'THA',  # TAILANDIA
    '153': 'TZA',  # TANZANIA
    '155': 'TGO',  # TOGO
    '156': 'TON',  # TONGA
    '157': 'TTO',  # TRINIDAD E TOBAGO
    '158': 'TUN',  # TUNISIA
    '159': 'TUR',  # TURQUIA
    '160': 'TUV',  # TUVALU
    '161': 'UGA',  # UGANDA
    '163': 'URY',  # URUGUAI
    '164': 'VUT',  # VANUATU
    '165': 'VAT',  # VATICANO
    '166': 'VEN',  # VENEZUELA
    '167': 'VNM',  # VIETINA
    '168': 'COD',  # ZAIRE
    '169': 'ZMB',  # ZAMBIA
    '170': 'ZWE',  # ZIMBABUE
    '171': 'GBR',  # ANGUILLA
    '173': 'NLD',  # ANTILHAS HOLANDESAS
    '174': 'NLD',  # ARUBA
    '175': 'GBR',  # BERMUDAS
    '176': 'ESP',  # CEUTA E MELILLA
    '177': 'GBR',  # GIBRALTAR
    '178': 'DNK',  # GROELANDIA
    '179': 'FRA',  # GUADALUPE
    '180': 'USA',  # GUAN
    '181': 'FRA',  # GUIANA FRANCESA
    '182': 'CHN',  # HONG KONG
    '183': 'USA',  # ILHA JOHNSTOM
    '184': 'AUS',  # ILHA NORFOLK
    '185': 'GBR',  # ILHA DE MAN
    '186': 'GBR',  # ILHA DE PITCAIRN
    '187': 'USA',  # ILHA WAKE
    '188': 'GBR',  # ILHAS DO CANAL
    '189': 'GBR',  # ILHAS CAYMAN
    '190': 'AUS',  # ILHAS CHRISTMAS
    '191': 'AUS',  # ILHAS COCOS (KEELING)
    '192': 'NZL',  # ILHAS COOR
    '193': 'DNK',  # ILHAS FABOE
    '194': 'GBR',  # ILHAS MALVINAS
    '195': 'USA',  # ILHAS MARIANAS DO NORTE
    '196': 'USA',  # ILHAS MIDWAY
    '197': 'GBR',  # ILHAS TURKS E CAICOS
    '198': 'USA',  # ILHAS VIRGENS AMERICANAS
    '199': 'GBR',  # ILHAS VIRGENS BRITANICAS
    '200': 'FRA',  # ILHAS WALLIS E FUTUNA
    '201': 'IDN',  # IRIA OCIDENTAL
    '202': 'CHN',  # MACAU
    '203': 'FRA',  # MARTINICA
    '204': 'FRA',  # MAYOTTE
    '205': 'GBR',  # MONTSERRAT
    '206': 'NAM',  # NAMIBIA
    '207': 'NZL',  # NIUE
    '208': 'FRA',  # NOVA CALEDONIA
    '209': 'FRA',  # POLINESIA FRANCESA
    '210': 'USA',  # PORTO RICO
    '211': 'FRA',  # REUNIAO
    '212': 'ESH',  # SAARA OCIDENTAL
    '213': 'FRA',  # SAINT-PIERRE E MIQUELOH
    '214': 'USA',  # SAMOA AMERICANA
    '215': 'GBR',  # SANTA HELENA
    '216': 'NOR',  # SVALBARD
    '217': 'GBR',  # T. BRIT. DO OCEANO INDICO
    '219': 'TLS',  # TIMOR
    '220': 'NZL',  # TOQUELAU
    '221': 'UKR',  # UCRANIA
    '222': 'IRL',  # IRLANDA
    '223': 'GBR',  # ESCOCIA
    '224': 'DZA',  # ALGERIA
    '225': 'ERI',  # ERITEIA
    '226': 'KGZ',  # QUIRGUISTAO
    '227': 'SRB',  # SERVIA
    '228': 'MNE',  # MONTENEGRO
    '229': 'BLR',  # BELARUS
    '230': 'SVK',  # ESLOVAQUIA
    '231': 'EST',  # ESTONIA
    '232': 'MHL',  # ILHAS MARSHAL
    '233': 'LTU',  # LITUANIA
    '234': 'MKD',  # MACEDONIA
    '235': 'MDA',  # MOLDOVA
    '236': 'CHE',  # SUICA
    '239': 'ARM',  # ARMENIA
    '242': 'HRV',  # CROACIA
    '243': 'AZE',  # AZERBAIJAO
    '244': 'SVN',  # ESLOVENIA
    '245': 'LVA',  # LETONIA
    '246': 'FRA',  # TAITI
    '249': 'GEO',  # GEORGIA
    '250': 'TKM',  # TURCOMENISTAO
    '251': 'PLW',  # PALAU
    '254': 'GBR',  # REINO UNIDO
    '255': 'ATG',  # BARBUDA
    '256': 'RUS',  # RUSSIA
    '257': 'KIR',  # QUIRIBATI
    '258': 'TJK',  # TADJIQUISTAO
    '260': 'BIH',  # BOSNIA-HERZEGOVINA
    '261': 'FSM',  # MICRONESIA
    '264': 'KAZ',  # CAZAQUISTAO
    '267': 'CZE',  # REPUBLICA TCHECA
    '268': 'UZB',  # UZBEQUISTAO
    '269': 'ZAF',  # AFRICA DO SUL
    '270': 'GBR',  # LONDRES
    '271': 'GBR',  # INGLATERRA
    '272': 'ARE',  # ABU DHABI
    '274': 'ESP',  # ALBORAN-PEREJIL
    '275': 'ATG',  # ANTIGUA E BARBUDA
    '279': 'ESP',  # CANARIAS, ILHAS
    '280': 'GBR',  # CANAL, ILHAS
    '281': 'ARE',  # DUBAI
    '282': 'LBY',  # FEZZAN
    '284': 'IND',  # JAMMU
    '285': 'MYS',  # LABUAN, ILHAS
    '286': 'PRT',  # ILHA DA MADEIRA
    '287': 'USA',  # PACIFICO, ILHAS DO (ADM. EUA)
    '288': 'USA',  # PACIFICO, ILHAS DO (POS. EUA)
    '290': 'PSE',  # PALESTINA
    '291': 'KNA',  # SAINT KITT E NEVIS
    '294': 'TLS',  # TIMOR LESTE
}


class Command(BaseCommandPlus):
    help = 'Preenche o ISO 3166-1 alfa-3 vazio dos países pela tabela do SIAPE.'

    def handle(self, *args, **options) -> None:
        # só as colunas usadas: a migration 0123 chama o command, e o model atual pode ter campos que o banco ainda não tem
        alterados = []
        for pais in Pais.objects.only('codigo', 'iso_alfa3').filter(iso_alfa3=''):
            pais.iso_alfa3 = ISO_ALFA3_POR_CODIGO_SIAPE.get(pais.codigo, '')
            if pais.iso_alfa3:
                alterados.append(pais)
        Pais.objects.bulk_update(alterados, ['iso_alfa3'])
        self.stdout.write(f'Países com ISO 3166-1 alfa-3 preenchido: {len(alterados)}')
