"""RQ worker entrypoint — runs the background job queue.

The web process enqueues jobs (SMS/WhatsApp, webhook dispatch, export
generation, PAYT dunning) into the 'smartgarbage' queue on Redis; this worker
process executes them so request handlers never block on external calls.

Usage (when REDIS_URL is configured, e.g. in Docker/Fly):
    python worker.py
"""
import os


def main():
    url = os.environ.get('REDIS_URL')
    if not url:
        print("REDIS_URL not set — background worker disabled (jobs run inline).")
        return
    from redis import Redis
    from rq import Worker, Queue, Connection

    conn = Redis.from_url(url)
    with Connection(conn):
        worker = Worker([Queue('smartgarbage')])
        worker.work()


if __name__ == '__main__':
    main()
