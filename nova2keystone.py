#!/usr/bin/python2
# vim: tabstop=4 shiftwidth=4 softtabstop=4

import sys

from nova.db.sqlalchemy.session import get_session, get_engine

import keystone.manage

import keystone.backends.api as db_api
import keystone.backends.models as db_models


class IdByName(object):
    users = {}
    tenants = {}
    roles = {}


id_by_name = IdByName()
nova_engine = None
user_tenants = {}
STD_ROLES = ("Admin", "Member", "KeystoneServiceAdmin",
             "projectmanager",
             "cloudadmin", "itsec", "sysadmin", "netadmin", "developer")


def log_create_if_exists(msg, created):
    print "%s\t%s" % ("N" if created else " ", msg)


def add_user_tenant(user_id, tenant_id, tenant_name):
    try:
        user_tenants[user_id][tenant_id] = tenant_name
    except KeyError:
        user_tenants[user_id] = {tenant_id: tenant_name}


def add_user(name, password, tenant=None):
    obj = db_models.User()
    obj.name = name
    obj.password = password
    obj.enabled = True
    obj.tenant_id = tenant
    return db_api.USER.create(obj)


def add_tenant(name, desc=None):
    obj = db_models.Tenant()
    obj.name = name
    obj.desc = desc
    obj.enabled = True
    return db_api.TENANT.create(obj)


def add_credentials(user, type, key, secrete, tenant=None):
    obj = db_models.Token()
    obj.user_id = user
    obj.type = type
    obj.key = key
    obj.secret = secrete
    obj.tenant_id = tenant
    return db_api.CREDENTIALS.create(obj)


def add_role(name):
    obj = db_models.Role()
    obj.name = name
    role = db_api.ROLE.create(obj)
    return role


def grant_role(role, user, tenant=None):
    """Grants `role` to `user` (and optionally, on `tenant`)"""
    obj = db_models.UserRoleAssociation()
    obj.role_id = role
    obj.user_id = user
    obj.tenant_id = tenant

    return db_api.USER.user_role_add(obj)


def add_endpoint(tenant, endpoint_template):
    obj = db_models.Endpoints()
    obj.tenant_id = tenant
    obj.endpoint_template_id = endpoint_template
    db_api.ENDPOINT_TEMPLATE.endpoint_add(obj)
    return obj


def add_endpoint_safe(tenant, endpoint_template):
    try:
        add_endpoint(tenant, endpoint_template)
        log_create_if_exists("%s - %s" % (tenant, endpoint_template), True)
    except:
        log_create_if_exists("%s - %s" % (tenant, endpoint_template), False)


def grant_role_safe(role, user, tenant=None):
    try:
        grant_role(role, user, tenant)
        log_create_if_exists("%s for %s on %s" % (role, user, tenant), True)
    except:
        log_create_if_exists("%s for %s on %s" % (role, user, tenant), False)


def make_existing_dict(rslt):
    return dict([(o.name, o.id) for o in rslt])


def add_if_not_exists(existing, name, ctor, **kwargs):
    if name in existing:
        log_create_if_exists(name, False)
        return
    log_create_if_exists(name, True)
    id = ctor(name, **kwargs).id
    existing[name] = id


def connect_db():
    keystone.manage.parse_args(None)

    from nova import flags
    from nova import utils
    FLAGS = flags.FLAGS
    utils.default_flagfile()
    flags.FLAGS(sys.argv)
    global nova_engine
    nova_engine = get_engine()


def migrate_users():
    print "Migrating users"
    id_by_name.users = make_existing_dict(db_api.USER.get_all())

    rslt = nova_engine.execute("select id, access_key from users")
    for row in rslt:
        add_if_not_exists(id_by_name.users, row[0], add_user, password=row[1])


def migrate_tenants():
    print "Migrating tenants"
    id_by_name.tenants = make_existing_dict(db_api.TENANT.get_all())

    rslt = nova_engine.execute("select id, description from projects")
    for row in rslt:
        add_if_not_exists(id_by_name.tenants, row[0], add_tenant, desc=row[1])


def migrate_roles():
    print "Migrating roles"
    id_by_name.roles = make_existing_dict(db_api.ROLE.get_all())

    for name in STD_ROLES:
        add_if_not_exists(id_by_name.roles, name, add_role)

    ADMIN_ROLE_ID = id_by_name.roles["Admin"]
    MEMBER_ROLE_ID = id_by_name.roles["Member"]
    PROJECT_MANAGER_ID = id_by_name.roles["projectmanager"]
    rslt = nova_engine.execute("select project_manager, id from projects")
    for row in rslt:
        grant_role_safe(
                PROJECT_MANAGER_ID,
                id_by_name.users[row[0]],
                id_by_name.tenants[row[1]])

    rslt = nova_engine.execute(
            "select role, user_id, project_id from user_project_role_association")
    for row in rslt:
        add_if_not_exists(id_by_name.roles, row[0], add_role)
        grant_role_safe(
                id_by_name.roles[row[0]],
                id_by_name.users[row[1]],
                id_by_name.tenants[row[2]])
        add_user_tenant(
            id_by_name.users[row[1]],
            id_by_name.tenants[row[2]],
            row[2])

    rslt = nova_engine.execute(
            "select user_id, project_id from user_project_association")
    for row in rslt:
        grant_role_safe(
                MEMBER_ROLE_ID,
                id_by_name.users[row[0]],
                id_by_name.tenants[row[1]])
        add_user_tenant(
            id_by_name.users[row[0]],
            id_by_name.tenants[row[1]],
            row[1])

    rslt = nova_engine.execute(
            "select id from users where is_admin=1")
    for row in rslt:
        grant_role_safe(
                ADMIN_ROLE_ID,
                id_by_name.users[row[0]],
                None)


def migrate_credentials():
    print "Migrating credentials"
    rslt = nova_engine.execute("select id, access_key, secret_key from users")
    for row in rslt:
        user_id = id_by_name.users[row[0]]
        print "credentials for user_id=%s" % user_id
        for tenant_id, tenant_name in user_tenants.get(user_id, {}).iteritems():
            print "\ttenant %s" % (tenant_name)
            add_credentials(
                user_id,
                "EC2",
                "%s:%s" % (row[1], tenant_name),
                row[2],
                tenant_id)
        add_credentials(
            user_id,
            "EC2",
            row[1],
            row[2],
            None)


def setup_endpoints():
    print "Setting up endpoints"
    endpoint_templates = db_api.ENDPOINT_TEMPLATE.get_all()
    for template in endpoint_templates:
        if template.is_global:
            print "\tskipping global template %s" % template.id
            continue
        for tenant_id in id_by_name.tenants.values():
            add_endpoint_safe(tenant_id, template.id)


def main():
    connect_db()
    migrate_users()
    migrate_tenants()

    setup_endpoints()
    migrate_roles()
    migrate_credentials()


if __name__ == "__main__":
    main()
