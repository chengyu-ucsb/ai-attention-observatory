"""Fetch and verify the two official Qwen shards used for issue composition."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import time


REVISION = "bb5d59e06d9551d752d08b292a50eb208b07ab1f"
BASE_URL = f"https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/{REVISION}"
# Exact sizes and SHA-256 digests from the Git LFS pointers at this revision.
SHARDS = (
    ("qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf", 3993201344,
     "dfce12e3862a5283ccfb88221b48480e58745165de856439950d0f22590580db"),
    ("qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf", 689872288,
     "539cf93f78e887edea1c04e2d7d8cdaca9d01dae9c9025bcb8accbe29df3d72a"),
)
ATTEMPTS = 4
TRANSIENT_CURL_ERRORS = {5, 6, 7, 16, 18, 28, 35, 52, 55, 56, 92}
TRANSIENT_HTTP = {"408", "429", "500", "502", "503", "504"}


def verified(path, size, digest):
    if not path.exists() or path.stat().st_size != size:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest


def fetch_shard(directory, name, size, digest, deadline):
    target = directory / name
    partial = directory / (name + ".part")
    if verified(target, size, digest):
        return
    target.unlink(missing_ok=True)
    if verified(partial, size, digest):
        partial.replace(target)
        return

    for attempt in range(1, ATTEMPTS + 1):
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            break
        if partial.exists() and partial.stat().st_size >= size:
            partial.unlink()
        offset = partial.stat().st_size if partial.exists() else 0
        print(f"{name}: attempt {attempt}, starting at {offset}/{size} bytes", flush=True)
        result = subprocess.run(
            ["curl", "--fail", "--location", "--silent", "--show-error", "--http1.1",
             "--connect-timeout", "15", "--max-time", str(remaining),
             "--speed-limit", "1024", "--speed-time", "30", "--continue-at", "-",
             "--output", str(partial), "--write-out", "%{http_code}", f"{BASE_URL}/{name}"],
            stdout=subprocess.PIPE, text=True, check=False,
        )
        if verified(partial, size, digest):
            partial.replace(target)
            return
        status = result.stdout.strip()
        print(f"{name}: curl={result.returncode}, HTTP={status}, shard still unverified", flush=True)
        if offset and (result.returncode == 33 or status == "416"):
            # Some download endpoints do not accept Range. Retry from byte zero.
            partial.unlink(missing_ok=True)
        elif (result.returncode not in TRANSIENT_CURL_ERRORS and result.returncode != 0
              and status not in TRANSIENT_HTTP):
            raise RuntimeError(f"{name}: download failed (curl {result.returncode}, HTTP {status})")
        if attempt < ATTEMPTS:
            time.sleep(min(2 ** attempt, max(0, deadline - time.monotonic())))
    raise RuntimeError(f"{name}: could not verify shard within the download budget")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    directory = parser.parse_args().directory
    directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 15 * 60
    for name, size, digest in SHARDS:
        fetch_shard(directory, name, size, digest, deadline)


if __name__ == "__main__":
    main()
