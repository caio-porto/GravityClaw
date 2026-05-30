import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import os
import asyncio
from src.agent.loop import AgentLoop

logger = logging.getLogger(__name__)

class AutomationManager:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

        # Use an SQLite database to store jobs persistently
        db_path = os.environ.get('AUTOMATION_DB_PATH', 'sqlite:///jobs.sqlite')

        if db_path == 'memory':
            from apscheduler.jobstores.memory import MemoryJobStore
            jobstores = {
                'default': MemoryJobStore()
            }
        else:
            jobstores = {
                'default': SQLAlchemyJobStore(url=db_path)
            }

        self.scheduler = AsyncIOScheduler(jobstores=jobstores)

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Automation scheduler started.")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Automation scheduler stopped.")

    async def execute_task(self, prompt: str, user_id: str = "System Cron"):
        logger.info(f"Executing scheduled task: {prompt}")
        try:
            # Process the input directly using the agent's process_input function
            response = await asyncio.to_thread(self.agent.process_input, prompt, user_id)
            logger.info(f"Scheduled task response: {response}")
            return response
        except Exception as e:
            logger.error(f"Failed to execute scheduled task: {e}")
            return str(e)

    def add_cron_job(self, cron_expr: str, prompt: str, job_id: str = None, user_id: str = "System Cron"):
        """Adds a new cron job.
        cron_expr: e.g. '0 8 * * *' (minute hour day month day_of_week)
        """
        # Parse standard cron expression: min hour day month dow
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError("Invalid cron expression format. Expected 5 parts (min hour day month dow)")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4]
        )

        job = self.scheduler.add_job(
            self.execute_task,
            trigger=trigger,
            args=[prompt, user_id],
            id=job_id,
            replace_existing=True
        )
        logger.info(f"Added cron job {job.id} with expression '{cron_expr}'")
        return job.id

    def remove_job(self, job_id: str):
        self.scheduler.remove_job(job_id)
        logger.info(f"Removed job {job_id}")

    def get_jobs(self):
        return [{"id": job.id, "next_run_time": job.next_run_time, "trigger": str(job.trigger), "args": job.args} for job in self.scheduler.get_jobs()]
