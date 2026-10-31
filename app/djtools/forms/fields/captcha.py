import logging
import sys

from django import forms
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.translation import gettext_lazy as _
from django_recaptcha import client
from django_recaptcha.constants import TEST_PRIVATE_KEY, TEST_PUBLIC_KEY
from django_recaptcha.widgets import ReCaptchaBase, ReCaptchaV2Checkbox

from djtools.utils import running_tests

logger = logging.getLogger(__name__)


class ReCaptchaField(forms.CharField):
    widget = ReCaptchaV2Checkbox
    default_error_messages = {
        'captcha_invalid': _('Erro ao validar o reCAPTCHA, por favor, tente novamente.'),
        'captcha_error': _('Error ao verificar o reCAPTCHA, por favor, recarregue a página e tente novamente.'),
    }

    def __init__(self, public_key=None, private_key=None, *args, **kwargs):
        """
        ReCaptchaField can accepts attributes which is a dictionary of
        attributes to be passed to the ReCaptcha widget class. The widget will
        loop over any options added and create the RecaptchaOptions
        JavaScript variables as specified in
        https://developers.google.com/recaptcha/docs/display#render_param
        """
        private_key = private_key or settings.RECAPTCHA_PRIVATE_KEY or TEST_PRIVATE_KEY
        public_key = public_key or settings.RECAPTCHA_PUBLIC_KEY or TEST_PUBLIC_KEY

        super().__init__(*args, **kwargs)

        if not isinstance(self.widget, ReCaptchaBase):
            raise ImproperlyConfigured('djtools.forms.fields.captcha.ReCaptchaField.widget must be a subclass of captcha.widgets.ReCaptchaBase')

        # Setup instance variables.
        self.private_key = private_key
        self.public_key = public_key

        # Update widget attrs with data-sitekey.
        self.widget.attrs['data-sitekey'] = self.public_key

    def get_remote_ip(self):
        f = sys._getframe()
        while f:
            request = f.f_locals.get('request')
            if request:
                remote_ip = request.META.get('REMOTE_ADDR', '')
                forwarded_ip = request.META.get('HTTP_X_FORWARDED_FOR', '')
                ip = forwarded_ip or remote_ip
                return ip
            f = f.f_back

    def validate(self, value):
        if running_tests() or settings.DEBUG:
            return True
        super().validate(value)
        if self.required:
            try:
                check_captcha = client.submit(recaptcha_response=value, private_key=self.private_key, remoteip=self.get_remote_ip())

            except Exception as e:  # Catch timeouts, etc
                raise ValidationError(self.error_messages['captcha_error'] + f' Detalhes: {e}', code='captcha_error')

            if not check_captcha.is_valid:
                raise ValidationError(self.error_messages['captcha_invalid'], code='captcha_invalid')
