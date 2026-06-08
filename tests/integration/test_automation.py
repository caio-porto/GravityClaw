import pytest
import pytest_asyncio
import asyncio
from unittest.mock import MagicMock, patch
from src.agent.loop import AgentLoop
from src.automation.manager import AutomationManager
import os

@pytest.fixture
def agent_mock():
    agent = MagicMock(spec=AgentLoop)
    agent.process_input.return_value = "Task completed."
    return agent

@pytest.fixture
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def automation_manager(agent_mock, event_loop):
    # Use memory database for testing
    os.environ['AUTOMATION_DB_PATH'] = 'memory' # Use memory jobstore directly
    manager = AutomationManager(agent_mock)

    # Start the manager within the explicitly provided event loop fixture context
    manager.start()
    yield manager
    manager.stop()

@pytest.mark.asyncio
async def test_add_and_get_cron_job(automation_manager):
    job_id = automation_manager.add_cron_job("0 8 * * *", "Check emails")

    jobs = automation_manager.get_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["args"][0] == "Check emails"
    assert jobs[0]["args"][1] == "System Cron"

@pytest.mark.asyncio
async def test_remove_job(automation_manager):
    job_id = automation_manager.add_cron_job("0 8 * * *", "Check emails")
    automation_manager.remove_job(job_id)

    jobs = automation_manager.get_jobs()
    assert len(jobs) == 0

@pytest.mark.asyncio
async def test_execute_task(automation_manager, agent_mock):
    response = await automation_manager.execute_task("Do something")
    assert response == "Task completed."
    agent_mock.process_input.assert_called_once_with("Do something", "System Cron")

@pytest.mark.asyncio
async def test_invalid_cron_expression(automation_manager):
    with pytest.raises(ValueError, match="Invalid cron expression format"):
        automation_manager.add_cron_job("invalid format", "Check emails")

@pytest.mark.asyncio
async def test_execute_task_exception(automation_manager, agent_mock):
    # Setup the mock to raise an exception when process_input is called
    error_message = "Test exception"
    agent_mock.process_input.side_effect = Exception(error_message)

    # Call execute_task
    response = await automation_manager.execute_task("Do something risky")

    # Verify the exception was caught and its string representation was returned
    assert response == error_message

    # Verify process_input was still called with expected arguments
    agent_mock.process_input.assert_called_once_with("Do something risky", "System Cron")
