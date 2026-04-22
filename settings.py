import os
from datetime import datetime

API_AUTH = (
    os.getenv("PARSER_USER", "parser"),
    os.getenv("PARSER_PASSWORD", "nekogeslo"),
)
API_URL = os.getenv("PARSER_PARLADATA_API_URL", "http://localhost:8000/v3")
MANDATE_STARTIME = datetime.strptime(
    os.getenv("PARSER_MANDATE_START_DATE", "2026-04-10"), "%Y-%m-%d"
)
MAIN_ORG_ID = os.getenv("PARSER_MAIN_ORG_ID", 590)
MANDATE = os.getenv("PARSER_MANDATE_ID", "4")
MANDATE_GOV_ID = os.getenv("PARSER_MANDATE_GOV_ID", "X")
BASE_URL = "https://www.dz-rs.si"
