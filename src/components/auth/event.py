from src.components.event_manager import ea_manager


class LoginEAManager(ea_manager.EventActivityManager):

    def pre_event_activity(self, *args, **kwargs):
        pass

    def post_event_activity(self, *args, **kwargs):
        pass


class PermissionEAManager(ea_manager.EventActivityManager):
    """
    PermissionEAManager that handles pre and post tasks related to permissions,
    """

    async def pre_event_activity(self, *args, **kwargs):
        pass

    async def post_event_activity(self, *args, **kwargs):
        pass
