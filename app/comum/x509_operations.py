# Adaptado de https://github.com/openstack/magnum


import datetime
import enum
import logging
import uuid

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509 import ReasonFlags

log = logging.getLogger(__name__)


class Extensions(enum.Enum):
    __order__ = (
        'AUTHORITY_KEY_IDENTIFIER SUBJECT_KEY_IDENTIFIER '
        'AUTHORITY_INFORMATION_ACCESS BASIC_CONSTRAINTS '
        'CRL_DISTRIBUTION_POINTS CERTIFICATE_POLICIES '
        'EXTENDED_KEY_USAGE OCSP_NO_CHECK INHIBIT_ANY_POLICY '
        'KEY_USAGE NAME_CONSTRAINTS SUBJECT_ALTERNATIVE_NAME '
        'ISSUER_ALTERNATIVE_NAME'
    )

    AUTHORITY_KEY_IDENTIFIER = 'authorityKeyIdentifier'
    SUBJECT_KEY_IDENTIFIER = 'subjectKeyIdentifier'
    AUTHORITY_INFORMATION_ACCESS = 'authorityInfoAccess'
    BASIC_CONSTRAINTS = 'basicConstraints'
    CRL_DISTRIBUTION_POINTS = 'cRLDistributionPoints'
    CERTIFICATE_POLICIES = 'certificatePolicies'
    EXTENDED_KEY_USAGE = 'extendedKeyUsage'
    OCSP_NO_CHECK = 'OCSPNoCheck'
    INHIBIT_ANY_POLICY = 'inhibitAnyPolicy'
    KEY_USAGE = 'keyUsage'
    NAME_CONSTRAINTS = 'nameConstraints'
    SUBJECT_ALTERNATIVE_NAME = 'subjectAltName'
    ISSUER_ALTERNATIVE_NAME = 'issuerAltName'


class KeyUsages(enum.Enum):
    __order__ = (
        'DIGITAL_SIGNATURE CONTENT_COMMITMENT KEY_ENCIPHERMENT DATA_ENCIPHERMENT KEY_AGREEMENT KEY_CERT_SIGN CRL_SIGN ENCIPHER_ONLY DECIPHER_ONLY'
    )

    DIGITAL_SIGNATURE = ('Digital Signature', 'digital_signature')
    CONTENT_COMMITMENT = ('Non Repudiation', 'content_commitment')
    KEY_ENCIPHERMENT = ('Key Encipherment', 'key_encipherment')
    DATA_ENCIPHERMENT = ('Data Encipherment', 'data_encipherment')
    KEY_AGREEMENT = ('Key Agreement', 'key_agreement')
    KEY_CERT_SIGN = ('Certificate Sign', 'key_cert_sign')
    CRL_SIGN = ('CRL Sign', 'crl_sign')
    ENCIPHER_ONLY = ('Encipher Only', 'encipher_only')
    DECIPHER_ONLY = ('Decipher Only', 'decipher_only')


# ALLOWED_EXTENSIONS_AVAILABL = ['"%s"' % e.value for e in Extensions]
# 'List of allowed x509 extensions. Available values: %s' % ', '.join(ALLOWED_EXTENSIONS_AVAILABL)
DEFAULT_ALLOWED_EXTENSIONS = [
    Extensions.KEY_USAGE.value,
    Extensions.EXTENDED_KEY_USAGE.value,
    Extensions.SUBJECT_ALTERNATIVE_NAME.value,
    Extensions.BASIC_CONSTRAINTS.value,
    Extensions.SUBJECT_KEY_IDENTIFIER.value,
]

# ALLOWED_KEY_USAGE_AVAILABLE = ['"%s"' % e.value[0] for e in KeyUsages]
# 'List of allowed x509 key usage. Available values: %s' % ', '.join(ALLOWED_KEY_USAGE_AVAILABLE)
DEFAULT_ALLOWED_KEY_USAGE = [KeyUsages.DIGITAL_SIGNATURE.value[0], KeyUsages.KEY_ENCIPHERMENT.value[0], KeyUsages.CONTENT_COMMITMENT.value[0]]

