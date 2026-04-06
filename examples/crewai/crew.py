from typing import List
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

import asyncio
from volnix.adapters.crewai import crewai_tools

from dotenv import load_dotenv
load_dotenv()  # loads .env from current directory or parent

URL = "http://localhost:8080"
_loop = asyncio.get_event_loop()

# Each agent gets tools bound to its identity from the agent YAML.
# Permissions and budgets are enforced per-agent by Volnix.
ANALYST_TOOLS = _loop.run_until_complete(crewai_tools(URL, actor_id="financial-analyst"))
RESEARCH_TOOLS = _loop.run_until_complete(crewai_tools(URL, actor_id="research-analyst"))
ADVISOR_TOOLS = _loop.run_until_complete(crewai_tools(URL, actor_id="investment-advisor"))


@CrewBase
class StockAnalysisCrew:
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    @agent
    def financial_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['financial_analyst'],
            verbose=True,
            tools=ANALYST_TOOLS,
            llm="gpt-4.1-mini",
        )

    @agent
    def research_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['research_analyst'],
            verbose=True,
            tools=RESEARCH_TOOLS,
            llm="gpt-4.1-mini",
        )

    @agent
    def financial_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['financial_analyst'],
            verbose=True,
            tools=ANALYST_TOOLS,
            llm="gpt-4.1-mini",
        )

    @agent
    def investment_advisor_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['investment_advisor'],
            verbose=True,
            tools=ADVISOR_TOOLS,
            llm="gpt-4.1-mini",
        )

    @task
    def research(self) -> Task:
        return Task(
            config=self.tasks_config['research'],
            agent=self.research_analyst_agent(),
        )

    @task
    def financial_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['financial_analysis'],
            agent=self.financial_analyst_agent(),
        )

    @task
    def filings_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['filings_analysis'],
            agent=self.financial_analyst_agent(),
        )

    @task
    def recommend(self) -> Task:
        return Task(
            config=self.tasks_config['recommend'],
            agent=self.investment_advisor_agent(),
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Stock Analysis"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
