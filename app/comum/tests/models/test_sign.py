from cryptography import x509 as c_x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import comum.x509_operations as x509_operations
from comum.x509_operations import CACertificate, CertificateRequest, Key


class TestX509:
    @classmethod
    def setup_class(cls):
        cls._rsa_key_size = x509_operations.RSA_KEY_SIZE
        x509_operations.RSA_KEY_SIZE = 1024

    @classmethod
    def teardown_class(cls):
        x509_operations.RSA_KEY_SIZE = cls._rsa_key_size

    def setup_method(self):
        self.issuer_name = 'fake-issuer'
        self.subject_name = 'fake-subject'
        self.ca_encryption_password = b'fake-ca-password'
        self.encryption_password = b'fake-password'

    def _load_pems(self, keypairs, encryption_password):
        private_key = serialization.load_pem_private_key(keypairs['private_key'], password=encryption_password, backend=default_backend())
        certificate = c_x509.load_pem_x509_certificate(keypairs['certificate'], default_backend())
        return certificate, private_key

    def _generate_ca_certificate(self, issuer_name=None):
        issuer_name = issuer_name or self.issuer_name
        ca_cert = CACertificate(issuer_name)
        ca_cert.generate_x509_root(self.ca_encryption_password)
        return ca_cert.cert_signed, ca_cert.key.private

    def _generate_client_certificate(self, issuer_name, subject_name):
        issuer_name = issuer_name or self.issuer_name
        subject_name = subject_name or self.issuer_name
        ca_cert = CACertificate(issuer_name)
        ca_cert.generate_x509_root(self.ca_encryption_password)
        ca_csr = CertificateRequest(subject_name, ca_cert)
        c_cert = ca_csr.generate_sign_client_certificate(self.encryption_password)
        return c_cert.cert_signed, c_cert.key.private

    def _generate_client_revoked_certificate(self, issuer_name, subject_name):
        issuer_name = issuer_name or self.issuer_name
        subject_name = subject_name or self.issuer_name
        ca_cert = CACertificate(issuer_name)
        ca_cert.generate_x509_root(self.ca_encryption_password)
        ca_csr = CertificateRequest(subject_name, ca_cert)
        c_cert = ca_csr.generate_sign_client_certificate(self.encryption_password)
        certificate = ca_cert.revoke(c_cert)
        return certificate.cert_signed, certificate.key.private

    def _public_bytes(self, public_key):
        return public_key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def _private_bytes(self, private_key):
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()
        )

    def _generate_private_key(self):
        return Key._generate_private_key()

    def _build_csr(self, private_key):
        csr = c_x509.CertificateSigningRequestBuilder()
        csr = csr.subject_name(c_x509.Name([c_x509.NameAttribute(NameOID.COMMON_NAME, self.subject_name)]))
        return csr.sign(private_key, hashes.SHA256(), default_backend())

    def assertHasPublicKey(self, keypairs):
        key = keypairs[1]
        cert = keypairs[0]
        assert self._public_bytes(key.public_key()) == self._public_bytes(cert.public_key())

    def assertHasSubjectName(self, cert, subject_name):
        actual_subject_name = cert.subject.get_attributes_for_oid(c_x509.NameOID.COMMON_NAME)
        actual_subject_name = actual_subject_name[0].value
        assert subject_name == actual_subject_name

    def assertHasIssuerName(self, cert, issuer_name):
        actual_issuer_name = cert.issuer.get_attributes_for_oid(c_x509.NameOID.COMMON_NAME)
        actual_issuer_name = actual_issuer_name[0].value
        assert issuer_name == actual_issuer_name

    def assertInClientExtensions(self, cert):
        key_usage = c_x509.KeyUsage(True, False, True, False, False, False, False, False, False)
        key_usage = c_x509.Extension(key_usage.oid, True, key_usage)
        extended_key_usage = c_x509.ExtendedKeyUsage([c_x509.OID_CLIENT_AUTH])
        extended_key_usage = c_x509.Extension(extended_key_usage.oid, False, extended_key_usage)
        basic_constraints = c_x509.BasicConstraints(ca=False, path_length=None)
        basic_constraints = c_x509.Extension(basic_constraints.oid, True, basic_constraints)
        assert key_usage in cert.extensions
        assert extended_key_usage in cert.extensions
        assert basic_constraints in cert.extensions

    def test_generate_ca_certificate_with_bytes_issuer_name(self):
        issuer_name = b'bytes-issuer-name'
        cert, _ = self._generate_ca_certificate(issuer_name)
        issuer_name = issuer_name.decode('utf-8')
        self.assertHasSubjectName(cert, issuer_name)
        self.assertHasIssuerName(cert, issuer_name)

    def test_generate_ca_certificate_has_publickey(self):
        keypairs = self._generate_ca_certificate(self.issuer_name)
        self.assertHasPublicKey(keypairs)

    def test_generate_ca_certificate_set_subject_name(self):
        cert, _ = self._generate_ca_certificate(self.issuer_name)
        self.assertHasSubjectName(cert, self.issuer_name)

    def test_generate_ca_certificate_set_issuer_name(self):
        cert, _ = self._generate_ca_certificate(self.issuer_name)
        self.assertHasIssuerName(cert, self.issuer_name)

    def test_generate_ca_certificate_set_extentions_as_ca(self):
        cert, _ = self._generate_ca_certificate(self.issuer_name)
        key_usage = c_x509.KeyUsage(False, False, False, False, False, True, False, False, False)
        key_usage = c_x509.Extension(key_usage.oid, True, key_usage)
        basic_constraints = c_x509.BasicConstraints(ca=True, path_length=0)
        basic_constraints = c_x509.Extension(basic_constraints.oid, True, basic_constraints)
        assert key_usage in cert.extensions
        assert basic_constraints in cert.extensions

    def test_generate_client_certificate_has_publickey(self):
        keypairs = self._generate_client_certificate(self.issuer_name, self.subject_name)
        self.assertHasPublicKey(keypairs)

    def test_generate_client_certificate_set_subject_name(self):
        cert, _ = self._generate_client_certificate(self.issuer_name, self.subject_name)
        self.assertHasSubjectName(cert, self.subject_name)

    def test_generate_client_certificate_set_issuer_name(self):
        cert, _key = self._generate_client_certificate(self.issuer_name, self.subject_name)
        self.assertHasIssuerName(cert, self.issuer_name)

    def test_generate_client_certificate_set_extentions_as_client(self):
        cert, _key = self._generate_client_certificate(self.issuer_name, self.subject_name)
        self.assertInClientExtensions(cert)

    def test_generate_client_revoked_certificate(self):
        certificate, private_key = self._generate_client_revoked_certificate(self.issuer_name, self.subject_name)
        self.assertHasPublicKey((certificate, private_key))

    def test_load_pem_private_key_with_bytes_private_key(self):
        private_key = self._generate_private_key()
        private_key = self._private_bytes(private_key)
        assert isinstance(private_key, bytes)
        private_key = Key._load_pem_private_key(private_key)
        assert isinstance(private_key, rsa.RSAPrivateKey)

    def test_load_pem_private_key_with_unicode_private_key(self):
        private_key = self._generate_private_key()
        private_key = self._private_bytes(private_key)
        private_key = str(private_key.decode('utf-8'))
        assert isinstance(private_key, str)
        private_key = Key._load_pem_private_key(private_key)
        assert isinstance(private_key, rsa.RSAPrivateKey)
