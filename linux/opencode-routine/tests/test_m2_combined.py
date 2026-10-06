"""Real adapter composition over offline transports and fake secret delivery."""
from pathlib import Path
import unittest

import test_m2_checkpoints as checkpoint_tests
import test_m2_network_adapters as network_tests
import test_m2_services_adapter as service_tests
from test_m2_environment import FakeBroker
from routine.contracts import canonical
from routine.environment import Environment
from routine.networking import NetworkAdapter
from routine.network_transport import DockerNetworkTransport, NetworkAdminTransport
from routine.service_adapters import ServiceEnvironmentAdapter


class CombinedDocker(service_tests.FakeDocker):
    def __init__(self, harness, calls):
        super().__init__(calls)
        self.harness = harness

    def compose(self, directory, artifact_id, args, timeout):
        super().compose(directory, artifact_id, args, timeout)
        self.value['HostConfig']['PidsLimit'] = service_tests.service_config(self.documents[-1])['pids_limit']
        self.value['HostConfig']['PublishAllPorts'] = False
        self.value['NetworkSettings']['Ports'] = {}
        for name, endpoint in self.value['NetworkSettings']['Networks'].items():
            owned = next(value for value in self.harness.networks.values() if value['Name'] == name)
            endpoint.update(NetworkID=owned['Id'], EndpointID='7' * 64, LinkLocalIPv6Address='', Links=[])
            owned['Containers'][self.value['Id']] = {'IPv4Address': endpoint['IPAddress'] + '/24', 'IPv6Address': ''}
        self.harness.containers[self.value['Id']] = self.value


class CombinedEnvironmentTests(unittest.TestCase):
    write = checkpoint_tests.EnvironmentCheckpointTests.write
    fixture = checkpoint_tests.EnvironmentCheckpointTests.fixture
    save_manifest = checkpoint_tests.EnvironmentCheckpointTests.save_manifest
    authorize = checkpoint_tests.EnvironmentCheckpointTests.authorize
    prepare_profile = checkpoint_tests.EnvironmentCheckpointTests.prepare_profile
    git = staticmethod(checkpoint_tests.EnvironmentCheckpointTests.git)
    writable_fixture = checkpoint_tests.EnvironmentCheckpointTests.writable_fixture
    setUp = checkpoint_tests.EnvironmentCheckpointTests.setUp

    def run_environment(self, failure=None):
        authorization = self.authorize()
        harness = network_tests.Harness()
        harness.assert_timeout = lambda timeout: self.assertTrue(0 < timeout <= self.profile['resources']['command_seconds'])
        calls = []
        docker = CombinedDocker(harness, calls)
        def request(method, path, body, timeout):
            if path.startswith('/images/'):
                return {'Id': self.profile['runtime']['image'], 'Config': {'Labels': {
                    'routine.bundle-sha256': self.manifest['bundle_sha256'], 'routine.opencode-version': '2.0.22'}}}
            return harness.docker(method, path, body, timeout)
        network = NetworkAdapter(DockerNetworkTransport(request), NetworkAdminTransport(harness.admin),
                                 artifact_root=self.launcher.store.root / 'artifacts', clock=lambda: harness.clock)
        broker = FakeBroker()
        if failure:
            def mutate(operation, value):
                if operation == 'read_component_dns' and value.get('component') == 'service:database':
                    value['pre_docker_dns_dnat'] = False
                return value
            harness.mutate = mutate
        adapter = ServiceEnvironmentAdapter(self.launcher.store.root / 'artifacts', network, docker=docker,
                                             checkpoint=lambda *args: self.fail('host sink must replace placeholder'))
        environment = Environment(adapter=adapter, broker=broker)
        with self.launcher.coordinator('project', 'feature', 'coord') as session:
            session.claim('01', 'run', authorization)
            environment.prepare(session, 'run')
            result = environment.launch(session, 'run')['run']
        return result, harness, docker, calls, broker

    def test_proxy_service_dns_credential_and_durable_checkpoint_composition(self):
        result, harness, docker, calls, broker = self.run_environment()
        self.assertEqual(result['environment']['state'], 'environment-check-passed')
        self.assertTrue(result['environment']['result']['components_stopped'])
        self.assertEqual([value[2] for value in broker.calls], ['service:database'])
        self.assertTrue(all(not any(value) for value in broker.buffers))
        events = result['environment']['adapter_checkpoints']
        names = [value['event'] for value in events]
        self.assertLess(names.index('firewall-verified'), names.index('proxy-start-intent'))
        self.assertLess(names.index('component-network-verified', names.index('service-created')),
                        names.index('service-start-intent'))
        self.assertNotIn('fake-secret-DO-NOT-EXPORT', canonical(events).decode())
        self.assertFalse(docker.value['State']['Running'])
        self.assertTrue(all(not value['State']['Running'] for value in harness.containers.values()))
        self.assertEqual(result['state'], 'claimed')
        self.assertTrue(harness.networks)

    def test_service_dns_readback_denial_stops_owned_consumers_without_starting_service(self):
        result, harness, docker, calls, broker = self.run_environment(failure=True)
        self.assertEqual(result['environment']['state'], 'environment-check-failed')
        self.assertTrue(result['environment']['result']['components_stopped'])
        self.assertNotIn('start:' + 'f' * 64, calls)
        self.assertFalse(docker.value['State']['Running'])
        self.assertTrue(all(not value['State']['Running'] for value in harness.containers.values()))
        self.assertTrue(harness.firewall)
