# Nova Spec Summarizer

The Nova Spec Summarizer is a command line tool that uses Claude AI to generate 3 summaries given a `openstack/nova-specs` patch proposal Gerrit URL:

1. A summary of the current proposal compared with versions that were approved in previous release cycles
2. A summary of changes in each patchset of the current proposal
3. A summary of the conversation in the review comments of the current proposal

## Prerequisites

Access to a Claude model hosted on Vertex AI is required.

### Environment variables

Just an example:
```
export GERRIT_USER=myuser
export GERRIT_HTTP_PASS=mypassword
export CLAUDE_VERTEX_API_URL=https://$ENDPOINT/v1/projects/$PROJECT_ID/locations/$LOCATION/publishers/anthropic/models/$MODEL:streamRawPredict
export CLAUDE_VERTEX_API_KEY=myapikey
```

### Python packages

The `gradio` package is optional in that it is only needed for the web application.
```
pip install colorama
pip install gradio
```

## CLI usage

If the `--url` is not provided, there will be a prompt for input on the command line.
```
python nova_spec_summarizer.py --url https://review.opendev.org/c/openstack/nova-specs/+/123456
```

The summaries will be output to the console.

## Web application usage

Start the web application:
```
$ python app.py
* Running on local URL:  http://127.0.0.1:7860
* To create a public link, set `share=True` in `launch()`.
```

Navigate to the indicated URL `http://127.0.0.1:7860` in a web browser.
