import json

import gradio as gr

from birdai.context import (
    build_observation_context,
    get_default_observation_context,
)
from birdai.logging_utils import log_observation
from birdai.perception import analyze_observation


def _context_defaults() -> tuple[str, str, str, float | None, float | None]:
    context = get_default_observation_context()
    return (
        context.observation_date.isoformat(),
        context.observation_time.isoformat(timespec="seconds"),
        context.location_text,
        context.latitude,
        context.longitude,
    )


def run_birdai(
    file,
    observation_date: str,
    observation_time: str,
    location_text: str,
    latitude: float | None,
    longitude: float | None,
):
    if file is None:
        return (
            "Please upload a bird image or audio recording.",
            "",
        )

    try:
        observation_context = build_observation_context(
            observation_date=observation_date,
            observation_time=observation_time,
            location_text=location_text,
            latitude=latitude,
            longitude=longitude,
        )
        result = analyze_observation(file.name, observation_context, use_mock=False)
        log_observation(file.name, result)

        warning_text = "\n".join(result.warnings) if result.warnings else "No warnings."
        result_json = json.dumps(
            result.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
        return warning_text, result_json

    except Exception as exc:
        return f"Error: {exc}", ""


with gr.Blocks(title="BirdAI") as demo:
    gr.Markdown(
        """
        # BirdAI: Secure Contextual Bird Identification

        Upload an image or audio recording and review the
        editable observation context before analysis.
        """
    )

    file_input = gr.File(
        label="Upload image or audio",
        file_types=["image", "audio"],
    )

    default_date, default_time, default_location, default_lat, default_lng = (
        _context_defaults()
    )

    with gr.Row():
        observation_date_input = gr.Textbox(
            label="Observation date (YYYY-MM-DD)",
            value=default_date,
        )
        observation_time_input = gr.Textbox(
            label="Observation time (HH:MM:SS)",
            value=default_time,
        )

    location_input = gr.Textbox(
        label="Location",
        value=default_location,
    )

    with gr.Row():
        latitude_input = gr.Number(label="Latitude", value=default_lat)
        longitude_input = gr.Number(label="Longitude", value=default_lng)

    warnings_output = gr.Textbox(label="Warnings", lines=4, interactive=False)
    result_output = gr.Code(label="BirdAI result", language="json")

    analyze_button = gr.Button("Analyze observation")
    reset_button = gr.Button("Reset")

    analyze_button.click(
        fn=run_birdai,
        inputs=[
            file_input,
            observation_date_input,
            observation_time_input,
            location_input,
            latitude_input,
            longitude_input,
        ],
        outputs=[warnings_output, result_output],
    )
    reset_button.click(
        fn=lambda: (None, *_context_defaults(), "No warnings.", ""),
        inputs=[],
        outputs=[
            file_input,
            observation_date_input,
            observation_time_input,
            location_input,
            latitude_input,
            longitude_input,
            warnings_output,
            result_output,
        ],
    )


if __name__ == "__main__":
    demo.launch()
