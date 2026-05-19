import json
import gradio as gr

from birdai.perception import analyze_observation
from birdai.logging_utils import log_observation


def run_birdai(file):
    if file is None:
        return "Please upload a bird image, audio recording, or short video."

    file_path = file.name

    try:
        result = analyze_observation(file_path, use_mock=False)
        log_observation(file_path, result)

        return json.dumps(
            result.model_dump(),
            indent=2,
            ensure_ascii=False,
        )

    except Exception as exc:
        return f"Error: {exc}"


with gr.Blocks(title="BirdAI") as demo:
    gr.Markdown(
        """
        # BirdAI: Embodied Bird Perception MVP

        Upload a bird image, Merlin-style audio recording, or short Birdfy video.

        This MVP returns:
        - likely bird species
        - uncertainty level
        - ecological plausibility
        - suggested next perception action
        """
    )

    file_input = gr.File(
        label="Upload image, audio, or short video",
        file_types=["image", "audio", "video"],
    )

    output = gr.Code(label="BirdAI result", language="json")

    analyze_button = gr.Button("Analyze observation")
    reset_button = gr.Button("Reset")

    analyze_button.click(fn=run_birdai, inputs=file_input, outputs=output)
    reset_button.click(
        fn=lambda: (None, ""),
        inputs=[],
        outputs=[file_input, output],
    )


if __name__ == "__main__":
    demo.launch()