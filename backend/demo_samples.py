"""Fixed public demo import choices. Client input never names a server path."""

from pathlib import Path

DIRECTORY = Path(__file__).with_name("demo-upload-samples")
SAMPLES = {
    "pdf-1": ("04_2025-05-12_Annual_Visit_Note_Mary.pdf", "application/pdf"),
    "pdf-2": ("05_2025-05-12_Lab_Report_Mary.pdf", "application/pdf"),
    "image-1": ("sample-3.jpg", "image/jpeg"),
}


def catalog():
    return [dict(id=key, filename=name, media=media, available=(DIRECTORY / name).is_file())
            for key, (name, media) in SAMPLES.items()]


def source(sample_id):
    name, media = SAMPLES[sample_id]
    return name, media, (DIRECTORY / name).read_bytes()
