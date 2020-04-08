import time
from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)


def handle_broker_timeout(callable_func, args=(), kwargs={}, timeout=None, retry_delay=0.1):
    timeout_time = time.time() + timeout if timeout else None
    tries = 0
    while True:
        tries += 1
        try:
            return_value = callable_func(*args, **kwargs)
        except Exception as e:
            # need to handle different timeout exceptions from different brokers
            if type(e).__name__ != "TimeoutError":
                raise
            if not timeout:
                logger.warning(f'Backend was not reachable and timed out...'
                               f'retrying in {retry_delay}s')
                time.sleep(retry_delay)
            else:
                current_time = time.time()
                if current_time < timeout_time:
                    logger.warning(f'Backend was not reachable and timed out...'
                                   f'retrying in {retry_delay}s for a max of {timeout}s '
                                   f'({timeout_time-current_time:.2f}s remaining)')
                    time.sleep(retry_delay)
                else:
                    logger.error(f'Reached max timeout of {timeout}s...giving up!')
                    try:
                        send_task_instrumentation_event(instrumentation_label='handle_broker_timeout-failure',
                                                        broker_timeout_tries=tries)
                    finally:
                        raise
        else:
            try:
                if tries > 1:
                    send_task_instrumentation_event(instrumentation_label='handle_broker_timeout-success',
                                                    broker_timeout_tries=tries)
            finally:
                return return_value


def send_task_instrumentation_event(event_type='task-instrumentation', **fields):
    from celery import current_task
    if not current_task:
        return
    try:
        import traceback
        current_task.send_event(event_type, instrumentation_event_stack=traceback.format_stack(), **fields)
    except Exception as e:
        logger.debug(e, exc_info=True)
        logger.debug('Could not instrument')