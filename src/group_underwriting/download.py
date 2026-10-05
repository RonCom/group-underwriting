"""Download and unzip DE-SynPUF Sample 1 into data/real/01_raw.

Usage: uv run python -m group_underwriting.download [--sample 1] [--dest data/real/01_raw]

The URLs follow the layout CMS has used for these files; they were not reachable from the
environment this project was built in, so check them against the CMS DE-SynPUF page
(Sample 1) if a download fails and pass the right ones with --url.
"""

from __future__ import annotations

import argparse
import io
import logging
import urllib.request
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

CMS = "https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs/Downloads"
FILES = "https://downloads.cms.gov/files"


def urls(sample: int) -> list[str]:
    s = sample
    return [
        f"{CMS}/DE1_0_2008_Beneficiary_Summary_File_Sample_{s}.zip",
        f"{CMS}/DE1_0_2009_Beneficiary_Summary_File_Sample_{s}.zip",
        f"{CMS}/DE1_0_2010_Beneficiary_Summary_File_Sample_{s}.zip",
        f"{CMS}/DE1_0_2008_to_2010_Inpatient_Claims_Sample_{s}.zip",
        f"{CMS}/DE1_0_2008_to_2010_Outpatient_Claims_Sample_{s}.zip",
        f"{FILES}/DE1_0_2008_to_2010_Carrier_Claims_Sample_{s}A.zip",
        f"{FILES}/DE1_0_2008_to_2010_Carrier_Claims_Sample_{s}B.zip",
        f"{FILES}/DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_{s}.zip",
    ]


def fetch(url: str, dest: Path) -> None:
    log.info("Downloading %s", url)
    with urllib.request.urlopen(url, timeout=600) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.lower().endswith(".csv"):
                (dest / Path(name).name).write_bytes(z.read(name))
                log.info("  -> %s", dest / Path(name).name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", type=int, default=1)
    ap.add_argument("--dest", default="data/real/01_raw")
    ap.add_argument("--url", action="append", help="download these URLs instead of the defaults")
    args = ap.parse_args()
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    for url in args.url or urls(args.sample):
        fetch(url, dest)


if __name__ == "__main__":
    main()
