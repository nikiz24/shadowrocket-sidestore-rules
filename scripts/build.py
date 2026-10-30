#!/usr/bin/env python3
"""Build one updateable Shadowrocket module from Johnshall's release config."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

UPSTREAM = "https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip_ad.conf"
MODULE_NAME = "Shadowrocket-SideStore.sgmodule"
RULE_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6", "GEOIP", "FINAL"}


def sections(text):
    result = {}
    current = None
    for line in text.splitlines():
        match = re.fullmatch(r"\[([^\]]+)\]\s*", line)
        if match:
            current = match[1]
            if current in result:
                raise ValueError("Duplicate section: " + current)
            result[current] = []
        elif current:
            result[current].append(line)
    return result


def active_rules(lines):
    return [line.split(" #", 1)[0].strip() for line in lines
            if line.strip() and not line.lstrip().startswith("#")]


def build(text):
    source = sections(text)
    if set(source) != {"General", "Rule", "URL Rewrite", "MITM"}:
        raise ValueError("Upstream sections changed; review before publishing")
    rules = active_rules(source["Rule"])
    if len(rules) < 1000 or rules[-2:] != ["GEOIP,CN,DIRECT", "FINAL,proxy"]:
        raise ValueError("Upstream routing structure changed or download is incomplete")
    for rule in rules:
        if rule.split(",", 1)[0].upper() not in RULE_TYPES:
            raise ValueError("New upstream rule type requires review: " + rule)

    upstream_build = re.search(r"^# build time: (.+)$", text, re.M)
    upstream_build = upstream_build[1] if upstream_build else "unknown"
    header = [
        "#!name=CNIP AdBlock + SideStore + MITM",
        "#!desc=Johnshall CNIP/ad-block rules and scoped MITM. For SideStore, separately enable Settings > Other > Include Route 10.7.0.1/32 in Shadowrocket and import a valid pairing file in SideStore. Keep your CA in a LOCAL base config.",
        "#!homepage=https://github.com/nikiz24/shadowrocket-sidestore-rules",
        "# Original rules: Moshel / Johnshall, CC BY-SA 4.0.",
        "# Source: " + UPSTREAM,
        "# Upstream build: " + upstream_build,
        "# Requires a Shadowrocket build with native 10.7.0.1/32 loopback support.",
        "# REQUIRED: manually enable Shadowrocket Settings > Other > Include Route 10.7.0.1/32.",
        "# A module cannot supply SideStore pairing credentials or the native loopback switch.",
        "# General/profile options are intentionally omitted: module parsing is not runtime proof.",
        "# This module intentionally contains no CA certificate/private key.",
        "",
    ]
    body = header
    body += ["", "[Rule]", "IP-CIDR,10.7.0.1/32,DIRECT,no-resolve"] + source["Rule"]
    body += ["", "[URL Rewrite]"] + source["URL Rewrite"]
    body += ["", "[MITM]", "enable = true", "hostname = g.cn,*.g.cn,google.cn,*.google.cn", ""]
    module = "\n".join(body)
    if re.search(r"(?mi)^\s*ca-(?:p12|passphrase)\s*=|^\s*update-url\s*=", module):
        raise ValueError("Module must not publish CA data or replace its base config")
    metadata = {
        "source": UPSTREAM,
        "upstream_build": upstream_build,
        "upstream_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "module_sha256": hashlib.sha256(module.encode()).hexdigest(),
        "upstream_rules": len(rules),
        "module_rules": len(rules) + 1,
    }
    return module, metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.source_file:
        text = args.source_file.read_text()
    else:
        with urlopen(Request(UPSTREAM, headers={"User-Agent": "Shadowrocket-SideStore-Rules"}), timeout=60) as response:
            data = response.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024:
            raise ValueError("Upstream exceeded 16 MiB")
        text = data.decode("utf-8")
    module, metadata = build(text)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / MODULE_NAME
    temp = output.with_suffix(".tmp")
    temp.write_text(module)
    temp.replace(output)
    (args.output_dir / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
