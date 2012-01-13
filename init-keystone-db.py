#!/usr/bin/python2
# vim: tabstop=4 shiftwidth=4 softtabstop=4

import sys
import keystone.manage

DEFAULT_FIXTURE = [
    ('tenant', 'add', 'systenant'),
    ('user', 'add', 'admin', 'secrete'),
    ('role', 'add', 'Admin'),
    ('role', 'grant', 'Admin', 'admin'),
# Add Services
    ('service', 'add', 'swift',
        'object-store', 'Swift-compatible service'),
    ('service', 'add', 'nova',
        'compute', 'OpenStack Compute Service'),
    ('service', 'add', 'nova_billing',
        'nova_billing', 'Billing for OpenStack'),
    ('service', 'add', 'glance',
        'image', 'OpenStack Image Service'),
    ('service', 'add', 'identity',
        'identity', 'OpenStack Identity Service'),
]

ENDPOINT_TEMPLATES = {
    "swift": ('http://%host%:8080/v1', 'http://%host%:8080/v1', 'http://%host%:8080/v1', '1', '0'),
    "nova": ('http://%host%:8774/v1.1/%tenant_id%', 'http://%host%:8774/v1.1/%tenant_id%', 'http://%host%:8774/v1.1/%tenant_id%', '1', '0'),
    "glance": ('http://%host%:9292/v1.1', 'http://%host%:9292/v1.1', 'http://%host%:9292/v1.1', '1', '0'),
    "nova_billing": ('http://%host%:8787/', 'http://%host%:8787/', 'http://%host%:8787/', '1', '1'),
    "identity": ('http://%host%:9292/v1.1', 'http://%host%:35357/v2.0', 'http://%host%:5000/v2.0', '1', '1'),
}


def process_safe(cmd):
    try:
        keystone.manage.process(*cmd)
    except Exception, e:
        pass


def main():
    keystone.manage.parse_args(None)
    for cmd in DEFAULT_FIXTURE:
        process_safe(cmd)
    added_services = []
    for arg in sys.argv:
        if "=" not in arg:
            continue
        (service, host) = arg.split("=", 1)
        if service == "magic":
            process_safe(["token", "add", host, 'admin', 'systenant',
                '2015-02-05T00:00'])
            continue
        if service not in ENDPOINT_TEMPLATES:
            print "unknown service %s" % (service)
            continue
        if service in added_services:
            print "duplicated host for service %s" % (service)
            continue
        added_services.append(service)
        cmd = ['endpointTemplates', 'add', 'RegionOne', service] + \
              [word.replace("%host%", host)
               for word in ENDPOINT_TEMPLATES[service]]
        process_safe(cmd)


if __name__ == '__main__':
    main()
