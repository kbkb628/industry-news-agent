from apscheduler.schedulers.background import BackgroundScheduler


def build_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler()