ALLOWED_KEY_USAGE = DEFAULT_ALLOWED_KEY_USAGE
ALLOWED_EXTENSIONS = DEFAULT_ALLOWED_EXTENSIONS
RSA_KEY_SIZE = 2048
TERM_OF_VALIDITY = 365 * 5
ALOW_CA = True


class Validator:
    _CA_KEY_USAGES = [KeyUsages.KEY_CERT_SIGN.value[0], KeyUsages.CRL_SIGN.value[0]]

    @classmethod
    def filter_extensions(cls, extensions):
        filtered_extensions = []
        allowed_key_usage = set(ALLOWED_KEY_USAGE)
        if not ALOW_CA:
            allowed_key_usage = cls._remove_ca_key_usage(allowed_key_usage)

        for ext in cls.filter_allowed_extensions(extensions, ALLOWED_EXTENSIONS):
            if ext.oid == x509.OID_KEY_USAGE:
                ext = cls._merge_key_usage(ext, allowed_key_usage)
            elif ext.oid == x509.OID_BASIC_CONSTRAINTS:
                if not ALOW_CA:
                    ext = cls._disallow_ca_in_basic_constraints(ext)

            filtered_extensions.append(ext)

        return filtered_extensions

    @staticmethod
    def filter_allowed_extensions(extensions, allowed_extensions=None):
        """Ensure only accepted extensions are used."""
        allowed_extensions = allowed_extensions or []

        for ext in extensions:
            ext_name = x509.oid._OID_NAMES.get(ext.oid, None)
            if ext_name in allowed_extensions:
                yield ext
            else:
                if ext.critical:
                    raise Exception(f'CertificateValidationError: extension {ext} not allowed')

    @staticmethod
    def _merge_key_usage(key_usage, allowed_key_usage):
        critical = key_usage.critical
        key_usage_value = key_usage.value

        usages = []
        for usage in KeyUsages:
            k, v = usage.value
            try:
                value = getattr(key_usage_value, v)
            except ValueError:
                # ValueError is raised when encipher_only/decipher_only is
                # retrieved but key_agreement is False
                value = False
            if value:
                if k not in allowed_key_usage:
                    if critical:
                        raise Exception(f'CertificateValidationError: extension {key_usage} not allowed')
                    else:
                        value = False
            usages.append(value)

        rtn = x509.KeyUsage(*usages)
        return x509.Extension(rtn.oid, critical, rtn)

    @classmethod
    def _remove_ca_key_usage(cls, allowed_key_usage):
        for usage in cls._CA_KEY_USAGES:
            try:
                allowed_key_usage.remove(usage)
            except KeyError:
                pass
        return allowed_key_usage

    @staticmethod
    def _disallow_ca_in_basic_constraints(basic_constraints):
        if basic_constraints.value.ca:
            if basic_constraints.critical:
                raise Exception(f'CertificateValidationError: extension {basic_constraints} not allowed')

            bc = x509.BasicConstraints(False, None)
            return x509.Extension(bc.oid, False, bc)

        return basic_constraints


class Key:
    def __init__(self, pwd=None, key_pem=None):
        if isinstance(pwd, str):
            pwd = pwd.encode('latin-1')
        if pwd is not None:
            encryption_algorithm = serialization.BestAvailableEncryption(pwd)
        else:
            encryption_algorithm = serialization.NoEncryption()
        if key_pem is None:
            self._private_key = Key._generate_private_key()
            self._private_key_pem = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=encryption_algorithm
            )
        else:
            self._private_key_pem = key_pem
            self._private_key = Key._load_pem_private_key(key_pem, pwd)

    @property
    def private_pem(self):
        return self._private_key_pem

    @property
    def private(self):
        return self._private_key

    @property
    def public(self):
        return self._private_key.public_key()

    @staticmethod
    def _generate_private_key():
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_SIZE, backend=default_backend())
        return private_key

    @classmethod
    def generate(cls, pwd):
        return cls(pwd)

    @classmethod
    def new_from_pem(cls, key_pem, pwd):
        return cls(key_pem, pwd)

    @classmethod
    def _load_pem_private_key(cls, key, pwd=None):
        if not isinstance(key, rsa.RSAPrivateKey):
            if isinstance(key, str):
                key = key.encode('latin-1')
            if isinstance(pwd, str):
                pwd = pwd.encode('latin-1')

            key = serialization.load_pem_private_key(key, password=pwd, backend=default_backend())
        return key

    @classmethod
    def new_from_pem_file(cls, filename, pwd=None):
        with open(filename, 'rb') as key_file:
            key_pem = key_file.read()
        return cls(key_pem, pwd)

    def save_pem(self, filename):
        with open(filename, 'wb') as f:
            f.write(self._private_key_pem)

            # @staticmethod
            # def decrypt_key(encrypted_key, password):
            #     private_key = _load_pem_private_key(encrypted_key, password)
            #
            #     decrypted_pem = private_key.private_bytes(
            #         encoding=serialization.Encoding.PEM,
            #         format=serialization.PrivateFormat.PKCS8,
            #         encryption_algorithm=serialization.NoEncryption()
            #     )
            #     return decrypted_pem


