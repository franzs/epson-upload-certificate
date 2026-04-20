#!/usr/bin/env python3

import argparse
import io
import os
import sys
import requests
import html5lib
import urllib.parse


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
        help='Path to the certificate file'
    )
    parser.add_argument(
        '--key',
        required=True,
        help='Path to the private key file'
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

    if not os.path.isfile(args.cert):
        print(f'Error: Certificate file not found: {args.cert}', file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.key):
        print(f'Error: Key file not found: {args.key}', file=sys.stderr)
        sys.exit(1)

    ########################################################################
    # step 1, authenticate
    jar = requests.cookies.RequestsCookieJar()
    set_url = urllib.parse.urljoin(args.url, 'PRESENTATION/ADVANCED/PASSWORD/SET')
    r = requests.post(
        set_url,
        cookies=jar,
        data={
            'INPUTT_USERNAME': username,
            'access': 'https',
            'INPUTT_PASSWORD': password,
            'INPUTT_ACCSESSMETHOD': 0,
            'INPUTT_DUMMY': '',
        },
    )

    if r.status_code != 200:
        print(f'Error: Authentication failed with status code {r.status_code}', file=sys.stderr)
        sys.exit(1)

    jar = r.cookies

    ########################################################################
    # step 2, get the cert update form iframe and its token
    form_url = urllib.parse.urljoin(args.url, 'PRESENTATION/ADVANCED/NWS_CERT_SSLTLS/CA_IMPORT')
    r = requests.get(form_url, cookies=jar)
    tree = html5lib.parse(r.text, namespaceHTMLElements=False)
    data = {}
    for f in tree.findall('.//input'):
        if 'name' in f.attrib and 'value' in f.attrib:
            data[f.attrib['name']] = f.attrib['value']

    if 'INPUTT_SETUPTOKEN' not in data:
        print('Error: Setup token not found in form', file=sys.stderr)
        sys.exit(1)

    ########################################################################
    # step 3, upload key and certs
    data['format'] = 'pem_der'
    del data['cert0']
    del data['cert1']
    del data['cert2']
    del data['key']

    upload_url = urllib.parse.urljoin(args.url, 'PRESENTATIONEX/CERT/IMPORT_CHAIN')

    ########################################################################
    # Epson doesn't seem to like bundled certificates,
    # so split it into its components
    with open(args.cert, 'r') as f:
        full = f.readlines()

    certno = 0
    certs = dict()

    for line in full:
        if not line.strip():
            continue
        certs[certno] = certs.get(certno, '') + line
        if 'END CERTIFICATE' in line:
            certno = certno + 1

    if certno >= 3:
        print(f'Error: Too many certificates found ({certno + 1}), maximum is 3', file=sys.stderr)
        sys.exit(1)

    with open(args.key, 'rb') as key_file:
        key_content = key_file.read()

    files = {
        'key': io.BytesIO(key_content),
    }

    for certno in certs:
        files[f'cert{certno}'] = io.BytesIO(certs[certno].encode('utf-8'))

    ########################################################################
    # step 4, submit the new cert
    r = requests.post(upload_url, cookies=jar, files=files, data=data)

    ########################################################################
    # step 5, verify the printer accepted the cert and is shutting down
    if 'Shutting down' not in r.text:
        print('Error: Unexpected response from printer:', file=sys.stderr)
        print(r.text, file=sys.stderr)
        sys.exit(1)

    print('Epson certificate successfully uploaded to printer.')


if __name__ == '__main__':
    main()
