"""Proxy component contracts/loopback transport; NOT firewall isolation proof."""
import asyncio
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_m1  # Add the shipped launcher library to sys.path.
from routine.compose import worker_assets


spec = importlib.util.spec_from_file_location("routine_proxy", worker_assets() / "proxy.py")
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def request(domain="example.com", extra=b""):
    return (f"CONNECT {domain}:443 HTTP/1.1\r\nHost: {domain}:443\r\n".encode() + extra + b"\r\n")


def hello(domain="example.com", *, extensions=None):
    name = domain.encode()
    names = b"\x00" + len(name).to_bytes(2, "big") + name
    sni = len(names).to_bytes(2, "big") + names
    if extensions is None:
        extensions = [(0, sni)]
    encoded = b"".join(kind.to_bytes(2, "big") + len(value).to_bytes(2, "big") + value
                       for kind, value in extensions)
    body = b"\x03\x03" + b"r" * 32 + b"\x00\x00\x02\x13\x01\x01\x00" + len(encoded).to_bytes(2, "big") + encoded
    handshake = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x01" + len(handshake).to_bytes(2, "big") + handshake


class ProxyPolicyTests(unittest.TestCase):
    def test_exact_domains_not_wildcards_urls_literals_or_local_names(self):
        self.assertEqual(proxy.domain_name("api.example.com"), "api.example.com")
        for value in ("*.example.com", "https://example.com", "127.0.0.1", "8.8.8.8", "[::1]",
                      "EXAMPLE.com", "example.com.", "example.com@evil.test", "bad.local",
                      "bad.internal", "bad.localhost", "-bad.com", "a..com", "é.com", None):
            with self.subTest(value=value), self.assertRaises(proxy.Denied):
                proxy.domain_name(value)

    def test_connect_requires_exact_domain_host_https_port_and_http_version(self):
        self.assertEqual(proxy.connect_target(request(), {"example.com"}), "example.com")
        bad = [request("sub.example.com"), request("evil.test"), request().replace(b":443", b":80"),
               request().replace(b"CONNECT", b"GET"), request().replace(b"HTTP/1.1", b"HTTP/1.0"),
               request().replace(b"Host: example.com", b"Host: evil.test"),
               b"CONNECT example.com:443 HTTP/1.1\r\n\r\n",
               request().replace(b"CONNECT ", b"CONNECT  "), request().replace(b"\r\n", b"\n"),
               request().replace(b"example.com", b"example.com@evil.test")]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(proxy.Denied):
                proxy.connect_target(value, {"example.com"})

    def test_request_smuggling_authentication_and_oversized_headers_are_denied(self):
        for extra in (b"Content-Length: 0\r\n", b"Transfer-Encoding: chunked\r\n",
                      b"Proxy-Authorization: private-secret\r\n", b"Authorization: private-secret\r\n",
                      b"Host: example.com:443\r\n", b"X-Other: value\r\n", b" User-Agent: folded\r\n",
                      b"User-Agent: x\x00x\r\n", b"User-Agent: x\x7fx\r\n", b"User-Agent: \xff\r\n",
                      b"User-Agent: " + b"x" * 8192 + b"\r\n"):
            with self.subTest(extra=extra[:40]), self.assertRaises(proxy.Denied):
                proxy.connect_target(request(extra=extra), {"example.com"})
        self.assertEqual(proxy.connect_target(request(extra=b"User-Agent: fixture\r\nProxy-Connection: Keep-Alive\r\n"),
                                             {"example.com"}), "example.com")

    def test_nonpublic_and_transition_addresses_are_denied(self):
        for value in ("127.0.0.1", "10.0.0.1", "172.17.0.1", "192.168.1.1", "169.254.169.254",
                      "100.64.0.1", "192.0.0.8", "192.0.0.9", "192.0.2.1", "192.88.99.1", "198.18.0.1",
                      "224.0.0.1", "0.0.0.0", "255.255.255.255",
                      "::1", "::", "fe80::1", "fc00::1", "ff02::1", "2001:db8::1", "::ffff:8.8.8.8",
                      "2002:0808:0808::1", "64:ff9b::808:808", "64:ff9b:1::1", "2001::1", "2001:20::1", "3fff::1",
                      "example.com", "fe80::1%eth0", None, 134744072):
            with self.subTest(value=value), self.assertRaises(proxy.Denied):
                proxy.public_address(value)
        self.assertEqual(proxy.public_address("8.8.8.8"), "8.8.8.8")
        self.assertEqual(proxy.public_address("2606:4700:4700::1111"), "2606:4700:4700::1111")

    def test_clienthello_requires_single_visible_sni_without_ech(self):
        self.assertEqual(proxy.client_hello_name(hello()[9:]), "example.com")
        name = b"\x00\x0e\x00\x00\x0bexample.com"
        for extensions in ([], [(0xfe0d, b"encrypted")], [(0, name), (0xfe0d, b"encrypted")],
                           [(0, name), (0, name)], [(0, b"\x00\x00")], [(0, b"\x00\x03\x01\x00\x00")],
                           [(0, name + b"extra")], [(0, name.replace(b"example.com", b"EXAMPLE.COM"))]):
            with self.subTest(extensions=extensions), self.assertRaises(proxy.Denied):
                proxy.client_hello_name(hello(extensions=extensions)[9:])

    def test_every_truncation_of_clienthello_is_denied(self):
        body = hello()[9:]
        for length in range(len(body)):
            with self.subTest(length=length), self.assertRaises(proxy.Denied):
                proxy.client_hello_name(body[:length])

    def test_invalid_resource_limits_and_duplicate_domains_fail_closed(self):
        with self.assertRaises(proxy.Denied):
            proxy.Proxy(["example.com", "example.com"])
        for key in ("max_connections", "request_seconds", "idle_seconds", "tunnel_seconds", "max_tunnel_bytes"):
            for value in (0, -1, True, 1.5, "1"):
                with self.subTest(key=key, value=value), self.assertRaises(proxy.Denied):
                    proxy.Proxy(["example.com"], **{key: value})
        policy = {"allowed_domains": ["example.com"], "max_connections": 1, "request_seconds": 1,
                  "idle_seconds": 1, "tunnel_seconds": 1, "max_tunnel_bytes": 1024}
        invalid = [b"x" * 65537, b"{}", json.dumps({**policy, "allowed_domains": "example.com"}).encode(),
                   json.dumps({**policy, "max_connections": True}).encode(),
                   json.dumps({**policy, "unknown": 1}).encode(),
                   (json.dumps(policy)[:-1] + ', "max_connections": 2}').encode()]
        with tempfile.TemporaryDirectory(prefix="routine-proxy-policy-", dir="/tmp/opencode") as directory:
            path = Path(directory) / "policy.json"
            for data in invalid:
                path.write_bytes(data)
                with patch.object(proxy.asyncio, "start_server") as listener:
                    with self.subTest(data=data[:40]), self.assertRaises(proxy.Denied):
                        asyncio.run(proxy.serve(path))
                    listener.assert_not_called()


