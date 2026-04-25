#!/usr/bin/env python3

import argparse
import io
import os
import sys
import time

from typing import Any
from urllib.parse import urljoin

import html5lib
import requests
import urllib3

URL_PATH_AUTHENTICATE = 'PRESENTATION/ADVANCED/PASSWORD/SET'
URL_PATH_CA_CERT_STATUS = 'PRESENTATION/ADVANCED/NWS_CERT_SSLTLS/TOP'
URL_PATH_CA_IMPORT = 'PRESENTATION/ADVANCED/NWS_CERT_SSLTLS/CA_IMPORT'
URL_PATH_SET_CA_TYPE = 'PRESENTATION/ADVANCED/NWS_CERT_SSLTLS/SET'
URL_PATH_UPLOAD_CERT = 'PRESENTATIONEX/CERT/IMPORT_CHAIN'

CERT_TYPE_CA = 'CA-SIGNED_CERT'
CERT_TYPE_SELF_SIGNED = 'SELF-SIGNED_CERT'

REAUTH_TOTAL_WAIT_TIME = 120.0  # seconds
REAUTH_POLL_INTERVAL = 5.0  # seconds


class EpsonError(Exception):
    """Raised when printer returns unexpected response."""

    pass


def authenticate(
    s: requests.Session, url: str, timeout: float, username: str, password: str
) -> None:
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


def _fetch_and_parse_form(
    s: requests.Session, url: str, timeout: float, url_path: str
) -> tuple[dict[str, str], Any]:
    """Fetch a form page and return its hidden input data and parsed HTML tree."""
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

    return data, tree


def get_form_data(s: requests.Session, url: str, timeout: float) -> dict[str, str]:
    """Fetch a form page and return its hidden input fields."""
    data, _ = _fetch_and_parse_form(s, url, timeout, URL_PATH_CA_IMPORT)

    return data


def get_form_data_and_ca_cert_type(
    s: requests.Session, url: str, timeout: float
) -> dict[str, str]:
    """Fetch the CA cert status page and return form data including the active cert type."""
    data, tree = _fetch_and_parse_form(s, url, timeout, URL_PATH_CA_CERT_STATUS)

    cert_type = None

    for form in tree.iter('form'):
        if form.get('id') == 'input_form':
            # Find selected option within this form
            for option in form.iter('option'):
                if option.get('selected') is not None:
                    cert_type = option.get('value')
                    break
            break

    if cert_type:
        data['cert_type'] = cert_type
    else:
        raise EpsonError('No cert type found.')

    return data


def split_cert_chain(cert_path: str) -> list[str]:
    """Split a PEM file into its individual certificate components."""
    with open(cert_path, 'r') as f:
        lines = f.readlines()

    certs: list[str] = []
    current: list[str] = []

    for line in lines:
        if line.strip():
            current.append(line)
            if 'END CERTIFICATE' in line:
                certs.append(''.join(current))
                current = []

    if not certs:
        raise ValueError('No certificates found in file')
    if len(certs) > 3:
        raise ValueError(f'Too many certificates ({len(certs)}), maximum is 3')

    return certs


def upload_cert(
    s: requests.Session,
    url: str,
    timeout: float,
    data: dict[str, str],
    cert: str,
    key: str,
) -> None:
    post_data = {**data, 'format': 'pem_der'}

    post_data.pop('cert0', None)
    post_data.pop('cert1', None)
    post_data.pop('cert2', None)
    post_data.pop('key', None)

    certs = split_cert_chain(cert)

    with open(key, 'rb') as key_file:
        key_content = key_file.read()

    files = {
        'key': io.BytesIO(key_content),
    }

    for certno, cert_pem in enumerate(certs):
        files[f'cert{certno}'] = io.BytesIO(cert_pem.encode('utf-8'))

    upload_url = urljoin(url, URL_PATH_UPLOAD_CERT)

    r = s.post(upload_url, files=files, data=post_data, timeout=timeout)
    r.raise_for_status()

    if 'Shutting down' not in r.text and 'Setup complete' not in r.text:
        raise EpsonError(f'Missing success message in response at {upload_url}')


def wait_for_reauthentication(
    s: requests.Session,
    url: str,
    timeout: float,
    username: str,
    password: str,
    total_wait_time: float = REAUTH_TOTAL_WAIT_TIME,
    poll_interval: float = REAUTH_POLL_INTERVAL,
) -> None:
    start_time = time.monotonic()

    while time.monotonic() - start_time < total_wait_time:
        try:
            # Clear any old session cookies that might be invalid after the restart
            s.cookies.clear()

            # Attempt to authenticate. This is our "health check".
            authenticate(s, url, timeout, username, password)

            # If authentication succeeds, the service is up.
            return
        except requests.exceptions.RequestException:
            # This is expected while the service is restarting.
            pass

        time.sleep(poll_interval)

    # If the loop completes without returning, we've timed out.
    raise TimeoutError(
        f"Service did not become available within {total_wait_time} seconds."
    )


