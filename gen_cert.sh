#!/usr/bin/env bash
# Generates a self-signed TLS certificate for local HTTPS testing.
# Browsers will show a "not secure" warning for self-signed certs — click
# through it (or import the cert into your OS/browser trust store) for
# local dev. For a real deployment with no browser warning, use a real
# domain + Let's Encrypt instead (see README).
set -e
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
echo "Created certs/cert.pem and certs/key.pem (valid 365 days)."
