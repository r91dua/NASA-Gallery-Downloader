# NASA Lunar Flyby Image Downloader

This repo downloads the NASA Lunar Flyby `~large.jpg` images into a folder in the same repo.

## Files

```text
.
├── nasa_ids.txt
├── download_from_ids.py
└── .github/workflows/download-nasa-images.yml
```

## How to run in GitHub

1. Upload these files to a GitHub repo.
2. Go to **Settings → Actions → General**.
3. Under **Workflow permissions**, allow **Read and write permissions** if needed.
4. Go to **Actions**.
5. Open **Download NASA Lunar Flyby Images**.
6. Click **Run workflow**.
7. When it finishes, the repo should contain:

```text
lunar_flyby_images/
```

## Run locally

```bash
pip install requests
python download_from_ids.py
```
