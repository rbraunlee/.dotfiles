"""Container-only HTTPS CONNECT component; not a substitute for host firewall rules.

No request/payload/error logs or credentials. Production dispatch remains disabled
until the per-environment proxy network and host firewall are qualified together.
"""
import asyncio
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys


class Denied(Exception):
    pass


# Conservative special-use exclusions, consistent on host 3.14 and image 3.11.
# Never rely on a newer interpreter's IANA classification alone.
SPECIAL_V4 = tuple(ipaddress.ip_network(value) for value in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
    "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4"))
SPECIAL_V6 = tuple(ipaddress.ip_network(value) for value in ("2001::/23", "2002::/16", "3fff::/20"))


def domain_name(value):
    if (not isinstance(value, str) or len(value) > 253 or
            not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+", value) or
            value.endswith((".localhost", ".local", ".internal"))):
        raise Denied()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise Denied()


def public_address(value):
    if not isinstance(value, str) or "%" in value:
        raise Denied()
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise Denied() from None
    # Admit native global unicast IPv6 only: no mapped, NAT64 or transition routes.
    if (not address.is_global or address.is_multicast or address.is_reserved or
            (address.version == 4 and any(address in network for network in SPECIAL_V4)) or
            (address.version == 6 and (address not in ipaddress.ip_network("2000::/3") or
                                      any(address in network for network in SPECIAL_V6)))):
        raise Denied()
    return str(address)


