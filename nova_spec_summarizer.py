#! /usr/bin/env python3

import argparse
import base64
import json
import os
import urllib.parse

from colorama import just_fix_windows_console
import requests
from termcolor import colored


CERT_PATH = os.environ.get('CERT_PATH') or '/etc/ssl/certs/ca-certificates.crt'

PAST_RELEASES = [
    '2025.2', '2025.1', '2024.2', '2024.1', '2023.2', '2023.1', 'zed', 'yoga',
    'xena', 'wallaby', 'victoria', 'ussuri', 'train']

def query_model(prompt):
    user_key = os.environ.get('VERTEX_API_KEY')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {user_key}',
    }

    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "maxOutputTokens": 8192,
            "temperature": 0.0,
        }
    }

    url = os.environ.get('VERTEX_API_URL')
    print('... Calling the LLM at ' + colored(f'{url}', 'green') + ' -- this will take several seconds')

    r = requests.post(url, headers=headers, data=json.dumps(payload))

    if r.status_code != 200:
        print(colored(f'Error: API returned status {r.status_code}', 'red'))
        print(f'Response: {r.text[:500]}')
        raise RuntimeError(f'LLM API request failed with status {r.status_code}')

    response_json = r.json()

    # Handle the case where the response is a list of chunks (streaming response)
    if isinstance(response_json, list):
        if not response_json:
            raise RuntimeError('LLM API returned an empty list response')

        # Check for error in the first chunk
        if 'error' in response_json[0]:
            print(colored(f'Error from API: {response_json[0]["error"]}', 'red'))
            raise RuntimeError(f'LLM API error: {response_json[0]["error"]}')

        all_text_parts = []
        for chunk in response_json:
            try:
                # We expect the text to be in candidates -> content -> parts -> text
                text_part = chunk['candidates'][0]['content']['parts'][0]['text']
                all_text_parts.append(text_part)
            except (KeyError, IndexError):
                # This might happen if a chunk is malformed or doesn't contain text
                print(colored(f'Warning: Could not parse a chunk of the streaming response: {chunk}', 'yellow'))
                continue
        
        result_text = "".join(all_text_parts)

    # Handle the case where the response is a single JSON object (non-streaming)
    elif isinstance(response_json, dict):
        if 'error' in response_json:
            print(colored(f'Error from API: {response_json["error"]}', 'red'))
            raise RuntimeError(f'LLM API error: {response_json["error"]}')

        if 'candidates' not in response_json or not response_json.get('candidates'):
            print(colored('Error: No candidates in API response', 'red'))
            print(f'Response keys: {response_json.keys()}')
            print(f'Full response: {str(response_json)[:500]}')
            raise RuntimeError('LLM API response missing candidates field')
        
        result_text = response_json['candidates'][0]['content']['parts'][0]['text']
    
    else:
        # Handle any other unexpected format
        raise RuntimeError(f'LLM API returned unexpected response format: {type(response_json)}')


    print('... Received result from the LLM')
    print(f'\n{result_text}\n')
    return result_text


def parse_gerrit_response(response, verbose=None):
    """Parse Gerrit API response, handling the XSSI prevention prefix."""
    if response.status_code != 200:
        raise RuntimeError(
            f'Gerrit API returned status {response.status_code}: {response.text[:200]}')
    
    text = response.text
    # Gerrit prepends ")]}'" to prevent XSSI attacks
    if text.startswith(")]}'"):
        text = text[4:]
    
    if not text.strip():
        raise RuntimeError('Gerrit API returned empty response')
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if verbose:
            print(f'... Response text: {response.text[:200]}')
        raise RuntimeError(f'Failed to parse Gerrit response: {e}')


def get_gerrit_file_content(change_id, revision_id='current', verbose=None):
    http_user = os.environ.get('GERRIT_USER')
    http_password = os.environ.get('GERRIT_HTTP_PASS')
    url = f'https://review.opendev.org/a/changes/{change_id}/revisions/{revision_id}/files'

    if verbose:
        print('... Calling Gerrit at ' + colored(f'{url}', 'green'))

    r = requests.get(url, auth=(http_user, http_password), verify=CERT_PATH)
    resp = parse_gerrit_response(r, verbose=verbose)
    resp.pop('/COMMIT_MSG')
    if len(resp) > 1:
        raise ValueError('Found more than one .rst file for the spec')

    filename = next(iter(resp))
    base_filename = os.path.basename(filename)
    encoded_filename = urllib.parse.quote(filename, safe='')
    url += f'/{encoded_filename}/content'
    if verbose:
        print('... Calling Gerrit at ' + colored(f'{url}', 'green'))

    r = requests.get(url, auth=(http_user, http_password), verify=CERT_PATH)

    return base_filename, base64.b64decode(r.text)


