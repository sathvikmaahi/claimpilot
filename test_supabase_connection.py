import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("/Users/shubhangvangari/Documents/AI_fellowship/adk-demo/section_1_agent/.env")  

url = os.environ["SUPABASE_URL"]          # read the project URL out of the environment
key = os.environ["SUPABASE_KEY"]          # read the secret key out of the environment

supabase = create_client(url, key)        # open a connection (this is "adding the API")

# Ask the DB: every row from the individuals table.
response = supabase.table("individuals").select("*").execute()

print(response.data)                      # .data is where the returned rows live (a list of dicts)