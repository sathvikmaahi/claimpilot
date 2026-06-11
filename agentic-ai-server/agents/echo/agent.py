"""Sample ADK root agent — keep agent logic here, not in the HTTP layer."""

from google.adk import Agent

# ADK convention: root_agent is the entry point for this agent package.
root_agent = Agent(
    name="echo_agent",
    model="gemini-2.0-flash",
    instruction=(
        "You are a helpful echo assistant. Repeat the user's message clearly "
        "and add one brief, friendly sentence confirming you received it."
    ),
)
