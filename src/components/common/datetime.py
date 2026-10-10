from datetime import datetime


class DateTimeUtil:

    @staticmethod
    def get_current_time() -> float:
        """
        Get the current time in milliseconds.
        """
        dt: datetime = datetime.now()
        return dt.timestamp() * 1000
