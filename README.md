# NASA Gallery Downloader for GitHub Actions

This repo downloads media from NASA gallery pages into folders inside the same repo, then commits the downloaded files.

## Included galleries

Edit `galleries.txt` to add or remove galleries.

```text
https://www.nasa.gov/gallery/lunar-flyby/
https://www.nasa.gov/gallery/journey-to-the-moon/
```

## Output folders

The workflow saves files here:

```text
nasa_downloads/
├── lunar-flyby/
├── journey-to-the-moon/
└── _download_manifest.json
```

## How to run

1. Upload these files to your repo.
2. Go to **Settings → Actions → General**.
3. Under **Workflow permissions**, select **Read and write permissions**.
4. Go to **Actions**.
5. Select **Download NASA Gallery Media**.
6. Click **Run workflow**.
