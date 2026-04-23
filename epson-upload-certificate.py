#!/usr/bin/env python3

import argparse
import io
import os
import sys
import requests
import html5lib

from urllib.parse import urljoin


URL_PATH_AUTHENTICATE = 'PRESENTATION/ADVANCED/PASSWORD/SET'
URL_PATH_CA_IMPORT = 'PRESENTATION/ADVANCED/NWS_CERT_SSLTLS/CA_IMPORT'
URL_PATH_UPLOAD_CERT = 'PRESENTATIONEX/CERT/IMPORT_CHAIN'


class EpsonError(Exception):
    """Raised when printer returns unexpected response."""

    pass


def authenticate(s, url, timeout, username, password):
    set_url = urljoin(url, URL_PATH_AUTHENTICATE)

    r = s.post(
        set_url,
        data={
            'INPUTT_USERNAME': username,
            'access': 'https',
            'INPUTT_PASSWORD': password,
            'INPUTT_ACCSESSMETHOD': 0,
            'INPUTT_DUMMY': '',
        },
        timeout=timeout,
    )
    r.raise_for_status()


def get_data_from_form(s, url, timeout, url_path):
    form_url = urljoin(url, url_path)

    r = s.get(form_url, timeout=timeout)
    r.raise_for_status()

    tree = html5lib.parse(r.text, namespaceHTMLElements=False)
    data = {}
    for f in tree.findall('.//input'):
        if 'name' in f.attrib and 'value' in f.attrib:
            data[f.attrib['name']] = f.attrib['value']

    if 'INPUTT_SETUPTOKEN' not in data:
        raise EpsonError(f'Setup token not found in form at {form_url}')

    return data


def upload_cert(s, url, timeout, data, cert, key):
    data['format'] = 'pem_der'
    data.pop('cert0', None)
    data.pop('cert1', None)
    data.pop('cert2', None)
    data.pop('key', None)

    ########################################################################
    # Epson doesn't seem to like bundled certificates,
    # so split it into its components
    with open(cert, 'r') as f:
        full = f.readlines()

    certno = 0
    certs = {}
    current_cert = []

    for line in full:
        if line.strip():
            current_cert.append(line)
            if 'END CERTIFICATE' in line:
                certs[certno] = ''.join(current_cert)
                current_cert = []
                certno += 1

    if certno == 0:
        raise ValueError('No certificates found in file')

    if certno > 3:
        raise ValueError(f'Too many certificates found ({certno}), maximum is 3')

    with open(key, 'rb') as key_file:
        key_content = key_file.read()

    files = {
        'key': io.BytesIO(key_content),
    }

    for certno in certs:
        files[f'cert{certno}'] = io.BytesIO(certs[certno].encode('utf-8'))

    upload_url = urljoin(url, URL_PATH_UPLOAD_CERT)

    r = s.post(upload_url, files=files, data=data, timeout=timeout)
    r.raise_for_status()

    if 'Shutting down' not in r.text:
        raise EpsonError(f'Missing "Shutting down" in response at {upload_url}')


def validate_file(path):
    """Validate that file exists and is readable."""
    if not os.path.isfile(path):
        raise argparse.ArgumentTypeError(f'File not found: {path}')

    if not os.access(path, os.R_OK):
        raise argparse.ArgumentTypeError(f'File not readable: {path}')

    return path


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Upload SSL/TLS certificate to Epson printer'
    )

    parser.add_argument(
        '--url',
        required=True,
        help='Base URL of the Epson printer (e.g., https://myepson.example.com/)'
    )
    parser.add_argument(
        '--cert',
        required=True,
        type=validate_file,
        help='Path to the certificate file'
    )
    parser.add_argument(
        '--key',
        required=True,
        type=validate_file,
        help='Path to the private key file'
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=30,
        help='Request timeout in seconds (default: 30)'
    )

    args = parser.parse_args()

    # Get credentials from environment variables
    username = os.environ.get('EPSON_CERT_UPLOAD_USERNAME')
    password = os.environ.get('EPSON_CERT_UPLOAD_PASSWORD')

    if not username:
        print('Error: EPSON_CERT_UPLOAD_USERNAME environment variable not set', file=sys.stderr)
        sys.exit(1)

    if not password:
        print('Error: EPSON_CERT_UPLOAD_PASSWORD environment variable not set', file=sys.stderr)
        sys.exit(1)

    s = requests.Session()

    ########################################################################
    # step 1, authenticate
    try:
        authenticate(s, args.url, args.timeout, username, password)
    except requests.RequestException as e:
        print(f'Authentication attempt failed: {e}', file=sys.stderr)
        sys.exit(1)

    ########################################################################
    # step 2, get the cert update form iframe and its token
    try:
        data = get_data_from_form(s, args.url, args.timeout, URL_PATH_CA_IMPORT)
    except (requests.RequestException, EpsonError) as e:
        print(f'Getting data from form failed: {e}', file=sys.stderr)
        sys.exit(1)

    ########################################################################
    # step 3, upload key and certs
    try:
        upload_cert(s, args.url, args.timeout, data, args.cert, args.key)
    except (EpsonError, requests.RequestException, ValueError) as e:
        print(f'Uploading certificate failed: {e}', file=sys.stderr)
        sys.exit(1)

    print('Epson certificate successfully uploaded to printer.')


if __name__ == '__main__':
    main()