class BaseCertificate:
    def __init__(
        self,
        common_name,
        key=None,
        extensions=None,
        country_name=None,
        state_or_province_name=None,
        locality_name=None,
        organization_name=None,
        organizational_unit_name=None,
    ):
        self.cert_pem = None
        self._common_name = common_name
        self._country_name = country_name
        self._state_or_province_name = state_or_province_name
        self._locality_name = locality_name
        self._organization_name = organization_name
        self._organizational_unit_name = organizational_unit_name
        self._serial_number = 1
        if not isinstance(common_name, str):
            self._common_name = self.__unicode(common_name)
        self._extensions = extensions
        if key is not None and not isinstance(key, Key):
            raise ValueError('key is not instance of Key')
        self._key = key

    def __unicode(self, text):
        if text is None:
            return text
        if not isinstance(text, str):
            return str(text.decode('utf-8'))

    @property
    def common_name(self):
        return self._common_name

    @common_name.setter
    def common_name(self, value):
        self._common_name = self.__unicode(value)

    @property
    def country_name(self):
        return self._country_name

    @country_name.setter
    def country_name(self, value):
        self._country_name = self.__unicode(value)

    @property
    def state_or_province_name(self):
        return self.state

    @state_or_province_name.setter
    def state_or_province_name(self, value):
        self._state_or_province_name = self.__unicode(value)

    @property
    def locality_name(self):
        return self._locality_name

    @locality_name.setter
    def locality_name(self, value):
        self._locality_name = self.__unicode(value)

    @property
    def organization_name(self):
        return self._organization_name

    @organization_name.setter
    def organization_name(self, value):
        self._organization_name = self.__unicode(value)

    @property
    def organizational_unit_name(self):
        return self._organizational_unit_name

    @organizational_unit_name.setter
    def organizational_unit_name(self, value):
        self._organizational_unit_name = self.__unicode(value)

    @property
    def serial_number(self):
        return self._serial_number

    @serial_number.setter
    def serial_number(self, value):
        self._serial_number = value

    @property
    def extensions(self):
        return self._extensions

    @extensions.setter
    def extensions(self, value):
        self._extensions = value

    @property
    def key(self):
        return self._key

    @key.setter
    def key(self, value):
        if value is not None and not isinstance(value, Key):
            return ValueError('key is not instance of Key')
        self._key = value

    @property
    def pem(self):
        return self.cert_pem

    @pem.setter
    def pem(self, value):
        self.cert_pem = value

    @property
    def cert_signed(self):
        return x509.load_pem_x509_certificate(self.pem, default_backend())

    def _get_subject_names(self):
        x509_name = [x509.NameAttribute(x509.OID_COMMON_NAME, self._common_name)]
        if self._country_name:
            x509_name.append(x509.NameAttribute(x509.OID_COUNTRY_NAME, self._country_name))
        if self._state_or_province_name:
            x509_name.append(x509.NameAttribute(x509.OID_STATE_OR_PROVINCE_NAME, self._state_or_province_name))
        if self._locality_name:
            x509_name.append(x509.NameAttribute(x509.OID_LOCALITY_NAME, self._locality_name))
        if self._locality_name:
            x509_name.append(x509.NameAttribute(x509.OID_ORGANIZATION_NAME, self._locality_name))
        if self._locality_name:
            x509_name.append(x509.NameAttribute(x509.OID_ORGANIZATIONAL_UNIT_NAME, self._locality_name))
        return x509.Name(x509_name)

    def _generate_key(self, pwd):
        if self._key is None:
            self._key = Key.generate(pwd)
        return self._key

    def _sign(self, csr, issuer_name, ca_private_key, skip_validation=False, term_of_validity=TERM_OF_VALIDITY, serial_number=None):
        """Sign a given csr
        validade:
            from: today - one day
            to: today + TERM_OF_VALIDITY day
        """
        # ca_private_key = ca_key.private_key # _load_pem_private_key(key.private_pem, key.pwd)
        if not serial_number:
            serial_number = int(uuid.uuid4())
        self._serial_number = serial_number
        if isinstance(csr, str):
            csr = csr.encode('latin-1')
        if not isinstance(csr, x509.CertificateSigningRequest):
            try:
                csr = x509.load_pem_x509_csr(csr, backend=default_backend())
            except ValueError:
                raise Exception(f'Received invalid csr {csr}.')

        one_day = datetime.timedelta(1, 0, 0)
        expire_after = datetime.timedelta(term_of_validity, 0, 0)

        builder = x509.CertificateBuilder()
        builder = builder.subject_name(csr.subject)
        # issuer_name is set as common name
        builder = builder.issuer_name(issuer_name)
        builder = builder.not_valid_before(datetime.datetime.today() - one_day)
        builder = builder.not_valid_after(datetime.datetime.today() + expire_after)
        builder = builder.serial_number(serial_number)
        builder = builder.public_key(csr.public_key())

        if skip_validation:
            extensions = csr.extensions
        else:
            extensions = Validator.filter_extensions(csr.extensions)

        for extention in extensions:
            builder = builder.add_extension(extention.value, critical=extention.critical)

        certificate = builder.sign(private_key=ca_private_key, algorithm=hashes.SHA256(), backend=default_backend()).public_bytes(
            serialization.Encoding.PEM
        )

        return certificate

    def _generate_certificate(self, issuer_name, private_key, ca_private_key):
        # subject name is set as common name
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(self._get_subject_names())
        # builder = builder.subject_name(x509.Name([
        #     x509.NameAttribute(x509.OID_COMMON_NAME, self._common_name),
        #     x509.NameAttribute(x509.OID_COUNTRY_NAME, self._country_name),
        #     x509.NameAttribute(x509.OID_STATE_OR_PROVINCE_NAME, self._state_or_province_name),
        #     x509.NameAttribute(x509.OID_LOCALITY_NAME, self._locality_name),
        #     x509.NameAttribute(x509.OID_ORGANIZATION_NAME, self._organization_name),
        #     x509.NameAttribute(x509.OID_ORGANIZATIONAL_UNIT_NAME, self._organizational_unit_name),
        #     # x509.NameAttribute(NameOID.COMMON_NAME, u"Autoridade Certificadora Raiz Brasileira v1"),
        #     # x509.NameAttribute(NameOID.COUNTRY_NAME, u"BR"),
        #     # x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"RN"),
        #     # x509.NameAttribute(NameOID.LOCALITY_NAME, u"Natal"),
        #     # x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"ICP-Brasil"),
        #     # x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, u"Instituto Nacional de Tecnologia da Informacao - ITI"),
        # ]))

        for extention in self._extensions:
            builder = builder.add_extension(extention.value, critical=extention.critical)

        csr = builder.sign(private_key, hashes.SHA256(), default_backend())
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)

        self.cert_pem = self._sign(csr, issuer_name, ca_private_key, skip_validation=True)
        return csr_pem, self.cert_pem

    def save_pem(self, filename):
        with open(filename, 'wb') as f:
            f.write(self.pem)


