import datetime


class Logger:
    class Colors:
        HEADER = "\033[95m"
        OKBLUE = "\033[94m"
        OKGREEN = "\033[92m"
        WARNING = "\033[93m"
        FAIL = "\033[91m"
        ENDC = "\033[0m"
        BOLD = "\033[1m"
        UNDERLINE = "\033[4m"

    @staticmethod
    def _get_log_prefix(ctx: str = None):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d : %H:%M:%S.%f")[:-3]
        if ctx is None:
            prefix = f"\r{timestamp} | "
        else:
            prefix = f"\r{timestamp} - {ctx} | "
        return prefix

    @staticmethod
    def log_info(str: str, ctx: str = None):
        print(
            f"{Logger.Colors.OKGREEN}{Logger._get_log_prefix(ctx)}{str}{Logger.Colors.ENDC}"
        )

    @staticmethod
    def log_warn(str: str, ctx: str = None):
        print(
            f"{Logger.Colors.WARNING}{Logger._get_log_prefix(ctx)}{str}{Logger.Colors.ENDC}"
        )

    @staticmethod
    def log_error(str: str, ctx: str = None):
        print(
            f"{Logger.Colors.FAIL}{Logger._get_log_prefix(ctx)}{str}{Logger.Colors.ENDC}"
        )
