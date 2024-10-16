import os
from datetime import datetime

API_AUTH = (
    os.getenv("PARSER_USER", "parser"),
    os.getenv("PARSER_PASSWORD", "nekogeslo"),
)
API_URL = os.getenv("PARSER_PARLADATA_API_URL", "http://localhost:8000/v3")
MANDATE_STARTIME = datetime.strptime(
    os.getenv("PARSER_MANDATE_START_DATE", "2022-05-13"), "%Y-%m-%d"
)
MAIN_ORG_ID = os.getenv("PARSER_MAIN_ORG_ID", "137")
MANDATE = os.getenv("PARSER_MANDATE_ID", "2")
MANDATE_GOV_ID = os.getenv("PARSER_MANDATE_GOV_ID", "IX")
BASE_URL = "https://www.dz-rs.si"