class Certificate(BaseCertificate):
    def __init__(self, common_name, key=None, extension=None):
        self._revoked = False
        if extension is None:
            extension = self._build_ca_extentions()
        # issuer_name = common_name
        super().__init__(common_name, key, extension)

    @property
    def revoked(self):
        return self._revoked

    @revoked.setter
    def revoked(self, value):
        self._revoked = value


class CACertificate(BaseCertificate):
    def __init__(self, common_name, key=None, extension=None):
        if extension is None:
            extension = self._build_ca_extentions()
        super().__init__(common_name, key, extension)

    def _build_ca_extentions(self):
        # Certificate Sign is enabled
        key_usage = x509.KeyUsage(False, False, False, False, False, True, False, False, False)
        key_usage = x509.Extension(key_usage.oid, True, key_usage)
        basic_constraints = x509.BasicConstraints(ca=True, path_length=0)
        basic_constraints = x509.Extension(basic_constraints.oid, True, basic_constraints)
        return [basic_constraints, key_usage]

    @property
    def _csr(self):
        return self._csr

    @property
    def crl(self):
        # Certificate Revocation List
        return self.crl_pem

    def generate_x509_root(self, pwd):
        """
        Generate x509 self signed cert
        """
        key = self._generate_key(pwd)
        _csr_pem, certificate_pem = self._generate_certificate(self._get_subject_names(), key.private, key.private)
        self.cert_pem = certificate_pem
        self._generate_crl_builder()
        return certificate_pem

    def _generate_crl_builder(self):
        one_day = datetime.timedelta(1, 0, 0)
        # subject name is set as common name
        builder = x509.CertificateRevocationListBuilder()
        builder = builder.issuer_name(self._get_subject_names())

        builder = builder.last_update(datetime.datetime.today() - one_day)
        builder = builder.next_update(datetime.datetime.today() + one_day)
        self._crl_builder = builder

    def revoke(self, certificate):
        """
        CRL (Certificate Revocation List) - Certificados nesta lista podem ter sido roubados, perdidos ou, simplesmente, estar sem utilidade.
        """
        if not isinstance(certificate, Certificate):
            raise ValueError('certificate is not instance of Certificate')
        certificate.revoked = True
        revoked_cert_build = x509.RevokedCertificateBuilder()
        revoked_cert_build = revoked_cert_build.serial_number(certificate.serial_number)
        revoked_cert_build = revoked_cert_build.revocation_date(datetime.datetime.today())

        invalidity_date = x509.InvalidityDate(datetime.datetime.today())
        crl_reason = x509.CRLReason(ReasonFlags.certificate_hold)
        revoked_cert_build = revoked_cert_build.add_extension(invalidity_date, False)
        revoked_cert_build = revoked_cert_build.add_extension(crl_reason, False)

        revoked_certificate = revoked_cert_build.build(default_backend())
        self._crl_builder = self._crl_builder.add_revoked_certificate(revoked_certificate)

        log.info('Revoked Certificate')
        for ext in revoked_certificate.extensions:
            log.info(ext)

        crl_pem = self._crl_builder.sign(private_key=self.key.private, algorithm=hashes.SHA256(), backend=default_backend()).public_bytes(
            serialization.Encoding.PEM
        )
        self.crl_pem = crl_pem
        return certificate


