#!/usr/bin/env python3
"""Build a complete Shadowrocket profile and a legacy compatibility module."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

UPSTREAM = "https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip_ad.conf"
MODULE_NAME = "Shadowrocket-SideStore.sgmodule"
CONFIG_NAME = "Shadowrocket-SideStore.conf"
CONFIG_URL = "https://raw.githubusercontent.com/nikiz24/shadowrocket-sidestore-rules/main/" + CONFIG_NAME
TUN_INCLUDED_ROUTES = "0.0.0.0/0,10.7.0.1/32"
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


def build(text, *, full_config=False):
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
        "#!desc=Johnshall rules with IPv4 default/SideStore routes and scoped MITM. Separately enable native Include Route 10.7.0.1/32 and configure SideStore pairing. Keep your CA in a local extended profile when updating remotely.",
        "#!homepage=https://github.com/nikiz24/shadowrocket-sidestore-rules",
        "# Original rules: Moshel / Johnshall, CC BY-SA 4.0.",
        "# Source: " + UPSTREAM,
        "# Upstream build: " + upstream_build,
        "# Requires a Shadowrocket build with native 10.7.0.1/32 loopback support.",
        "# REQUIRED: manually enable Shadowrocket Settings > Other > Include Route 10.7.0.1/32.",
        "# Neither profiles nor modules can supply pairing credentials or the native loopback switch.",
        "# General includes IPv4 default and SideStore routes; it does not enable native loopback.",
        "# This file intentionally contains no CA certificate/private key or proxy credentials.",
        "# For MITM with remote updates, extend this profile locally and keep the CA there.",
        "",
    ]
    body = header
    body += ["", "[General]"]
    if full_config:
        body += [
            "ipv6 = false",
            "prefer-ipv6 = false",
            "bypass-system = true",
            "skip-proxy = 192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,localhost,*.local",
            "dns-server = system",
            "update-url = " + CONFIG_URL,
        ]
    body += ["tun-included-routes = " + TUN_INCLUDED_ROUTES]
    body += ["", "[Rule]", "IP-CIDR,10.7.0.1/32,DIRECT,no-resolve"] + source["Rule"]
    body += ["", "[URL Rewrite]"] + source["URL Rewrite"]
    body += ["", "[MITM]", "enable = true", "hostname = g.cn,*.g.cn,google.cn,*.google.cn", ""]
    module = "\n".join(body)
    if re.search(r"(?mi)^\s*ca-(?:p12|passphrase)\s*=", module):
        raise ValueError("Published files must not contain CA data")
    if not full_config and re.search(r"(?mi)^\s*update-url\s*=", module):
        raise ValueError("Module must not replace its base config")
    metadata = {
        "source": UPSTREAM,
        "upstream_build": upstream_build,
        "upstream_sha256": hashlib.sha256(text.encode()).hexdigest(),
        ("config_sha256" if full_config else "module_sha256"): hashlib.sha256(module.encode()).hexdigest(),
        "upstream_rules": len(rules),
        ("config_rules" if full_config else "module_rules"): len(rules) + 1,
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
    config, config_metadata = build(text, full_config=True)
    metadata.update(config_metadata)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in [(CONFIG_NAME, config), (MODULE_NAME, module)]:
        output = args.output_dir / name
        temp = output.with_suffix(".tmp")
        temp.write_text(content)
        temp.replace(output)
    (args.output_dir / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
