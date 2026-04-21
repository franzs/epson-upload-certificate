# Epson Printer/Scanner TLS Certificate Upload Tool

A Python script to automate the upload of TLS certificates to Epson network printers and scanners via their web interface.

## Description

This tool automates the process of uploading TLS certificates to Epson printers or scanners that support HTTPS administration. It handles authentication, certificate splitting (Epson devices require certificate chains to be split into individual certificates), and validation of the upload process.

> [!NOTE]
>
> This tool works by automating the printer's web interface. If Epson changes the web interface structure in future firmware updates, the script may need to be updated accordingly.

## Credit

The idea and the original Python script come from [Fazal Majid](https://blog.majid.info/). He did all the hard initial work and published it here:
[Automating Epson SSL/TLS certificate renewal](https://blog.majid.info/epson-certificates/)

## Features

- Automated certificate upload via Epson's web interface
- Supports certificate chains (up to 3 certificates)
- Secure credential handling via environment variables
- Configurable request timeout
- Comprehensive error handling and validation
- PEM/DER format support

## Requirements

- Python 3.6 or higher
- `requests` library
- `html5lib` library

## Installation

Clone this repository:

```bash
git clone https://github.com/franzs/epson-upload-certificate.git
cd epson-upload-certificate
```

Install required dependencies:

```bash
pip install requests html5lib
```

Or using `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Usage

### Example Usage

```bash
export EPSON_CERT_UPLOAD_USERNAME="admin"
export EPSON_CERT_UPLOAD_PASSWORD="your_password"

./epson-cert-upload.py \
  --url https://printer.example.com \
  --cert /path/to/certificate.pem \
  --key /path/to/private-key.pem
```

> [!WARNING]
>
> After uploading a certificate to the device, communication with the device will be interrupted for a few seconds while it applies the new certificate.

### Command Line Options

- `--url`: Base URL of the Epson printer/scanner (required)
- `--cert`: Path to the certificate file (required)
- `--key`: Path to the private key file (required)
- `--timeout`: Request timeout in seconds (default: 30)

### Environment Variables

The following environment variables must be set:

- `EPSON_CERT_UPLOAD_USERNAME`: Admin username for the printer/scanner
- `EPSON_CERT_UPLOAD_PASSWORD`: Admin password for the printer/scanner

## Certificate Requirements

- **Format**: PEM or DER format
- **Certificate Chain**: Maximum of 3 certificates
- **Private Key**: Must match the certificate
- **Bundled Certificates**: Supported (automatically split)

> [!NOTE]
>
> Let's Encrypt certificates work fine. Use `fullchain.pem` with `--cert` and `privkey.pem` with `--key`.

## Troubleshooting

### "Authentication failed with status code 401"

- Verify your username and password are correct
- Ensure the device's web interface is accessible

### "Setup token not found in form"

- The device's web interface may have changed
- Check if your device model is supported

### "Too many certificates found"

- Epson devices support a maximum of 3 certificates in the chain
- Remove intermediate certificates if possible

### Connection timeout

- Increase the timeout with `--timeout 60`
- Check network connectivity to the device

### "No certificates found in file"

- Verify the certificate file is in PEM format
- Ensure the file contains `BEGIN CERTIFICATE` and `END CERTIFICATE` markers

### Certificate verify failed: self-signed certificate

Initially Epson devices have a self-signed certificate. Switching to a CA-signed certificate with this script is not covered, yet. Please import a CA-signed certificate manually and set `Server Certificate` to `CA-signed certificate` in the web interface.

## Tested Devices

This script has been tested with the following Epson devices:

- EcoTank ET-16600
- WorkForce DS-730N

If you successfully use this with other Epson models, please open an issue or PR to add it to the list!

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This is an unofficial tool and is not affiliated with or endorsed by Epson. Use at your own risk. Always backup your printer configuration before making changes.