class CertificateRequest(BaseCertificate):
    def __init__(self, common_name, ca, key=None, extension=None):
        if not isinstance(ca, CACertificate):
            raise ValueError('ca is not instance of CACertificate')
        else:
            if ca.pem is None:
                raise ValueError('ca is not valid certificate. Use the method generate_x509_root to generate the certificate.')
        self.ca = ca
        if extension is None:
            extension = self._build_client_extentions()
        super().__init__(common_name, key, extension)

    def _build_client_extentions(self):
        # Digital Signature and Key Encipherment are enabled
        key_usage = x509.KeyUsage(True, False, True, False, False, False, False, False, False)
        key_usage = x509.Extension(key_usage.oid, True, key_usage)
        extended_key_usage = x509.ExtendedKeyUsage([x509.OID_CLIENT_AUTH])
        extended_key_usage = x509.Extension(extended_key_usage.oid, False, extended_key_usage)
        basic_constraints = x509.BasicConstraints(ca=False, path_length=None)
        basic_constraints = x509.Extension(basic_constraints.oid, True, basic_constraints)

        return [key_usage, extended_key_usage, basic_constraints]

    @property
    def _csr(self):
        return self._csr

    def generate_sign_client_certificate(self, pwd):
        key = self._generate_key(pwd)

        csr_pem, cert_pem = self._generate_certificate(self.ca._get_subject_names(), key.private, self.ca.key.private)
        self.cert_pem = csr_pem

        cert = Certificate(self._common_name, key, self._extensions)
        cert.pem = cert_pem
        return cert