def summarize_current_conversation(change_id, verbose=None):
    http_user = os.environ.get('GERRIT_USER')
    http_password = os.environ.get('GERRIT_HTTP_PASS')
    url = f'https://review.opendev.org/a/changes/{change_id}/comments?enable-context'

    if verbose:
        print('... Calling Gerrit at ' + colored(f'{url}', 'green'))
    r = requests.get(url, auth=(http_user, http_password), verify=CERT_PATH)
    resp = parse_gerrit_response(r, verbose=verbose)

    prompt = f"""
Here are the revisions of the spec in chronological order:
This is the JSON response from the Gerrit /changes/{{change-id}}/comments API:

{json.dumps(resp)}

Please provide a summary of the conversation among the proposal reviewers.
"""

    return query_model(prompt)


def summarize_current_changes(change_id, verbose=None):
    http_user = os.environ.get('GERRIT_USER')
    http_password = os.environ.get('GERRIT_HTTP_PASS')
    url = f'https://review.opendev.org/a/changes/{change_id}?o=ALL_REVISIONS'

    if verbose:
        print('... Calling Gerrit at ' + colored(f'{url}', 'green'))
    r = requests.get(url, auth=(http_user, http_password), verify=CERT_PATH)
    resp = parse_gerrit_response(r, verbose=verbose)

    revisions = []
    revision_infos = resp['revisions']
    sorted_revision_infos = sorted(revision_infos.items(), key=lambda item: item[1]['_number'])

    for revision_id, revision_info in sorted_revision_infos:
        filename, content = get_gerrit_file_content(change_id, revision_id=revision_id, verbose=verbose)
        revisions.append(str(content))

    prompt = """
Here are the patchsets of the spec in chronological order:

{}

Please provide:
1. A summary of what changed in each patchset
2. What new sections or requirements were added
3. What was removed or modified
4. Any significant shifts in approach or design decisions
""".format('\n\n'.join(revisions))

    return query_model(prompt)


def summarize_history(change_id, verbose=None):
    filename, content = get_gerrit_file_content(change_id, verbose=verbose)
    revisions = [content]
    for release in PAST_RELEASES:
        url = f'https://raw.githubusercontent.com/openstack/nova-specs/master/specs/{release}/approved/{filename}'
        if verbose:
            print('... Checking for past approval at ' + colored(f'{url}', 'yellow'))

        r = requests.get(url, verify=CERT_PATH)
        if r.status_code != 404:
            print('... Found past approval from the ' + colored(f'{release}', 'green') + ' release')
            revisions.append(r.text)

    prompt = """
Here's the current proposal of a design spec:

{}

And here are the approvals of the spec from previous releases, in reverse chronological order:

{}

Please provide:
1. A summary of what changed in each proposal
2. What new sections or requirements were added
3. What was removed or modified
4. Any significant shifts in approach or design decisions
""".format(revisions[0], '\n\n'.join(revisions[1:]))

    return query_model(prompt)


def main():
    required_vars = ('GERRIT_USER', 'GERRIT_HTTP_PASS', 'VERTEX_API_URL', 'VERTEX_API_KEY')
    if not all([env_var in os.environ for env_var in required_vars]):
        print(f'The following environment variables are required to be set: {", ".join(required_vars)}')
        return 1

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output.')
    parser.add_argument('--url', help='URL for the spec proposed in Gerrit.')
    args = parser.parse_args()

    # use Colorama to make Termcolor work on Windows too
    just_fix_windows_console()

    spec_url = args.url or input('Enter the URL for the spec proposed in Gerrit: ')
    print('... Processing spec at ' + colored(f'{spec_url}', 'green'))
    change_id = spec_url.split('/')[-1]

    if args.verbose:
        print('... The change-id is ' + colored(f'{change_id}', 'yellow'))

    print(colored('Summarizing the current proposal and past approvals', 'yellow'))
    summarize_history(change_id, verbose=args.verbose)

    print(colored('Summarizing changes in each patchset of the current proposal', 'yellow'))
    summarize_current_changes(change_id, verbose=args.verbose)

    print(colored('Summarizing conversation in the current proposal', 'yellow'))
    summarize_current_conversation(change_id, verbose=args.verbose)


if __name__ == "__main__":
    main()
