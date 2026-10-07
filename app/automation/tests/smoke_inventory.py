"""Exercise the real Runner/module against an HTTPS fixture inside the worker."""

from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import json
from pathlib import Path
import ssl
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.automation.ansible_inventory import run_inventory

REQUESTS = []
RESOURCES = {
    "/redfish/v1": {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
    "/redfish/v1/Systems": {"Members": [{"@odata.id": "/redfish/v1/Systems/fixture"}]},
    "/redfish/v1/Systems/fixture": {
        "Id": "fixture", "Model": "Test server", "Manufacturer": "Test manufacturer",
        "SerialNumber": "fixture-serial", "PowerState": "On",
    },
}


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        REQUESTS.append(("GET", self.path))
        payload = RESOURCES.get(self.path.rstrip("/"))
        self.send_response(200 if payload else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload or {}).encode())

    def do_POST(self):
        REQUESTS.append(("POST", self.path))
        self.send_error(405)


def main():
    with TemporaryDirectory() as directory:
        path = Path(directory)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        cert = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
            .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256())
        )
        (path / "key.pem").write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ))
        (path / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(path / "cert.pem", path / "key.pem")
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            facts = run_inventory(SimpleNamespace(
                host=f"127.0.0.1:{server.server_port}",
                username="fixture-user", password="fixture-password", verify_tls=False,
            ))
            assert len(facts) == 1 and facts[0].serial_number == "fixture-serial"
            assert REQUESTS and all(method == "GET" for method, _ in REQUESTS)
            print("PASS: real Ansible Runner, read-only HTTPS fixture, normalized system result.")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
