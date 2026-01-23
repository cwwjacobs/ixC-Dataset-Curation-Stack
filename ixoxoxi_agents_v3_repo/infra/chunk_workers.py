import concurrent.futures

class ChunkWorkerPool:
    """
    Executes chunk jobs in parallel using threads or processes.
    """
    def __init__(self, max_workers=4):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn, *args, **kwargs):
        return self.executor.submit(fn, *args, **kwargs)

    def map(self, fn, jobs):
        return list(self.executor.map(fn, jobs))

    def shutdown(self):
        self.executor.shutdown(wait=True)
