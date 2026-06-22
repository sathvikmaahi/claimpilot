import asyncio


from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.narrative_extractor.agent import root_agent  # the narrative extractor you already built

load_dotenv()  # loads GOOGLE_API_KEY from the .env in this folder

AUDIO_PATH = "/Users/shubhangvangari/Documents/AI_fellowship/adk-demo/my_agent/section1_gap_detection.m4a"
AUDIO_MIME = "audio/mp4"  

APP_NAME = "claimpilot_a2"
USER_ID = "dsp_maria"


async def main():
    
    """Reads a local audio file, sends it to an AI agent, and prints the 
    analyzed results with 'gaps' highlighted.

    How it works:
      1. Starts a new session with the AI agent.
      2. Opens and reads the specified audio file.
      3. Sends the audio to the agent and waits for it to finish processing.
      4. Takes the final answer from the agent, extracts the text as data,
         runs it through a 'gap detector' function, and prints the final 
         JSON results to the screen.

    """
    
    
    # start a new session with the agent
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    # open and read the audio file into raw bytes
    with open(AUDIO_PATH, "rb") as f:
        audio_bytes = f.read()

    #  send the audio to the agent and wait for it to finish processing
    message = types.Content(
        role="user",
        parts=[types.Part.from_bytes(data=audio_bytes, mime_type=AUDIO_MIME)],
    )

    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content:
            import json
            from agents.narrative_extractor.detect_gaps  import detect_gaps
            extraction = json.loads(event.content.parts[0].text)
            extraction["gaps_detected"] = detect_gaps(extraction)
            print(json.dumps(extraction, indent=2))


if __name__ == "__main__":
    asyncio.run(main())