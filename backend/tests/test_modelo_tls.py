"""
HTTPS entre el backend y el servidor del modelo propio (certificate pinning).

Un servidor HTTPS de verdad en 127.0.0.1 hace de llama.cpp, con un certificado
autofirmado como el de deploy/model_server/make_cert.sh:
- con LOCAL_MODEL_CERT = ese certificado, la conexion funciona;
- con OTRO certificado (o sin pinning, confiando en las CA del sistema) se rechaza.
No necesita base de datos.
"""
import base64
import datetime
import http.server
import ipaddress
import json
import ssl
import threading

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.core.config import settings
from app.services import trained_model


def _self_signed(tmp_path, name):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "modelo-propio")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_path, cert_path = tmp_path / f"{name}.key", tmp_path / f"{name}.pem"
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert_pem)
    return cert_pem, key_path, cert_path


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def https_model(tmp_path, monkeypatch):
    cert_pem, key_path, cert_path = _self_signed(tmp_path, "servidor")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "LOCAL_MODEL_URL", f"https://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(settings, "LOCAL_MODEL_API_KEY", "clave")
    yield cert_pem
    srv.shutdown()
    srv.server_close()


def test_con_el_certificado_fijado_conecta(https_model, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_MODEL_CERT", base64.b64encode(https_model).decode())
    assert isinstance(trained_model._verify(), ssl.SSLContext)
    assert trained_model.health() == "ok"


def test_otro_certificado_se_rechaza(https_model, monkeypatch, tmp_path):
    otro, _, _ = _self_signed(tmp_path, "impostor")
    monkeypatch.setattr(settings, "LOCAL_MODEL_CERT", base64.b64encode(otro).decode())
    with pytest.raises(httpx.ConnectError):
        trained_model.health()


def test_sin_pinning_un_autofirmado_se_rechaza(https_model, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_MODEL_CERT", "")
    assert trained_model._verify() is True
    with pytest.raises(httpx.ConnectError):
        trained_model.health()