def connect_target(header, allowed_domains):
    try:
        lines = header.decode("ascii").split("\r\n")
    except UnicodeError:
        raise Denied() from None
    if len(header) > 8192 or len(lines) < 4 or lines[-2:] != ["", ""]:
        raise Denied()
    request = lines[0].split(" ")
    if len(request) != 3 or request[0] != "CONNECT" or request[2] != "HTTP/1.1":
        raise Denied()
    authority = request[1]
    if not authority.endswith(":443"):
        raise Denied()
    domain = domain_name(authority[:-4])
    if domain not in allowed_domains:
        raise Denied()
    headers = {}
    for line in lines[1:-2]:
        name, separator, value = line.partition(":")
        if (not separator or not re.fullmatch(r"[A-Za-z-]+", name) or
                any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise Denied()
        name = name.lower()
        if name in headers or name not in ("host", "user-agent", "proxy-connection", "connection"):
            raise Denied()
        headers[name] = value.strip(" ")
    if headers.get("host") != authority:
        raise Denied()
    # Bodies, proxy authentication and ambiguous framing are not accepted.
    return domain


def client_hello_name(data):
    """Parse only a complete, bounded TLS ClientHello; require one clear SNI name."""
    offset = 0

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(data):
            raise Denied()
        result = data[offset:offset + size]
        offset += size
        return result

    def number(size):
        return int.from_bytes(take(size), "big")

    if take(2) != b"\x03\x03":
        raise Denied()
    take(32)
    session_size = number(1)
    if session_size > 32:
        raise Denied()
    take(session_size)
    cipher_size = number(2)
    if cipher_size < 2 or cipher_size % 2:
        raise Denied()
    take(cipher_size)
    if take(number(1)) != b"\x00":
        raise Denied()
    extension_size = number(2)
    if extension_size != len(data) - offset:
        raise Denied()
    seen, name = set(), None
    while offset < len(data):
        kind, size = number(2), number(2)
        value = take(size)
        if kind in seen or kind == 0xfe0d:  # ECH obscures the intended TLS hostname.
            raise Denied()
        seen.add(kind)
        if kind == 0:
            if (len(value) < 6 or int.from_bytes(value[:2], "big") != len(value) - 2 or
                    value[2] != 0 or int.from_bytes(value[3:5], "big") != len(value) - 5):
                raise Denied()
            try:
                name = domain_name(value[5:].decode("ascii"))
            except UnicodeError:
                raise Denied() from None
    if name is None:
        raise Denied()
    return name


async def read_client_hello(reader):
    raw, handshake = bytearray(), bytearray()
    for _ in range(16):
        header = await reader.readexactly(5)
        size = int.from_bytes(header[3:], "big")
        if header[0] != 22 or header[1] != 3 or header[2] not in (1, 2, 3) or not 0 < size <= 16384:
            raise Denied()
        body = await reader.readexactly(size)
        raw.extend(header + body)
        handshake.extend(body)
        if len(raw) > 65536 or handshake[0] != 1:
            raise Denied()
        if len(handshake) >= 4:
            length = int.from_bytes(handshake[1:4], "big")
            if not 1 <= length <= 60000:
                raise Denied()
            if len(handshake) >= length + 4:
                return bytes(raw), client_hello_name(bytes(handshake[4:4 + length]))
    raise Denied()


async def resolve(domain, timeout):
    # A killable/reaped child avoids immortal libc DNS calls or accumulating
    # executor threads after DNS timeouts. At most one child per admitted client.
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--resolve", domain,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(timeout):
            data = bytearray()
            while chunk := await process.stdout.read(8193 - len(data)):
                data.extend(chunk)
                if len(data) > 8192:
                    raise Denied()
            if await process.wait() != 0:
                raise Denied()
            try:
                rows = json.loads(data)
            except (ValueError, UnicodeError):
                raise Denied() from None
            if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
                raise Denied()
            return rows
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()


class Proxy:
    def __init__(self, allowed_domains, *, resolver=resolve, connector=asyncio.open_connection,
                 max_connections=16, request_seconds=10, idle_seconds=30,
                 tunnel_seconds=300, max_tunnel_bytes=64 * 1024 * 1024):
        domains = [domain_name(value) for value in allowed_domains]
        if len(set(domains)) != len(domains):
            raise Denied()
        self.allowed_domains = frozenset(domains)
        for value in (max_connections, request_seconds, idle_seconds, tunnel_seconds, max_tunnel_bytes):
            if type(value) is not int or value <= 0:
                raise Denied()
        self.max_connections = max_connections
        self.request_seconds = request_seconds
        self.idle_seconds = idle_seconds
        self.tunnel_seconds = tunnel_seconds
        self.max_tunnel_bytes = max_tunnel_bytes
        self.resolver, self.connector = resolver, connector
        self.active = 0

    async def upstream(self, domain):
        addresses = await self.resolver(domain, self.request_seconds)
        if not isinstance(addresses, list) or not 1 <= len(addresses) <= 64:
            raise Denied()
        # Validate the entire DNS answer before dialing ANY address. No fallback
        # from a public answer to a LAN answer, nor a second hostname resolution.
        validated = list(dict.fromkeys(public_address(value) for value in addresses))
        for address in validated:
            try:
                reader, writer = await self.connector(address, 443)
            except OSError:
                continue
            peer = writer.get_extra_info("peername")
            try:
                if not peer or public_address(peer[0]) != address or peer[1] != 443:
                    raise Denied()
            except Denied:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), 1)
                raise Denied()
            return reader, writer
        raise Denied()

    async def relay(self, client_reader, client_writer, upstream_reader, upstream_writer, initial):
        transferred = len(initial)
        if transferred > self.max_tunnel_bytes:
            raise Denied()
        upstream_writer.write(initial)
        await asyncio.wait_for(upstream_writer.drain(), self.idle_seconds)

        async def pump(reader, writer):
            nonlocal transferred
            while True:
                data = await asyncio.wait_for(reader.read(65536), self.idle_seconds)
                if not data:
                    if writer.can_write_eof():
                        writer.write_eof()
                        await asyncio.wait_for(writer.drain(), self.idle_seconds)
                    return
                transferred += len(data)
                if transferred > self.max_tunnel_bytes:
                    raise Denied()
                writer.write(data)
                await asyncio.wait_for(writer.drain(), self.idle_seconds)

        # TaskGroup cancels/reaps the sibling on failure; half-close still permits
        # the remote response. Total tunnel time bounds a silent half-closed peer.
        async with asyncio.TaskGroup() as group:
            group.create_task(pump(client_reader, upstream_writer))
            group.create_task(pump(upstream_reader, client_writer))

    async def handle(self, reader, writer):
        if self.active >= self.max_connections:
            # Refuse synchronously rather than accumulate waiting handler tasks.
            writer.close()
            return
        upstream_writer = None
        admitted, established = False, False
        try:
            self.active += 1
            admitted = True
            async with asyncio.timeout(self.request_seconds):
                header = await reader.readuntil(b"\r\n\r\n")
                domain = connect_target(header, self.allowed_domains)
                upstream_reader, upstream_writer = await self.upstream(domain)
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                established = True
                initial, name = await read_client_hello(reader)
                if name != domain:
                    raise Denied()
            async with asyncio.timeout(self.tunnel_seconds):
                await self.relay(reader, writer, upstream_reader, upstream_writer, initial)
        except (Denied, OSError, ValueError, TimeoutError, asyncio.IncompleteReadError,
                asyncio.LimitOverrunError, ExceptionGroup):
            if not established:
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
                try:
                    await asyncio.wait_for(writer.drain(), 1)
                except (OSError, TimeoutError):
                    pass
        finally:
            for stream in (upstream_writer, writer):
                if stream is not None:
                    stream.close()
                    try:
                        await asyncio.wait_for(stream.wait_closed(), 1)
                    except (OSError, TimeoutError):
                        pass
            if admitted:
                self.active -= 1


async def serve(policy_path):
    with Path(policy_path).open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise Denied()
    def unique_pairs(items):
        value = {}
        for key, entry in items:
            if key in value:
                raise Denied()
            value[key] = entry
        return value

    policy = json.loads(data, object_pairs_hook=unique_pairs)
    names = {"allowed_domains", "max_connections", "request_seconds", "idle_seconds",
             "tunnel_seconds", "max_tunnel_bytes"}
    if not isinstance(policy, dict) or set(policy) != names or not isinstance(policy["allowed_domains"], list):
        raise Denied()
    proxy = Proxy(**policy)
    server = await asyncio.start_server(proxy.handle, "0.0.0.0", 3128, limit=8192, backlog=16)
    async with server:
        await server.serve_forever()


def main():
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--resolve":
            domain = domain_name(sys.argv[2])
            addresses = sorted({row[4][0] for row in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)})
            if not 1 <= len(addresses) <= 64:
                raise Denied()
            print(json.dumps(addresses))
        elif len(sys.argv) == 2 and Path("/.dockerenv").is_file():
            asyncio.run(serve(sys.argv[1]))
        else:
            raise Denied()
    except (Denied, OSError, ValueError):
        # Never expose request bytes, domain queries, exception details or payload.
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
