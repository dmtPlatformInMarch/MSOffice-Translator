class TaskCounter:
    task_dict = {}

    def __init__(self, completed_task_count=0, total_task_count=0):
        self.completed_task_count = completed_task_count
        self.total_task_count = total_task_count

    def __repr__(self):
        return f"TaskCounter(completed_task_count={self.completed_task_count}, total_task_count={self.total_task_count})"