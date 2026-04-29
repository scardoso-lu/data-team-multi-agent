from agents.data_analyst.app import DataAnalystAgent
from agents.data_architect.app import DataArchitectAgent
from agents.data_engineer.app import DataEngineerAgent
from agents.data_steward.app import DataStewardAgent
from agents.qa_engineer.app import QAEngineerAgent


AGENT_CLASSES = {
    "data_architect": DataArchitectAgent,
    "data_engineer": DataEngineerAgent,
    "qa_engineer": QAEngineerAgent,
    "data_analyst": DataAnalystAgent,
    "data_steward": DataStewardAgent,
}


def agent_names():
    return tuple(AGENT_CLASSES)


def build_agent(agent_name):
    try:
        agent_cls = AGENT_CLASSES[agent_name]
    except KeyError as exc:
        valid = ", ".join(agent_names())
        raise ValueError(f"Unknown agent '{agent_name}'. Valid agents: {valid}") from exc
    return agent_cls()
