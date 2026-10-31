from oauth2_provider.models import AccessToken

from comum.models import User
from djtools import forms


class AccessTokenForm(forms.ModelFormPlus):
    user = forms.ModelChoiceFieldPlus(queryset=User.objects)

    class Meta:
        model = AccessToken
        exclude = ()
