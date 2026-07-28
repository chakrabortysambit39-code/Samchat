"""
gen_cert.py
Cross-platform alternative to gen_cert.sh — generates a local self-signed
TLS certificate using Python's `cryptography` package, so it works the
same on Windows/PowerShell as on macOS/Linux (no openssl CLI needed).

    pip install cryptography
    python gen_cert.py

Creates certs/cert.pem and certs/key.pem, valid 365 days for
localhost/127.0.0.1. Browsers will show a "not secure" warning for a
self-signed cert — that's expected for local dev; click through it.
For a real domain with no warning, use Caddy/Let's Encrypt instead
(see README).
"""
import datetime
import ipaddress
import os

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:
    raise SystemExit(
        "Missing dependency. Run:\n    pip install cryptography\nthen re-run this script."
    )

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    key_path = os.path.join(OUT_DIR, "key.pem")
    cert_path = os.path.join(OUT_DIR, "cert.pem")

    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Created {cert_path} and {key_path} (valid 365 days).")


if __name__ == "__main__":
    main()
