from djtools.utils import to_ascii

DELIMITADOR = '¥'
FIM_LINHA = '£'


def is_empty(data):
    return len(data.strip()) == 0


def get_chefe(chefes):
    chefe = None
    if chefes.exists():
        if chefes.count() == 1:
            chefe = chefes.first()
        else:
            chefe = chefes.first()
    return chefe and chefe.servidor or chefe


def trim(data, size):
    if len(data) > size:
        return data[:size]
    return data


def clear_masks(data):
    value = data.replace('-', '').replace('.', '').replace(' ', '')
    value = value.replace('(', '').replace(')', '').replace(',', '')
    return value


def get_ddd(data):
    if len(data) >= 10:
        if data[0] == '0':
            return data[1:3]
        return data[0:2]
    return ''


def get_telefone(data):
    size = len(data)
    if size < 10:
        return data
    elif data[0] == '0':
        return data[3:]
    elif size >= 8:
        return data[2:]
    return ''


def add_delimitador(data):
    return to_ascii(DELIMITADOR.join(data).upper())
