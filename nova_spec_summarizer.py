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
    '2026.1', '2026.2',
    '2025.2', '2025.1', '2024.2', '2024.1', '2023.2', '2023.1',
    'gazpacho', 'flamingo', 'epoxy', 'dalmatian', 'caracal', 'bobcat',
    'antelope', 'zed', 'yoga', 'xena', 'wallaby', 'victoria', 'ussuri',
    'train']

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


def analyze_cross_reference(change_id, cross_ref_change_id, verbose=None):
    """Fetch both specs and analyze cross-project alignment."""
    main_filename, main_content = get_gerrit_file_content(
        change_id, verbose=verbose)
    cross_filename, cross_content = get_gerrit_file_content(
        cross_ref_change_id, verbose=verbose)

    prompt = f"""
You are an OpenStack cross-project spec analyst. You are given two design specs
from different but related OpenStack projects (e.g. Nova and Cyborg, Nova and
Neutron, Nova and Cinder, etc.). These specs describe complementary sides of a
cross-project feature: one spec covers the "initiating" side and the other
covers the "receiving" or "implementing" side.

=== MAIN SPEC ({main_filename}) ===
{main_content}

=== CROSS-REFERENCE SPEC ({cross_filename}) ===
{cross_content}

Analyze these two specs as a pair of cross-project design documents and provide:

1. **Project Identification**: Identify which OpenStack projects each spec
   belongs to, and which project is the "driving" side vs. the "supporting"
   side of the feature.

2. **Cross-Project Alignment**: How well do the two specs align on the overall
   feature design? Summarize the shared goals and the division of
   responsibilities between the two projects.

3. **API & Interface Contracts**: Do the specs agree on the APIs, REST
   endpoints, RPC calls, or data formats that cross the project boundary? Flag
   any mismatches in request/response schemas, versioning expectations, or
   capability negotiation.

4. **Workflow & Lifecycle Consistency**: Trace the end-to-end workflow across
   both specs. Are the state machines, lifecycle hooks, and ordering of
   operations consistent? Identify any gaps where one spec assumes a step that
   the other does not describe.

5. **Conflicting Design Requirements**: Identify any requirements, constraints,
   or design decisions in one spec that directly contradict or are incompatible
   with the other. This includes conflicting assumptions about data ownership,
   scheduling, resource management, or upgrade/migration strategies.

6. **Missing or Unconnected Design Connections**: Identify design elements in
   one spec that reference or depend on the other project but have no
   corresponding section in the counterpart spec. These are "dangling
   references" — features, callbacks, notifications, or configuration options
   that one side expects but the other side does not address.

7. **Error Handling & Failure Modes**: Do both specs handle cross-project
   failure scenarios consistently? What happens if the "other side" is
   unavailable, returns errors, or behaves unexpectedly?

8. **Upgrade & Compatibility**: Are the specs aligned on how the cross-project
   feature behaves during rolling upgrades, when one project is upgraded before
   the other?

9. **Recommendations**: Provide concrete suggestions for improving alignment
   between the two specs, closing design gaps, and resolving contradictions.
"""

    return query_model(prompt)


def summarize_history(change_id, verbose=None, specs_repo='openstack/nova-specs'):
    filename, content = get_gerrit_file_content(change_id, verbose=verbose)
    revisions = [content]
    for release in PAST_RELEASES:
        # Check for approved specs
        url = f'https://raw.githubusercontent.com/{specs_repo}/master/specs/{release}/approved/{filename}'
        if verbose:
            print('... Checking for past approval at ' + colored(f'{url}', 'yellow'))

        r = requests.get(url, verify=CERT_PATH)
        if r.status_code != 404:
            print('... Found past approval from the ' + colored(f'{release}', 'green') + ' release')
            revisions.append(r.text)
            continue

        # Check for implemented specs
        url = f'https://raw.githubusercontent.com/{specs_repo}/master/specs/{release}/implemented/{filename}'
        if verbose:
            print('... Checking for past implementation at ' + colored(f'{url}', 'yellow'))

        r = requests.get(url, verify=CERT_PATH)
        if r.status_code != 404:
            print('... Found past implementation from the ' + colored(f'{release}', 'green') + ' release')
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
    parser.add_argument('--specs-repo', default='openstack/nova-specs',
                        help='GitHub repository for specs (default: openstack/nova-specs).')
    parser.add_argument('--cross-ref',
                        help='URL for a related cross-project spec in Gerrit '
                             '(e.g. a Cyborg spec that complements a Nova spec).')
    args = parser.parse_args()

    # use Colorama to make Termcolor work on Windows too
    just_fix_windows_console()

    spec_url = args.url or input('Enter the URL for the spec proposed in Gerrit: ')
    print('... Processing spec at ' + colored(f'{spec_url}', 'green'))
    change_id = spec_url.split('/')[-1]

    if args.verbose:
        print('... The change-id is ' + colored(f'{change_id}', 'yellow'))

    print(colored('Summarizing the current proposal and past approvals', 'yellow'))
    summarize_history(change_id, verbose=args.verbose, specs_repo=args.specs_repo)

    print(colored('Summarizing changes in each patchset of the current proposal', 'yellow'))
    summarize_current_changes(change_id, verbose=args.verbose)

    print(colored('Summarizing conversation in the current proposal', 'yellow'))
    summarize_current_conversation(change_id, verbose=args.verbose)

    if args.cross_ref:
        cross_ref_url = args.cross_ref
        print('... Processing cross-reference spec at ' + colored(f'{cross_ref_url}', 'green'))
        cross_ref_change_id = cross_ref_url.split('/')[-1]
        if args.verbose:
            print('... The cross-ref change-id is ' + colored(f'{cross_ref_change_id}', 'yellow'))

        print(colored('Analyzing cross-project spec alignment', 'yellow'))
        analyze_cross_reference(change_id, cross_ref_change_id, verbose=args.verbose)


if __name__ == "__main__":
    main()
