import pytest
from task.queue import TaskQueue
from task.scheduler import CronScheduler
from shared.models import Task


class TestTaskQueue:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, tmp_path):
        queue = TaskQueue(db_path=str(tmp_path / "test.db"))
        await queue.initialize()

        task = Task(type="publish", input={"platform": "wechat"})
        await queue.enqueue(task)

        dequeued = await queue.dequeue()
        assert dequeued is not None
        assert dequeued.id == task.id
        assert dequeued.status == "running"

        await queue.close()

    @pytest.mark.asyncio
    async def test_ack(self, tmp_path):
        queue = TaskQueue(db_path=str(tmp_path / "test.db"))
        await queue.initialize()

        task = Task(type="test")
        await queue.enqueue(task)
        await queue.dequeue()
        await queue.ack(task.id, output={"status": "ok"})

        t = await queue.get_task(task.id)
        assert t.status == "completed"
        assert t.output == {"status": "ok"}

        await queue.close()

    @pytest.mark.asyncio
    async def test_nack_retry(self, tmp_path):
        queue = TaskQueue(db_path=str(tmp_path / "test.db"))
        await queue.initialize()

        task = Task(type="test")
        await queue.enqueue(task)
        await queue.dequeue()

        await queue.nack(task.id, "error occurred")
        t = await queue.get_task(task.id)
        assert t.retry_count == 1
        assert t.status == "pending"

        await queue.close()

    @pytest.mark.asyncio
    async def test_nack_fail_after_max_retries(self, tmp_path):
        queue = TaskQueue(db_path=str(tmp_path / "test.db"))
        await queue.initialize()

        task = Task(type="test", max_retries=1)
        await queue.enqueue(task)

        for _ in range(2):
            await queue.dequeue()
            await queue.nack(task.id, "fail")

        t = await queue.get_task(task.id)
        assert t.status == "failed"

        await queue.close()


class TestCronScheduler:
    def test_parse_cron(self):
        from task.scheduler import CronScheduler
        scheduler = CronScheduler(None)
        fields = scheduler._parse_cron("0 17 * * *")
        assert 0 in fields[0]
        assert 17 in fields[1]

    def test_parse_every_minute(self):
        from task.scheduler import CronScheduler
        scheduler = CronScheduler(None)
        fields = scheduler._parse_cron("* * * * *")
        assert len(fields[0]) == 60