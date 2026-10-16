# Nova Spec Summarizer

The Nova Spec Summarizer is a command line tool that uses an LLM behind a
[litellm](https://docs.litellm.ai/) proxy (OpenAI-compatible API) to generate
3 summaries given a `openstack/nova-specs` patch proposal Gerrit URL:

1. A summary of the current proposal compared with versions that were approved in previous release cycles
2. A summary of changes in each patchset of the current proposal
3. A summary of the conversation in the review comments of the current proposal

## Prerequisites

Access to a [litellm](https://docs.litellm.ai/) proxy is required, serving at
least one model. For example, the GLM 5.3 model
(`rits/zai-org/glm-5-3`) can be served by adding to
`~/.config/litellm/config.yaml`:

```yaml
model_list:
  - model_name: rits/zai-org/glm-5-3
    litellm_params:
      custom_llm_provider: openai
      model: openai/rits/zai-org/glm-5-3
      api_key: os.environ/APIKEY
      base_url: https://api.example.net/v1
```

and starting the proxy with `litellm --port 4000 --config ~/.config/litellm/config.yaml`.

### Environment variables

Just an example (the API key can be the dummy `sk-litellm-proxy` when the
local proxy requires no master key; the real ENMaaS key stays in the litellm
config on the host):
```
export GERRIT_USER=myuser
export GERRIT_HTTP_PASS=mypassword
export LITELLM_URL=http://localhost:4000
export LITELLM_API_KEY=sk-litellm-proxy
export LITELLM_MODEL=rits/zai-org/glm-5-3
```

When `LITELLM_URL` / `LITELLM_API_KEY` are not set, the script falls back to
the `OPENAI_BASE_URL` / `OPENAI_HOST` / `OPENAI_API_KEY` variables for
litellm proxy gateway, so it works inside that sandbox without extra exports.

### Python packages

The `gradio` package is optional in that it is only needed for the web application.
```
pip install requests colorama termcolor gradio
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
