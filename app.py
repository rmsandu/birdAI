import json
import tempfile
from pathlib import Path

import gradio as gr
from PIL import Image

from birdai.context import (
    build_observation_context,
    geocode_location,
    get_default_observation_context,
    reverse_geocode_coordinates,
)
from birdai.file_utils import detect_file_type
from birdai.logging_utils import log_observation
from birdai.perception import analyze_observation
from birdai.photo_metadata import extract_photo_coordinates


def _context_defaults() -> tuple[str, str, str, float | None, float | None]:
    context = get_default_observation_context()
    return (
        context.observation_date.isoformat(),
        context.observation_time.isoformat(timespec="seconds"),
        context.location_text,
        context.latitude,
        context.longitude,
    )


def _location_status_from_context_source(location_source: str) -> str:
    messages = {
        "photo_exif": "Coordinates extracted from the uploaded photo metadata.",
        "geocoded_location": "Coordinates geocoded from the provided location text.",
        "manual_coordinates": "Using the current latitude and longitude fields.",
        "config_default": "Using configured default coordinates.",
        "user_input": "Using the current location fields.",
    }
    return messages.get(location_source, f"Using coordinates from {location_source}.")


def build_photo_preview(file) -> str | None:
    if file is None:
        return None

    detected_file = detect_file_type(file.name)
    if detected_file.modality != "image":
        return None

    with Image.open(file.name) as image:
        preview = image.copy()
        preview.thumbnail((720, 720))
        with tempfile.NamedTemporaryFile(
            suffix=".png",
            delete=False,
        ) as temp_file:
            preview_path = Path(temp_file.name)
        preview.save(preview_path, format="PNG")

    return str(preview_path)


def update_coordinates_from_photo(
    file,
    location_text: str,
    latitude: float | None,
    longitude: float | None,
):
    preview_image = build_photo_preview(file)

    if file is None:
        return location_text, latitude, longitude, "No file uploaded yet.", preview_image

    detected_file = detect_file_type(file.name)
    if detected_file.modality != "image":
        return (
            location_text,
            latitude,
            longitude,
            "Uploaded file is not an image; photo GPS extraction skipped.",
            preview_image,
        )

    coordinates = extract_photo_coordinates(file.name)
    if coordinates is None:
        return (
            location_text,
            latitude,
            longitude,
            "No GPS metadata found in the uploaded photo. Use Location Search to geocode the location text.",
            preview_image,
        )

    extracted_latitude, extracted_longitude = coordinates
    resolved_location_text = location_text
    try:
        reverse_geocoded_location = reverse_geocode_coordinates(
            extracted_latitude,
            extracted_longitude,
        )
    except Exception as exc:
        status = (
            "Coordinates extracted from the uploaded photo metadata, but reverse geocoding "
            f"failed. Keeping the current location text. {exc}"
        )
    else:
        if reverse_geocoded_location:
            resolved_location_text = reverse_geocoded_location
            status = "Coordinates extracted from the uploaded photo metadata."
        else:
            status = (
                "Coordinates extracted from the uploaded photo metadata, but no matching "
                "location name was found."
            )
    return (
        resolved_location_text,
        extracted_latitude,
        extracted_longitude,
        status,
        preview_image,
    )


def use_location_search(
    location_text: str,
    latitude: float | None,
    longitude: float | None,
):
    if not location_text.strip():
        return latitude, longitude, "Enter a location before using live geolocation search."

    try:
        coordinates = geocode_location(location_text)
    except Exception as exc:
        return latitude, longitude, f"Live geolocation search failed: {exc}"

    if coordinates is None:
        return latitude, longitude, "Live geolocation search returned no coordinates."

    geocoded_latitude, geocoded_longitude = coordinates
    return (
        geocoded_latitude,
        geocoded_longitude,
        "Coordinates geocoded from the provided location text.",
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
            "No file uploaded yet.",
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
        location_status = _location_status_from_context_source(
            result.observation_context.location_source
        )
        result_json = json.dumps(
            result.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
        return warning_text, location_status, result_json

    except Exception as exc:
        return f"Error: {exc}", "Location resolution failed.", ""


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
    photo_preview = gr.Image(
        label="Photo preview",
        type="filepath",
        height=260,
        image_mode="RGB",
        interactive=False,
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

    with gr.Row():
        extract_photo_button = gr.Button("Extract From Photo")
        use_location_search_button = gr.Button("Use Location Search")

    result_output = gr.Code(label="BirdAI result", language="json")
    location_status_output = gr.Textbox(
        label="Location status",
        lines=2,
        interactive=False,
        value="Using configured default coordinates." if default_lat is not None and default_lng is not None else "No coordinates resolved yet.",
    )
    warnings_output = gr.Textbox(label="Warnings", lines=4, interactive=False)

    analyze_button = gr.Button("Analyze observation")
    reset_button = gr.Button("Reset")

    extract_photo_button.click(
        fn=update_coordinates_from_photo,
        inputs=[file_input, location_input, latitude_input, longitude_input],
        outputs=[
            location_input,
            latitude_input,
            longitude_input,
            location_status_output,
            photo_preview,
        ],
    )
    use_location_search_button.click(
        fn=use_location_search,
        inputs=[location_input, latitude_input, longitude_input],
        outputs=[latitude_input, longitude_input, location_status_output],
    )
    file_input.change(
        fn=update_coordinates_from_photo,
        inputs=[file_input, location_input, latitude_input, longitude_input],
        outputs=[
            location_input,
            latitude_input,
            longitude_input,
            location_status_output,
            photo_preview,
        ],
    )

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
        outputs=[warnings_output, location_status_output, result_output],
    )
    reset_button.click(
        fn=lambda: (
            None,
            *_context_defaults(),
            "Using configured default coordinates." if default_lat is not None and default_lng is not None else "No coordinates resolved yet.",
            "No warnings.",
            "",
            None,
        ),
        inputs=[],
        outputs=[
            file_input,
            observation_date_input,
            observation_time_input,
            location_input,
            latitude_input,
            longitude_input,
            location_status_output,
            warnings_output,
            result_output,
            photo_preview,
        ],
    )


if __name__ == "__main__":
    demo.launch()
