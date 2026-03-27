#! /usr/bin/env python3

import gradio as gr

import nova_spec_summarizer


def summarize(spec_url, cross_ref_url):
    change_id = spec_url.split('/')[-1]
    has_cross_ref = bool(cross_ref_url and cross_ref_url.strip())
    placeholder = "\u23f3 Analyzing with Claude AI (this may take a few minutes)..."
    yield placeholder, '', '', ''
    history = nova_spec_summarizer.summarize_history(change_id)
    changes = nova_spec_summarizer.summarize_current_changes(change_id)
    conversation = nova_spec_summarizer.summarize_current_conversation(change_id)

    if has_cross_ref:
        cross_ref_change_id = cross_ref_url.strip().split('/')[-1]
        cross_analysis = nova_spec_summarizer.analyze_cross_reference(
            change_id, cross_ref_change_id)
    else:
        cross_analysis = '*No cross-reference spec provided.*'

    yield history, changes, conversation, cross_analysis


with gr.Blocks() as demo:
    gr.Markdown('Generate a summary for a proposed openstack/nova-specs review.')
    with gr.Row():
        inp = gr.Textbox(show_label=False, submit_btn='Submit', max_length=100,
                         placeholder='Gerrit review URL')
        cross_inp = gr.Textbox(show_label=False, max_length=100,
                               placeholder='Cross-project spec URL (optional)')
    with gr.Row():
        out1 = gr.Markdown()
        out2 = gr.Markdown()
        out3 = gr.Markdown()
    out4 = gr.Markdown(label='Cross-Project Analysis')
    inp.submit(fn=summarize, inputs=[inp, cross_inp],
               outputs=[out1, out2, out3, out4])


demo.launch()
