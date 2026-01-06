#! /usr/bin/env python3

import gradio as gr

import nova_spec_summarizer


def summarize(spec_url):
    change_id = spec_url.split('/')[-1]
    yield "\u23f3 Analyzing with Claude AI (this may take a few minutes)...", '', ''
    yield (nova_spec_summarizer.summarize_history(change_id),
           nova_spec_summarizer.summarize_current_changes(change_id),
           nova_spec_summarizer.summarize_current_conversation(change_id))


with gr.Blocks() as demo:
    gr.Markdown('Generate a summary for a proposed openstack/nova-specs review.')
    inp = gr.Textbox(show_label=False, submit_btn='Submit', max_length=100, placeholder='Gerrit review URL')
    with gr.Row():
        out1 = gr.Markdown()
        out2 = gr.Markdown()
        out3 = gr.Markdown()
    inp.submit(fn=summarize, inputs=inp, outputs=[out1, out2, out3])


demo.launch()
