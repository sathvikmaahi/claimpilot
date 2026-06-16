import os
from dotenv import load_dotenv
from supabase import create_client


# use the same .env as section_1_agent
load_dotenv("/Users/shubhangvangari/Documents/AI_fellowship/adk-demo/section_1_agent/.env")  


# setting DB keys
url = os.environ["SUPABASE_URL"]          
key = os.environ["SUPABASE_KEY"] 
supabase = create_client(url, key)


# load records from the DB, from 3 different tables, to be used as context for the agents.
def load_context(individual_id: str) -> dict:
    goals = supabase.table("isp_goals") \
        .select("goal_id, category, goal_description") \
        .eq("individual_id", individual_id).eq("active", True).execute().data

    meds = supabase.table("medications") \
        .select("name, dosage, scheduled_time") \
        .eq("individual_id", individual_id).eq("active", True).execute().data

    schedule = supabase.table("schedules") \
        .select("schedule_id, dsp_name, location_name, scheduled_start, scheduled_end, service_code") \
        .eq("individual_id", individual_id).limit(1).single().execute().data

    goals_text = "\n".join(
        f'- goal_id={g["goal_id"]} | category={g["category"]} | "{g["goal_description"]}"'
        for g in goals
    )
    medications = [{"name": m["name"], "time": m["scheduled_time"]} for m in meds]
    shift = {"start": schedule["scheduled_start"], "end": schedule["scheduled_end"]}

    return {
        "goals_text": goals_text,
        "medications": medications,
        "shift": shift,
        "individual_id": individual_id,        
        "schedule_id": schedule["schedule_id"], 
    }


def insert_service_event(row: dict) -> dict:
    """Write one service_events row and return it (including the new event_id)."""
    result = supabase.table("service_events").insert(row).execute()
    return result.data[0]
    
if __name__ == "__main__":
    import json
    JOHN_ID = "63d99f9b-d342-43a3-bf5b-8b70216a9d57"   # John's UUID from your earlier read
    print(json.dumps(load_context(JOHN_ID), indent=2))