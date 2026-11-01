# Demo upload samples

Place the three user-provided fictional test documents here:

- `04_2025-05-12_Annual_Visit_Note_Mary.pdf`
- `05_2025-05-12_Lab_Report_Mary.pdf`
- `sample-3.jpg`

`IMG_4922.HEIC` preserves the supplied Apple original (3024 × 4032 pixels).
`sample-3.jpg` is its full-resolution JPEG conversion at quality 95, without chroma subsampling.
Only the JPEG is exposed by the fixed demo picker; the original is not a selectable import.

The picker always exposes these three fixed IDs. Missing files are shown as unavailable.
The API accepts only those IDs, never filenames or paths supplied by a browser.
Importing a choice stores its original bytes and runs the normal live AI workflow.
These files must not be added to the prepared demo-results manifest.
