from src.components.notifications.constants import NotificationServiceType
def firebase_init(service_type: NotificationServiceType):
    import firebase_admin
    from firebase_admin import credentials
    import json
    from src.core.environment import ENV

    app_name = service_type.value

    # Already initialized
    if app_name in firebase_admin._apps:
        return firebase_admin.get_app(app_name)

    if service_type == NotificationServiceType.MAGLO:
        credentials_json = ENV.FIREBASE_CREDENTIALS_MAGLO_JSON
    
    elif service_type == NotificationServiceType.BABBLER:
        credentials_json = ENV.FIREBASE_CREDENTIALS_BABBLER_JSON
    
    else:
        raise ValueError(f"Unsupported notification service type: {service_type.value}")
    
    if not credentials_json:
        raise ValueError(
            f"Firebase credentials missing for service: {service_type.value}"
        )


    print(f"//////////////// Initializing Firebase for {service_type.value}//////////////////")

    try:
        cred_dict = json.loads(credentials_json)

        cred = credentials.Certificate(cred_dict)
        app = firebase_admin.initialize_app(cred,name=app_name)

        print(
            f"Firebase initialized successfully:"
            f"service={service_type.value},"
            f"project={cred_dict.get('project_id')}"
        )
        return app

    except Exception as e:
        print(f"🔥 Firebase init FAILED for service {service_type.value}")

        raise