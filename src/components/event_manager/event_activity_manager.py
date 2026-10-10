from abc import ABC, abstractmethod


class EventActivityManager(ABC):

    @abstractmethod
    def pre_event_activity(self, *args, **kwargs):
        pass

    @abstractmethod
    def post_event_activity(self, *args, **kwargs):
        pass
