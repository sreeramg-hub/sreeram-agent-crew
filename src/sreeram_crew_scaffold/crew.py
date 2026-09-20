import os
import pathlib

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent

# Explicitly use Anthropic so the crew never falls back to OpenAI
_LLM = LLM(
    model=os.getenv("MODEL", "anthropic/claude-sonnet-4-6"),
    api_key=os.getenv("ANTHROPIC_API_KEY"),
)

from sreeram_crew_scaffold.tools.youtube_tool import YoutubeNewUploadsTool


@CrewBase
class SreeramCrewScaffold():
    """Gold & Silver video-links crew (the tech half of the digest is plain Python in tech/)"""

    agents: list[BaseAgent]
    tasks: list[Task]

    # ── Agents ────────────────────────────────────────────────────────────────

    @agent
    def gold_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['gold_agent'],
            tools=[YoutubeNewUploadsTool()],
            llm=_LLM,
            verbose=True,
        )

    @agent
    def silver_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['silver_agent'],
            tools=[YoutubeNewUploadsTool()],
            llm=_LLM,
            verbose=True,
        )

    @agent
    def final_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['final_agent'],
            llm=_LLM,
            verbose=True,
        )

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @task
    def gold_research_task(self) -> Task:
        return Task(
            config=self.tasks_config['gold_research_task'],
        )

    @task
    def silver_research_task(self) -> Task:
        return Task(
            config=self.tasks_config['silver_research_task'],
        )

    @task
    def compose_digest_task(self) -> Task:
        return Task(
            config=self.tasks_config['compose_digest_task'],
            context=[self.gold_research_task(), self.silver_research_task()],
            output_file='metals.html',
        )

    # ── Crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            task_callback=self._strip_code_fences,
        )

    @staticmethod
    def _strip_code_fences(task_output) -> None:
        """Remove markdown code fences from metals.html if the LLM added them."""
        digest = pathlib.Path("metals.html")
        if not digest.exists():
            return
        content = digest.read_text(encoding="utf-8").strip()
        if content.startswith("```"):
            lines = content.splitlines()
            # Drop first line (```html or ```) and last line (```)
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            digest.write_text("\n".join(lines), encoding="utf-8")
