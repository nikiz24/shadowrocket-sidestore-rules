#!/usr/bin/env python3
"""Build one updateable Shadowrocket module from Johnshall's release config."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

UPSTREAM = "https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip_ad.conf"
TARGET = ipaddress.ip_network("10.7.0.1/32")
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
    if set(result) != {"General", "Rule", "URL Rewrite", "MITM"}:
        raise ValueError("Upstream sections changed; review before publishing")
    return result


def active_rules(lines):
    return [line.split(" #", 1)[0].strip() for line in lines
            if line.strip() and not line.lstrip().startswith("#")]


def build(text):
    source = sections(text)
    rules = active_rules(source["Rule"])
    if len(rules) < 1000 or rules[-2:] != ["GEOIP,CN,DIRECT", "FINAL,proxy"]:
        raise ValueError("Upstream routing structure changed or download is incomplete")
    for rule in rules:
        if rule.split(",", 1)[0].upper() not in RULE_TYPES:
            raise ValueError("New upstream rule type requires review: " + rule)

    general = {}
    for line in source["General"]:
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            general[key.strip()] = value.strip()
    if "bypass-tun" in general and "tun-excluded-routes" in general:
        raise ValueError("Ambiguous upstream route exclusions")
    excluded = general.pop("bypass-tun", None)
    if excluded is None:
        excluded = general.pop("tun-excluded-routes", None)
    if not excluded:
        raise ValueError("Missing upstream bypass routes")

    networks = []
    for item in excluded.split(","):
        item = item.strip()
        network = ipaddress.ip_network(item)
        if network.version == 4 and TARGET.subnet_of(network):
            networks.extend(str(part) for part in network.address_exclude(TARGET))
        else:
            networks.append(item)
    existing = [ipaddress.ip_network(n.strip()) for n in general.get("tun-included-routes", "").split(",") if n.strip()]
    if not any(n.version == 4 and TARGET.subnet_of(n) for n in existing):
        existing.append(TARGET)
    general["tun-included-routes"] = ",".join(map(str, existing))
    general["tun-excluded-routes"] = ",".join(networks)
    # The module updates; the user's base config and CA remain local.
    general.pop("update-url", None)
    if any(key.lower().startswith("ca-") for key in general):
        raise ValueError("Unexpected certificate data in General")

    upstream_build = re.search(r"^# build time: (.+)$", text, re.M)
    upstream_build = upstream_build[1] if upstream_build else "unknown"
    header = [
        "#!name=CNIP AdBlock + SideStore + MITM",
        "#!desc=Johnshall CNIP/ad-block rules, native 10.7.0.1 loopback, scoped MITM. Generate and trust your CA in a LOCAL base config. Update this module only.",
        "#!homepage=https://github.com/nikiz24/shadowrocket-sidestore-rules",
        "# Original rules: Moshel / Johnshall, CC BY-SA 4.0.",
        "# Source: " + UPSTREAM,
        "# Upstream build: " + upstream_build,
        "# Requires a Shadowrocket build with native 10.7.0.1/32 loopback support.",
        "# This module intentionally contains no CA certificate/private key.",
        "",
        "[General]",
    ]
    body = header + [f"{key} = {value}" for key, value in general.items()]
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
