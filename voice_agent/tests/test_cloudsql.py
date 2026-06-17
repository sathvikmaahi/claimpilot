import os
from dotenv import load_dotenv
import psycopg2

load_dotenv("/Users/shubhangvangari/Documents/AI_fellowship/care-claim-repo/care-claim-ai/section_1_agent/.env")   
conn = psycopg2.connect(
    host=os.environ["CLOUD_SQL_HOST"],
    port=5432,
    dbname="claimpilot",
    user="postgres",
    password=os.environ["CLOUD_SQL_PASSWORD"],
    sslmode="require",
)

cur = conn.cursor()                                    # a cursor runs queries
cur.execute("select full_name, medicaid_id from care_recipients;")
for row in cur.fetchall():                             # fetch all returned rows
    print(row)

cur.close()
conn.close()