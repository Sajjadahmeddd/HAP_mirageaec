"""The production container's wiring, read from the files that deploy it.

Cheap structural checks on configuration the test client cannot run:
docker-compose.yml, the backend entrypoint and .env.maec.example.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ("CORE_URL", "CORE_PUBLIC_URL", "MAEC_APP_KEY", "MAEC_GATE_SECRET")
LOGIN = ("MAEC_PASSWORD", "MAEC_SECRET_KEY", "MAEC_EMAIL")
DEPLOY_FILES = ("docker-compose.yml", "backend/docker-entrypoint.sh",
                ".env.maec.example", "backend/Dockerfile", "README-docker.md",
                "Makefile")


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _example() -> dict[str, str]:
    pairs = re.findall(r"^([A-Z_]+)=(.*)$", _read(".env.maec.example"), re.M)
    return dict(pairs)


def test_the_example_carries_the_gate_s_settings():
    example = _example()
    for name in SETTINGS:
        assert name in example, name
    assert example["MAEC_APP_KEY"] == "engineering"


def test_core_is_reached_inside_docker_and_linked_to_publicly():
    """The check never leaves the machine; the browser gets the real address."""
    example = _example()
    assert example["CORE_URL"] == "http://maec-core:8000"
    assert example["CORE_PUBLIC_URL"] == "https://auth.mirageaec.com"


def test_the_example_s_secret_is_a_placeholder_the_entrypoint_refuses():
    """Never a real secret in a file — and the placeholder cannot boot."""
    placeholder = _example()["MAEC_GATE_SECRET"]
    assert placeholder == "generate-on-the-server"
    assert f'"{placeholder}"' in _read("backend/docker-entrypoint.sh")


def test_the_entrypoint_refuses_to_start_without_each_setting():
    entrypoint = _read("backend/docker-entrypoint.sh")
    checked = re.search(r"for _name in ([A-Z_ ]+); do", entrypoint).group(1).split()
    assert sorted(checked) == sorted(SETTINGS)


def test_no_deployment_file_still_configures_the_password_login():
    for name in DEPLOY_FILES:
        text = _read(name)
        for variable in LOGIN:
            assert variable not in text, f"{variable} in {name}"


def test_the_entrypoint_is_lf_only():
    """A CRLF shebang fails at container start with 'no such file or directory'."""
    assert b"\r" not in (ROOT / "backend" / "docker-entrypoint.sh").read_bytes()


# ------------------------------------------- running next to the old stack
OLD_SUBNET = "172.30.57.0/24"
# MAEC One Core: maec_core_private, and the shared maec_core_net.
CORE_SUBNETS = ("10.231.0.0/24", "10.231.1.0/24")


def test_the_project_name_is_set_not_derived_from_the_folder():
    assert re.search(r"^name:\s*maec-et\s*$", _read("docker-compose.yml"), re.M)


def test_it_publishes_on_loopback_at_et_port_not_80():
    compose = _read("docker-compose.yml")
    assert '"127.0.0.1:${ET_PORT:-8081}:80"' in compose
    assert '"127.0.0.1:80:80"' not in compose


def test_its_network_is_its_own_and_overlaps_neither_neighbour():
    import ipaddress
    compose = _read("docker-compose.yml")
    assert re.search(r"name:\s*maec_et_net", compose)
    default = re.search(r'subnet:\s*"\$\{ET_NET_SUBNET:-([^}]+)\}"', compose).group(1)
    ours = ipaddress.ip_network(default)
    for neighbour in (OLD_SUBNET, *CORE_SUBNETS):
        assert not ours.overlaps(ipaddress.ip_network(neighbour)), neighbour


def test_it_joins_core_s_network_as_external():
    compose = _read("docker-compose.yml")
    block = compose[compose.index("  maec_core_net:"):]
    assert "external: true" in block
    assert "name: maec_core_net" in block


def test_render_is_no_longer_faked():
    assert "RENDER" not in _read("docker-compose.yml")


def test_its_images_are_not_the_old_stack_s():
    """Found running both stacks: the old stack (and another project named
    "maec") use maec-backend / maec-frontend. Sharing those names retags their
    images, and their next recreate starts this code."""
    images = re.findall(r"^\s*image:\s*(\S+)", _read("docker-compose.yml"), re.M)
    assert sorted(images) == ["maec-et-backend:latest", "maec-et-frontend:latest"]
