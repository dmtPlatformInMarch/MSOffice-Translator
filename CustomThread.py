class CustomThread:
    def __init__(self, thread, stop_event):
        self.thread = thread
        self.stop_event = stop_event

    def stop(self):
        self.stop_event.set()
        self.thread.join()
