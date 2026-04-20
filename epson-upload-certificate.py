#!/usr/bin/env python3

import argparse
import io
import os
import sys
import requests
import html5lib


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

# Ensure URL ends with /
url = args.url if args.url.endswith('/') else args.url + '/'

########################################################################
# step 1, authenticate
jar = requests.cookies.RequestsCookieJar()
set_url = url + 'PRESENTATION/ADVANCED/PASSWORD/SET'
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
assert r.status_code == 200
jar = r.cookies

########################################################################
# step 2, get the cert update form iframe and its token
form_url = url + 'PRESENTATION/ADVANCED/NWS_CERT_SSLTLS/CA_IMPORT'
r = requests.get(form_url, cookies=jar)
tree = html5lib.parse(r.text, namespaceHTMLElements=False)
data = dict([(f.attrib['name'], f.attrib['value']) for f in tree.findall('.//input')])
assert 'INPUTT_SETUPTOKEN' in data

# step 3, upload key and certs
data['format'] = 'pem_der'
del data['cert0']
del data['cert1']
del data['cert2']
del data['key']

upload_url = url + 'PRESENTATIONEX/CERT/IMPORT_CHAIN'

########################################################################
# Epson doesn't seem to like bundled certificates,
# so split it into its componens
f = open(args.cert, 'r')
full = f.readlines()
f.close()
certno = 0
certs = dict()

for line in full:
    if not line.strip():
        continue
    certs[certno] = certs.get(certno, '') + line
    if 'END CERTIFICATE' in line:
        certno = certno + 1

files = {
    'key': open(args.key, 'rb'),
}

for certno in certs:
    assert certno < 3
    files[f'cert{certno}'] = io.BytesIO(certs[certno].encode('utf-8'))

########################################################################
# step 3, submit the new cert
r = requests.post(upload_url, cookies=jar, files=files, data=data)

########################################################################
# step 4, verify the printer accepted the cert and is shutting down
if not 'Shutting down' in r.text:
    print(r.text)
assert 'Shutting down' in r.text

print('Epson certificate successfully uploaded to printer.')
