import base64

from django import template
from django.utils.safestring import mark_safe

from ldap_backend.utils import ad_to_datetime

register = template.Library()


@register.filter(name='get_ldap_attr')
def get_ldap_attr(dic, key):
    val = dic.get(key, [''])

    if isinstance(val, str):
        return val

    elif len(val) == 1:
        val = val[0]
        try:
            if not isinstance(val, str):
                val = val.decode('utf-8')
        except Exception:
            if key == 'thumbnailPhoto':
                val = base64.b64encode(val).decode('utf-8')
            else:
                val = '??????????'
        if key == 'thumbnailPhoto':
            return mark_safe(f'<img src="data:image/jpeg;base64,{val}"/>')
        if key in ['accountExpires', 'pwdLastSet', 'badPasswordTime', 'lastLogonTimestamp']:
            if not val or val in ['0', '9223372036854775807']:
                return 'Nunca'
            else:
                return ad_to_datetime(val)
        if key == 'userAccountControl':
            map_ = {
                '512': 'Enabled Account',
                '514': 'Disabled Account',
                '544': 'Enabled, Password Not Required',
                '546': 'Disabled, Password Not Required',
                '66048': "Enabled, Password Doesn't Expire",
                '66050': "Disabled, Password Doesn't Expire",
                '66080': "Enabled, Password Doesn't Expire & Not Required",
                '66082': "Disabled, Password Doesn't Expire & Not Required",
                '262656': 'Enabled, Smartcard Required',
                '262658': 'Disabled, Smartcard Required',
                '262688': 'Enabled, Smartcard Required, Password Not Required',
                '262690': 'Disabled, Smartcard Required, Password Not Required',
                '328192': "Enabled, Smartcard Required, Password Doesn't Expire",
                '328194': "Disabled, Smartcard Required, Password Doesn't Expire",
                '328224': "Enabled, Smartcard Required, Password Doesn't Expire & Not Required",
                '328226': "Disabled, Smartcard Required, Password Doesn't Expire & Not Required",
            }
            return '{} ({})'.format(val, map_.get(val, '?'))
        return val

    else:  # Múltiplos valores para o atributo
        out = ['<ul>']
        for v in val:
            out.append('<li>{}</li>'.format(v.decode('utf-8')))
        out.append('</ul>')
        return mark_safe(''.join(out))
