import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("builder", Path(__file__).resolve().parents[1] / "scripts/build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def fixture():
    rules = [f"DOMAIN-SUFFIX,ad{i}.example,Reject" for i in range(1000)]
    return "\n".join([
        "# build time: UTC 2026-10-30 00:00:00", "[General]",
        "bypass-tun = 10.0.0.0/8,192.168.0.0/16,fc00::/7",
        "skip-proxy = 10.0.0.0/8", "dns-server = system", "[Rule]",
        "DOMAIN-SUFFIX,example.org,Proxy", *rules,
        "GEOIP,CN,DIRECT", "FINAL,proxy", "[URL Rewrite]",
        r"^https?://google\.cn https://www.google.com 302",
        "[MITM]", "hostname = *.googlevideo.com",
        "ca-p12 = EXAMPLE_UPSTREAM_KEY_MUST_NOT_BE_PUBLISHED",
        "ca-passphrase = EXAMPLE_UPSTREAM_PASSWORD",
    ])


class BuildTest(unittest.TestCase):
    def test_all_source_rules_and_rewrites_preserved(self):
        text = fixture()
        module, metadata = builder.build(text)
        old, new = builder.sections(text), builder.sections(module)
        self.assertEqual(builder.active_rules(new["Rule"])[1:], builder.active_rules(old["Rule"]))
        self.assertEqual(builder.active_rules(new["Rule"])[0], "IP-CIDR,10.7.0.1/32,DIRECT,no-resolve")
        self.assertEqual([s for s in new["URL Rewrite"] if s.strip()], [s for s in old["URL Rewrite"] if s.strip()])
        self.assertEqual(metadata["module_rules"], 1004)

    def test_module_includes_default_route_and_still_requires_native_loopback(self):
        module, _ = builder.build(fixture())
        output = builder.sections(module)
        self.assertEqual(set(output), {"General", "Rule", "URL Rewrite", "MITM"})
        self.assertEqual(builder.active_rules(output["General"]), [
            "tun-included-routes = 0.0.0.0/0,10.7.0.1/32",
        ])
        self.assertNotIn("tun-excluded-routes =", module)
        self.assertIn("manually enable Shadowrocket Settings > Other > Include Route 10.7.0.1/32", module)

    def test_upstream_tunnel_settings_cannot_remove_default_route(self):
        text = fixture().replace("dns-server = system", "\n".join([
            "dns-server = system", "tun-included-routes = 10.7.0.1/32",
            "compatibility-mode = 5", "tun-excluded-routes = 0.0.0.0/0",
        ]))
        module, _ = builder.build(text)
        self.assertEqual(builder.active_rules(builder.sections(module)["General"]), [
            "tun-included-routes = 0.0.0.0/0,10.7.0.1/32",
        ])
        self.assertNotIn("compatibility-mode =", module)

    def test_module_leaves_certificate_and_base_config_local(self):
        module, _ = builder.build(fixture().replace("dns-server = system", "dns-server = system\nupdate-url = https://example.org/base.conf"))
        self.assertNotIn("ca-p12 =", module)
        self.assertNotIn("ca-passphrase =", module)
        self.assertNotIn("EXAMPLE_UPSTREAM", module)
        self.assertNotIn("update-url =", module)
        self.assertNotIn("dns-server =", module)
        self.assertIn("enable = true", module)
        self.assertIn("hostname = g.cn,*.g.cn,google.cn,*.google.cn", module)

    def test_incomplete_or_changed_upstream_does_not_publish(self):
        for text in ["<html>Service unavailable</html>", fixture().replace("FINAL,proxy", "FINAL,DIRECT"), fixture() + "\n[Script]\ncron = unexpected"]:
            with self.subTest(text=text[-80:]), self.assertRaises(ValueError):
                builder.build(text)

    def test_unsupported_rule_requires_review(self):
        with self.assertRaises(ValueError):
            builder.build(fixture().replace("DOMAIN-SUFFIX,example.org,Proxy", "SCRIPT,unexpected,PROXY"))

    def test_complete_profile_has_own_update_url_and_all_rules(self):
        text = fixture().replace("dns-server = system", "\n".join([
            "dns-server = https://untrusted.example/dns-query",
            "update-url = https://untrusted.example/profile.conf",
            "include = private.conf", "tun-included-routes = 10.7.0.1/32",
            "compatibility-mode = 5",
        ]))
        config, metadata = builder.build(text, full_config=True)
        output = builder.sections(config)
        self.assertEqual(set(output), {"General", "Rule", "URL Rewrite", "MITM"})
        self.assertIn("update-url = " + builder.CONFIG_URL, output["General"])
        self.assertIn("tun-included-routes = 0.0.0.0/0,10.7.0.1/32", output["General"])
        self.assertIn("dns-server = system", output["General"])
        self.assertNotIn("untrusted.example", config)
        self.assertNotIn("private.conf", config)
        self.assertNotIn("EXAMPLE_UPSTREAM", config)
        self.assertNotIn("ca-p12 =", config)
        self.assertNotIn("ca-passphrase =", config)
        self.assertNotIn("compatibility-mode =", config)
        self.assertNotIn(".sgmodule", config)
        source = builder.sections(text)
        self.assertEqual(builder.active_rules(output["Rule"])[1:], builder.active_rules(source["Rule"]))
        self.assertEqual(builder.active_rules(output["URL Rewrite"]), builder.active_rules(source["URL Rewrite"]))
        self.assertEqual(metadata["config_rules"], 1004)

    def test_cli_writes_both_outputs_and_keeps_them_on_bad_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.conf"
            output = root / "published"
            source.write_text(fixture())
            command = [sys.executable, str(Path(builder.__file__)),
                       "--source-file", str(source), "--output-dir", str(output)]
            subprocess.run(command, check=True, capture_output=True)
            saved = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(set(saved), {builder.CONFIG_NAME, builder.MODULE_NAME, "build-info.json"})
            import hashlib
            import json
            info = json.loads(saved["build-info.json"])
            self.assertEqual(info["config_sha256"], hashlib.sha256(saved[builder.CONFIG_NAME]).hexdigest())
            self.assertEqual(info["module_sha256"], hashlib.sha256(saved[builder.MODULE_NAME]).hexdigest())
            source.write_text("<html>Upstream unavailable</html>")
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(saved, {p.name: p.read_bytes() for p in output.iterdir()})


if __name__ == "__main__":
    unittest.main()
