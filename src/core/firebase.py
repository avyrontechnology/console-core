"""Push init retired (retired product apps decommissioned).

firebase_init is kept as a stub so FCMChannel imports keep working;
it always raises and FCMChannel degrades to "ERROR" (logged) instead
of crashing the worker. Delete this module + FCMChannel + factory
entry when push is reintroduced for a live product.
"""


def firebase_init(service_type):
    import firebase_admin

    # Already initialized only (no new inits: apps decommissioned).
    if service_type.value in firebase_admin._apps:
        return firebase_admin.get_app(service_type.value)
    raise ValueError(f"Unsupported notification service type: {service_type.value}")
