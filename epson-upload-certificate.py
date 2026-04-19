#!/usr/bin/env python3

import requests, html5lib, io

URL = 'https://myepson.example.com/'
USERNAME = 'majid'
PASSWORD = 'your-admin-UI-password-here'
KEYFILE = '/home/majid/web/acme-tiny/epson.key'
CERTFILE = '/home/majid/web/acme-tiny/epson.crt'

########################################################################
# step 1, authenticate
jar = requests.cookies.RequestsCookieJar()
set_url = URL + 'PRESENTATION/ADVANCED/PASSWORD/SET'
r = requests.post(
    set_url,
    cookies=jar,
    data={
        'INPUTT_USERNAME': USERNAME,
        'access': 'https',
        'INPUTT_PASSWORD': PASSWORD,
        'INPUTT_ACCSESSMETHOD': 0,
        'INPUTT_DUMMY': '',
    },
)
assert r.status_code == 200
jar = r.cookies

########################################################################
# step 2, get the cert update form iframe and its token
form_url = URL + 'PRESENTATION/ADVANCED/NWS_CERT_SSLTLS/CA_IMPORT'
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

upload_url = URL + 'PRESENTATIONEX/CERT/IMPORT_CHAIN'

########################################################################
# Epson doesn't seem to like bundled certificates,
# so split it into its componens
f = open(CERTFILE, 'r')
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
    'key': open(KEYFILE, 'rb'),
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