class PeerWriter:
    """Injected loopback upstream with a synthetic peer identity; never isolation proof."""
    def __init__(self, writer, peer=("8.8.8.8", 443)):
        self.writer, self.peer = writer, peer

    def get_extra_info(self, name):
        return self.peer if name == "peername" else self.writer.get_extra_info(name)

    def __getattr__(self, name):
        return getattr(self.writer, name)


class ProxyTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connections = []
        self.writers = []
        self.tasks = set()
        self.received = bytearray()
        self.allow_response = asyncio.Event()
        self.remote_done = asyncio.Event()

        async def remote(reader, writer):
            self.writers.append(writer)
            try:
                while data := await reader.read(65536):
                    self.received.extend(data)
                    if self.allow_response.is_set():
                        writer.write(data)
                        await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                self.remote_done.set()

        self.remote_server = await asyncio.start_server(remote, "127.0.0.1", 0)
        self.remote_port = self.remote_server.sockets[0].getsockname()[1]

        async def resolver(domain, timeout):
            self.connections.append(("resolve", domain))
            return ["8.8.8.8"]

        async def connector(address, port):
            self.connections.append(("connect", address, port))
            reader, writer = await asyncio.open_connection("127.0.0.1", self.remote_port)
            return reader, PeerWriter(writer)

        self.component = proxy.Proxy(["example.com"], resolver=resolver, connector=connector,
                                     request_seconds=1, tunnel_seconds=1, idle_seconds=1)
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0, limit=8192)
        self.port = self.server.sockets[0].getsockname()[1]

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            await self.component.handle(reader, writer)
        finally:
            self.tasks.discard(task)

    async def asyncTearDown(self):
        for server in (self.server, self.remote_server):
            server.close()
            await server.wait_closed()
        for writer in self.writers:
            writer.close()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        for writer in self.writers:
            await writer.wait_closed()

    async def client(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self.writers.append(writer)
        return reader, writer

    async def establish(self):
        reader, writer = await self.client()
        writer.write(request())
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2),
                         b"HTTP/1.1 200 Connection Established\r\n\r\n")
        return reader, writer

    async def test_unapproved_domain_never_resolves_or_dials_and_exports_no_request(self):
        reader, writer = await self.client()
        writer.write(request("evil.test", extra=b"User-Agent: private-secret\r\n"))
        data = await asyncio.wait_for(reader.read(), 2)
        self.assertIn(b"403 Forbidden", data)
        self.assertNotIn(b"private-secret", data)
        self.assertNotIn(b"evil.test", data)
        self.assertEqual(self.connections, [])

    async def test_mixed_public_private_dns_answers_never_dial(self):
        async def resolver(domain, timeout):
            return ["8.8.8.8", "10.0.0.1"]
        self.component.resolver = resolver
        reader, writer = await self.client()
        writer.write(request())
        self.assertIn(b"403 Forbidden", await asyncio.wait_for(reader.read(), 2))
        self.assertEqual(self.connections, [])

    async def test_dns_rebinding_on_next_connection_is_revalidated(self):
        resolutions = [0]
        async def resolver(domain, timeout):
            resolutions[0] += 1
            return ["8.8.8.8"] if resolutions[0] == 1 else ["127.0.0.1"]
        self.component.resolver = resolver
        reader, writer = await self.establish()
        writer.close()
        await writer.wait_closed()
        reader, writer = await self.client()
        writer.write(request())
        self.assertIn(b"403 Forbidden", await asyncio.wait_for(reader.read(), 2))
        self.assertEqual(self.connections, [("connect", "8.8.8.8", 443)])

    async def test_invalid_empty_or_excessive_dns_answers_cannot_dial(self):
        for addresses in ([], {}, ["8.8.8.8"] * 65, ["example.com"], [None]):
            async def resolver(domain, timeout):
                return addresses
            self.component.resolver = resolver
            reader, writer = await self.client()
            writer.write(request())
            self.assertIn(b"403 Forbidden", await asyncio.wait_for(reader.read(), 2))
        self.assertEqual(self.connections, [])

    async def test_numeric_pinning_avoids_second_resolution_and_preserves_transport(self):
        self.allow_response.set()
        reader, writer = await self.establish()
        data = hello()
        writer.write(data)
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(len(data)), 2), data)
        writer.write(b"private-payload")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(15), 2), b"private-payload")
        self.assertEqual(self.connections, [("resolve", "example.com"), ("connect", "8.8.8.8", 443)])

    async def test_wrong_sni_plaintext_and_ech_never_reach_upstream(self):
        for data in (hello("evil.test"), b"GET / HTTP/1.1\r\nHost: evil.test\r\n\r\n",
                     hello(extensions=[(0xfe0d, b"encrypted")])):
            with self.subTest(data=data[:20]):
                reader, writer = await self.establish()
                writer.write(data)
                await writer.drain()
                self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        self.assertEqual(self.received, b"")

    async def test_fragmented_tls_records_are_parsed_without_mutating_bytes(self):
        self.allow_response.set()
        reader, writer = await self.establish()
        handshake = hello()[5:]
        chunks = (handshake[:2], handshake[2:7], handshake[7:])
        data = b"".join(b"\x16\x03\x03" + len(chunk).to_bytes(2, "big") + chunk for chunk in chunks)
        writer.write(data)
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(len(data)), 2), data)

    async def test_peer_identity_mismatch_is_denied(self):
        async def connector(address, port):
            return await asyncio.open_connection("127.0.0.1", self.remote_port)
        self.component.connector = connector
        reader, writer = await self.client()
        writer.write(request())
        self.assertIn(b"403 Forbidden", await asyncio.wait_for(reader.read(), 2))
        self.assertEqual(self.received, b"")

    async def test_request_deadline_closes_slow_header_and_releases_slot(self):
        reader, writer = await self.client()
        writer.write(b"CONNECT")
        self.assertIn(b"403 Forbidden", await asyncio.wait_for(reader.read(), 2))
        await asyncio.sleep(0.01)
        self.assertEqual(self.component.active, 0)

    async def test_request_deadline_includes_resolver_and_connector(self):
        for phase in ("resolver", "connector"):
            async def hanging(*args):
                await asyncio.sleep(10)
            original = getattr(self.component, phase)
            setattr(self.component, phase, hanging)
            reader, writer = await self.client()
            writer.write(request())
            self.assertIn(b"403 Forbidden", await asyncio.wait_for(reader.read(), 2))
            setattr(self.component, phase, original)

    async def test_missing_hello_is_bounded_and_no_bytes_reach_remote(self):
        reader, writer = await self.establish()
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        self.assertEqual(self.received, b"")

    async def test_tunnel_total_lifetime_bounds_continuous_activity(self):
        self.allow_response.set()
        reader, writer = await self.establish()
        writer.write(hello())
        self.assertEqual(await reader.readexactly(len(hello())), hello())
        for _ in range(4):
            writer.write(b"x")
            self.assertEqual(await reader.readexactly(1), b"x")
            await asyncio.sleep(0.2)
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")

    async def test_byte_budget_counts_both_directions_and_initial_hello(self):
        self.component.max_tunnel_bytes = len(hello()) - 1
        reader, writer = await self.establish()
        writer.write(hello())
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        self.assertEqual(self.received, b"")
        self.allow_response.set()
        self.component.max_tunnel_bytes = len(hello()) * 2 + 1
        reader, writer = await self.establish()
        writer.write(hello())
        self.assertEqual(await reader.readexactly(len(hello())), hello())
        writer.write(b"xx")
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")

    async def test_capacity_rejects_without_waiting_or_resolving(self):
        self.component.max_connections = 1
        reader, writer = await self.establish()
        other_reader, other_writer = await self.client()
        self.assertEqual(await asyncio.wait_for(other_reader.read(), 0.5), b"")
        self.assertEqual(len(self.connections), 2)
        self.assertEqual(self.component.active, 1)

    async def test_client_disconnect_closes_remote_and_releases_slot(self):
        reader, writer = await self.establish()
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(self.remote_done.wait(), 1)
        await asyncio.sleep(0.01)
        self.assertEqual(self.component.active, 0)

    async def test_real_python_tls_clienthello_is_supported(self):
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        context = ssl.create_default_context()
        tls = context.wrap_bio(incoming, outgoing, server_hostname="example.com")
        with self.assertRaises(ssl.SSLWantReadError):
            tls.do_handshake()
        data = outgoing.read()
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        raw, name = await proxy.read_client_hello(reader)
        self.assertEqual(name, "example.com")
        self.assertEqual(raw, data)

    async def test_record_and_handshake_bounds_are_enforced(self):
        for data in (b"\x17\x03\x03\x00\x01x", b"\x16\x03\x03\xff\xff",
                     b"\x16\x03\x03\x00\x00", b"\x16\x03\x03\x00\x04\x01\xff\xff\xff",
                     b"\x16\x03\x03\x00\x04\x02\x00\x00\x01"):
            reader = asyncio.StreamReader()
            reader.feed_data(data)
            reader.feed_eof()
            with self.subTest(data=data), self.assertRaises(proxy.Denied):
                await proxy.read_client_hello(reader)

    async def test_oversized_header_is_closed_without_resolution(self):
        reader, writer = await self.client()
        writer.write(request(extra=b"User-Agent: " + b"x" * 9000 + b"\r\n"))
        self.assertIn(b"403 Forbidden", await asyncio.wait_for(reader.read(), 2))
        self.assertEqual(self.connections, [])

    async def test_tunnel_idle_timeout_cancels_both_pumps(self):
        self.allow_response.set()
        self.component.tunnel_seconds = 10
        reader, writer = await self.establish()
        writer.write(hello())
        await reader.readexactly(len(hello()))
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        await asyncio.wait_for(self.remote_done.wait(), 1)
        await asyncio.sleep(0.01)
        self.assertEqual(self.component.active, 0)

    async def test_cancelled_handler_closes_upstream_and_releases_slot(self):
        reader, writer = await self.establish()
        task = next(iter(self.tasks))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(self.component.active, 0)
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        await asyncio.wait_for(self.remote_done.wait(), 1)

    async def test_dns_child_timeout_kills_and_reaps_owned_process(self):
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(10)",
                                                       stdout=asyncio.subprocess.PIPE)
        with patch.object(proxy.asyncio, "create_subprocess_exec", return_value=process):
            with self.assertRaises(TimeoutError):
                await proxy.resolve("example.com", 0.05)
        self.assertIsNotNone(process.returncode)

    async def test_dns_child_output_is_bounded_validated_and_no_raw_stderr(self):
        for output in ("x" * 8193, "[]", "{}", "not-json", json.dumps(["8.8.8.8"] * 65)):
            process = await asyncio.create_subprocess_exec(sys.executable, "-c", f"print({output!r})",
                                                           stdout=asyncio.subprocess.PIPE)
            with patch.object(proxy.asyncio, "create_subprocess_exec", return_value=process):
                with self.subTest(output=output[:40]), self.assertRaises(proxy.Denied):
                    await proxy.resolve("example.com", 1)
            self.assertIsNotNone(process.returncode)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import sys,time;sys.stdout.write('[\"8.8.');sys.stdout.flush();time.sleep(.01);print('8.8\"]')",
            stdout=asyncio.subprocess.PIPE)
        with patch.object(proxy.asyncio, "create_subprocess_exec", return_value=process) as spawn:
            self.assertEqual(await proxy.resolve("example.com", 1), ["8.8.8.8"])
            self.assertIn("-I", spawn.call_args.args)
            self.assertEqual(spawn.call_args.kwargs["stderr"], asyncio.subprocess.DEVNULL)
        self.assertEqual(process.returncode, 0)


if __name__ == "__main__":
    unittest.main()
