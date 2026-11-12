"""Prepare the CISPRO Pages artifact from the public Drive folder."""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DRIVE_API = "https://www.googleapis.com/drive/v3/files"
FOLDER_ID = "1ddACHmm_DnvhKKp4_qzUmEtW58gEXdFW"
DOCUMENTS = {
    "1": ("application/pdf", "cispro-cv.pdf", b"%PDF-"),
    "2": ("image/png", "cispro-experiencia-offshore.png", b"\x89PNG\r\n\x1a\n"),
    "5": ("application/pdf", "cispro-catalogo.pdf", b"%PDF-"),
}


def open_drive(api_key, suffix="", **params):
    query = urlencode(params)
    request = Request(f"{DRIVE_API}{suffix}?{query}", headers={"X-Goog-Api-Key": api_key})
    return urlopen(request, timeout=60)


def list_folder(api_key):
    params = {
        "q": f"'{FOLDER_ID}' in parents and trashed = false",
        "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType)",
        "pageSize": 100,
    }
    while True:
        with open_drive(api_key, **params) as response:
            page = json.load(response)
        if page.get("incompleteSearch"):
            raise ValueError("Drive devolvió una lista incompleta.")
        yield from page.get("files", [])
        if not page.get("nextPageToken"):
            return
        params["pageToken"] = page["nextPageToken"]


def match_documents(files):
    matches = {number: [] for number in DOCUMENTS}
    for file in files:
        prefix = re.match(r"^(\d+)\.", file["name"])
        if prefix and prefix[1] in matches:
            matches[prefix[1]].append(file)

    selected = {}
    for number, items in matches.items():
        mime_type, _, _ = DOCUMENTS[number]
        if len(items) != 1:
            raise ValueError(f"Drive debe tener un solo archivo con el prefijo {number}. Se encontraron {len(items)}.")
        file = items[0]
        if file["mimeType"] != mime_type:
            raise ValueError(f"El archivo {number}. debe tener el formato {mime_type}.")
        selected[number] = file["id"]
    return selected


def download_documents(api_key, selected, folder):
    for number, file_id in selected.items():
        _, filename, signature = DOCUMENTS[number]
        with open_drive(api_key, f"/{file_id}", alt="media") as response:
            if response.read(len(signature)) != signature:
                raise ValueError(f"El archivo {number}. no tiene la firma del formato esperado.")
            with (folder / filename).open("wb") as output:
                output.write(signature)
                shutil.copyfileobj(response, output)
        print(f"Documento {number}. preparado: {filename}")


def build(api_key, source, destination):
    selected = match_documents(list_folder(api_key))
    with TemporaryDirectory() as temporary:
        downloaded = Path(temporary)
        download_documents(api_key, selected, downloaded)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "index.html", destination)
        for name in ("Logo_horizontal_1.jpg", "LOGO V CISPRO.png", "CNAME", "favicon.ico"):
            asset = source / name
            if asset.is_file():
                shutil.copy2(asset, destination)
        for asset in downloaded.iterdir():
            shutil.copy2(asset, destination)


if __name__ == "__main__":
    key = os.environ.get("DRIVE_API_KEY")
    if not key:
        sys.exit("Configura el secreto DRIVE_API_KEY antes de publicar con GitHub Actions.")
    try:
        build(key, Path.cwd(), Path(sys.argv[1]))
    except HTTPError as error:
        sys.exit(f"Google Drive respondió con HTTP {error.code}. Revisa la API y los permisos de la carpeta.")
    except (OSError, URLError, ValueError) as error:
        sys.exit(f"No se pudo preparar la publicación: {error}")
