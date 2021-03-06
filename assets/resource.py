#!/usr/bin/env python3

import json
import logging as log
import os
import sys
import tempfile

import requests


class HTTPResource:
    """HTTP resource implementation."""

    def cmd(self, name, arg, data):
        """Make the requests."""

        method = data.get('method', 'GET')
        check_method = data.get('check_method', 'HEAD')
        if name == 'check': method = check_method
        uri = data['uri']
        headers = data.get('headers', {})
        json_data = data.get('json', None)
        ssl_verify = data.get('ssl_verify', True)
        ok_responses = data.get('ok_responses', [200, 201, 202, 204])
        form_data = data.get('form_data')
        version_header = data.get('version_header', 'Last-Modified')

        if isinstance(ssl_verify, bool):
            verify = ssl_verify
        elif isinstance(ssl_verify, str):
            verify = str(tempfile.NamedTemporaryFile(delete=False, prefix='ssl-').write(verify))

        request_data = None
        if form_data:
            request_data = {k: json.dumps(v, ensure_ascii=False) for k, v in form_data.items()}

        response = requests.request(method, uri, json=json_data,
                                    data=request_data, headers=headers, verify=verify)

        log.info('http response code: %s', response.status_code)
        log.info('http response text: %s', response.text)

        if response.status_code not in ok_responses:
            raise Exception('Unexpected response {}'.format(response.status_code))

        if name == 'out':
            return (response.status_code, response.text)
        elif name == 'check':
            return (response.status_code, response.headers[version_header])
        elif name == 'in':
            return (response.status_code, response.headers[version_header], response.content)

    def run(self, command_name: str, json_data: str, command_argument: str):
        """Parse input/arguments, perform requested command return output."""

        with tempfile.NamedTemporaryFile(delete=False, prefix=command_name + '-') as f:
            f.write(bytes(json_data, 'utf-8'))

        data = json.loads(json_data)

        # allow debug logging to console for tests
        if os.environ.get('RESOURCE_DEBUG', False) or data.get('source', {}).get('debug', False):
            log.basicConfig(level=log.DEBUG)
        else:
            logfile = tempfile.NamedTemporaryFile(delete=False, prefix='log')
            log.basicConfig(level=log.DEBUG, filename=logfile.name)
            stderr = log.StreamHandler()
            stderr.setLevel(log.INFO)
            log.getLogger().addHandler(stderr)

        log.debug('command: %s', command_name)
        log.debug('input: %s', data)
        log.debug('args: %s', command_argument)
        log.debug('environment: %s', os.environ)

        path = "/"
        if len(command_argument) >= 1: path = command_argument[0]

        # initialize values with Concourse environment variables
        values = {k: v for k, v in os.environ.items() if k.startswith('BUILD_') or k == 'ATC_EXTERNAL_URL'}

        # combine source and params
        params = data.get('source', {})
        params.update(data.get('params', {}))

        # allow also to interpolate params
        values.update(params)

        # key tag to load file data
        values = {k: self._load_filedata(path, v) for k, v in values.items()}

        log.debug('processed_values: %s', values)

        # apply templating of environment variables onto parameters
        rendered_params = self._interpolate(params, values)

        log.debug('rendered_params: %s', rendered_params)

        if command_name == 'out':
            status_code, text = self.cmd(command_name, command_argument, rendered_params)
            _status_code, version = self.cmd("check", command_argument, rendered_params)
            response = {"version": {"ref": version}}
            if os.environ.get('TEST', False):
                response.update(json.loads(text))
            return json.dumps(response)
        elif command_name == 'check':
            status_code, version = self.cmd(command_name, command_argument, rendered_params)
            response = [{"ref": version}]
            return json.dumps(response)
        elif command_name == 'in':
            status_code, version, data = self.cmd(command_name, command_argument, rendered_params)
            with open(path+'/'+rendered_params.get('output', 'data'), 'wb') as f:
                f.write(data)
            response = {"version": {"ref": version}, "metadata": []}
            return json.dumps(response)

    def _load_filedata(self, base_path, value):
        """Check single level values for loading and replacing with file data"""
        log.debug("filedata-test: %s", repr(value))
        if isinstance(value, dict) and "load_filedata" in value:
            log.debug("filedata-found: %s", repr(value))
            try:
                with open(base_path+'/'+value['load_filedata'], 'r') as f:
                    data = f.read()
                    log.debug("filedata-loaded: %s", repr(data))
                    if "trim" in value and value['trim']: data = data.strip()
                    log.debug("filedata-processed: %s", repr(data))
                    return data
            except FileNotFoundError:
                log.debug("filedata-failed", value)
                if 'default' in value: return value['default']
                else: raise
        else:
            return value

    def _interpolate(self, data, values):
        """Recursively apply values using format on all string key and values in data."""

        if isinstance(data, str):
            return data.format(**values)
        elif isinstance(data, list):
            return [self._interpolate(x, values) for x in data]
        elif isinstance(data, dict):
            return {self._interpolate(k, values): self._interpolate(v, values)
                    for k, v in data.items()}
        else:
            return data


print(HTTPResource().run(os.path.basename(__file__), sys.stdin.read(), sys.argv[1:]))