def set_ca_cert_type(
    s: requests.Session, url: str, timeout: float, data: dict[str, str]
) -> None:
    post_data = {
        'INPUTT_SETUPTOKEN': data['INPUTT_SETUPTOKEN'],
        'SEL_SSLTLSUSECERT': CERT_TYPE_CA,
    }

    set_url = urljoin(url, URL_PATH_SET_CA_TYPE)

    r = s.post(set_url, data=post_data, timeout=timeout)
    r.raise_for_status()

    if 'Shutting down' not in r.text:
        raise EpsonError(f'Missing success message in response at {set_url}')


def validate_file(path: str) -> str:
    """Validate that file exists and is readable."""
    if not os.path.isfile(path):
        raise argparse.ArgumentTypeError(f'File not found: {path}')

    if not os.access(path, os.R_OK):
        raise argparse.ArgumentTypeError(f'File not readable: {path}')

    return path


def main() -> None:
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Upload SSL/TLS certificate to Epson printer'
    )

    parser.add_argument(
        '--url',
        required=True,
        help='Base URL of the Epson printer (e.g., https://myepson.example.com/)',
    )
    parser.add_argument(
        '--cert', required=True, type=validate_file, help='Path to the certificate file'
    )
    parser.add_argument(
        '--key', required=True, type=validate_file, help='Path to the private key file'
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=30,
        help='Request timeout in seconds (default: 30)',
    )

    args = parser.parse_args()

    # Get credentials from environment variables
    username = os.environ.get('EPSON_CERT_UPLOAD_USERNAME')
    password = os.environ.get('EPSON_CERT_UPLOAD_PASSWORD')

    if not username:
        print(
            'Error: EPSON_CERT_UPLOAD_USERNAME environment variable not set',
            file=sys.stderr,
        )
        sys.exit(1)

    if not password:
        print(
            'Error: EPSON_CERT_UPLOAD_PASSWORD environment variable not set',
            file=sys.stderr,
        )
        sys.exit(1)

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    s = requests.Session()
    s.verify = False

    # authenticate
    try:
        authenticate(s, args.url, args.timeout, username, password)
    except requests.RequestException as e:
        print(f'Authentication attempt failed: {e}', file=sys.stderr)
        sys.exit(1)

    # get CA cert type
    try:
        data = get_form_data_and_ca_cert_type(s, args.url, args.timeout)
    except (requests.RequestException, EpsonError) as e:
        print(f'Getting data from form failed: {e}', file=sys.stderr)
        sys.exit(1)

    cert_type = data['cert_type']

    if cert_type == CERT_TYPE_CA:
        s.verify = True

    # get the cert update form iframe and its token
    try:
        data = get_form_data(s, args.url, args.timeout)
    except (requests.RequestException, EpsonError) as e:
        print(f'Getting data from form failed: {e}', file=sys.stderr)
        sys.exit(1)

    # upload key and certs
    try:
        upload_cert(s, args.url, args.timeout, data, args.cert, args.key)
    except (EpsonError, requests.RequestException, ValueError) as e:
        print(f'Uploading certificate failed: {e}', file=sys.stderr)
        sys.exit(1)

    # check if we need to switch cert type
    if cert_type == CERT_TYPE_SELF_SIGNED:
        # wait for the service to come back online by polling and reauthenticate
        try:
            wait_for_reauthentication(s, args.url, args.timeout, username, password)
        except TimeoutError as e:
            print(f'Waiting for reauthentication failed: {e}', file=sys.stderr)
            sys.exit(1)

        # Fetch fresh form data after restart — previous token is stale
        try:
            data = get_form_data_and_ca_cert_type(s, args.url, args.timeout)
        except (requests.RequestException, EpsonError) as e:
            print(f'Getting data from form failed: {e}', file=sys.stderr)
            sys.exit(1)

        # set CA cert type
        try:
            set_ca_cert_type(s, args.url, args.timeout, data)
        except (EpsonError, requests.RequestException) as e:
            print(f'Setting CA certificate type failed: {e}', file=sys.stderr)
            sys.exit(1)

    print('Epson certificate successfully uploaded to printer.')


if __name__ == '__main__':
    main()
