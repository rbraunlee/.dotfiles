"""Container-only loopback proxy probe; DNS/dial identities are deliberately fake."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import ssl


if not Path("/.dockerenv").is_file() or os.geteuid() != 10001:
    raise SystemExit(1)

spec = importlib.util.spec_from_file_location("proxy", "/opt/routine/bundle/proxy.py")
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def hello(domain):
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    connection = ssl.create_default_context().wrap_bio(incoming, outgoing, server_hostname=domain)
    try:
        connection.do_handshake()
    except ssl.SSLWantReadError:
        pass
    return outgoing.read()


def request(domain):
    return f"CONNECT {domain}:443 HTTP/1.1\r\nHost: {domain}:443\r\n\r\n".encode()


class PeerWriter:
    def __init__(self, writer):
        self.writer = writer

    def get_extra_info(self, name):
        return ("8.8.8.8", 443) if name == "peername" else self.writer.get_extra_info(name)

    def __getattr__(self, name):
        return getattr(self.writer, name)


async def probe():
    assert set(os.listdir("/sys/class/net")) == {"lo"}
    assert os.statvfs("/").f_flag & os.ST_RDONLY
    received, calls, tasks, writers = bytearray(), [], set(), []
    observations = {}

    async def remote(reader, writer):
        writers.append(writer)
        try:
            while data := await reader.read(65536):
                received.extend(data)
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    remote_server = await asyncio.start_server(remote, "127.0.0.1", 0)
    remote_port = remote_server.sockets[0].getsockname()[1]
    addresses = ["8.8.8.8"]

    async def resolver(domain, timeout):
        calls.append("resolve")
        return addresses

    async def connector(address, port):
        assert address == "8.8.8.8" and port == 443
        calls.append("dial")
        reader, writer = await asyncio.open_connection("127.0.0.1", remote_port)
        return reader, PeerWriter(writer)

    component = proxy.Proxy(["example.com"], resolver=resolver, connector=connector,
                            max_connections=1, request_seconds=1, idle_seconds=1, tunnel_seconds=1)

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            await component.handle(reader, writer)
        finally:
            tasks.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0, limit=8192)
    port = server.sockets[0].getsockname()[1]

    async def client(domain):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writers.append(writer)
        writer.write(request(domain))
        await writer.drain()
        return reader, writer

    async def settled():
        async with asyncio.timeout(2):
            while component.active:
                await asyncio.sleep(0.01)

    try:
        reader, writer = await client("evil.test")
        assert b"403 Forbidden" in await reader.read()
        assert not calls
        observations["unapproved_domain_denied_before_dns"] = True
        await settled()

        addresses = ["8.8.8.8", "127.0.0.1"]
        reader, writer = await client("example.com")
        assert b"403 Forbidden" in await reader.read()
        assert calls == ["resolve"]
        observations["mixed_private_dns_denied_before_dial"] = True
        await settled()

        addresses = ["8.8.8.8"]
        reader, writer = await client("example.com")
        assert b"200 Connection Established" in await reader.readuntil(b"\r\n\r\n")
        writer.write(hello("evil.test"))
        await writer.drain()
        assert await reader.read() == b"" and not received
        observations["mismatched_sni_denied_before_payload"] = True
        await settled()

        reader, writer = await client("example.com")
        assert b"200 Connection Established" in await reader.readuntil(b"\r\n\r\n")
        data = hello("example.com")
        writer.write(data)
        await writer.drain()
        assert await reader.readexactly(len(data)) == data
        payload = b"private-proxy-output-canary"
        writer.write(payload)
        await writer.drain()
        assert await reader.readexactly(len(payload)) == payload
        observations["injected_loopback_relay_passed"] = True
        other_reader, other_writer = await asyncio.open_connection("127.0.0.1", port)
        writers.append(other_writer)
        assert await other_reader.read() == b""
        observations["connection_capacity_denied"] = True
        assert await reader.read() == b""
        await settled()
        observations["tunnel_deadline_and_slot_release"] = True

        for address in ("192.0.0.8", "192.88.99.1", "2001:20::1", "3fff::1", "::ffff:8.8.8.8"):
            try:
                proxy.public_address(address)
            except proxy.Denied:
                continue
            raise AssertionError("Special-use address admitted")
        observations["image_python_special_use_denied"] = True
    finally:
        for service in (server, remote_server):
            service.close()
            await service.wait_closed()
        for writer in writers:
            writer.close()
        for task in tuple(tasks):
            task.cancel()
        await asyncio.gather(*tuple(tasks), return_exceptions=True)
        for writer in writers:
            await writer.wait_closed()
    return {"passed": True, "test": "offline-loopback-proxy-component", "observed": observations,
            "injected_dns_and_peer_identity": True, "approved_external_access_qualified": False,
            "host_firewall_qualified": False, "production_baseline_admitted": False}


async def main():
    async with asyncio.timeout(20):
        print(json.dumps(await probe(), sort_keys=True))


asyncio.run(main())
